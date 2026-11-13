"""The download queue: searches Soulseek, picks the best file, downloads, renames."""
import json
import shutil
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

import matching
from i18n import T
from slskd_mgr import NotConnected, SlskdError

QUEUED, SEARCHING, NOT_FOUND, NEEDS_OK, PLACE, DOWNLOADING, DONE, SKIPPED = (
    "queued", "searching", "notfound", "needsok", "place", "downloading", "done", "skipped")

KEEPS_STOPPING = T("The Soulseek engine keeps stopping. Check that Windows Firewall or your antivirus isn't blocking slskd.exe.")
RETRY_SECONDS = 10 * 60
PROGRESS_FILE = "session-progress.json"


@dataclass
class Track:
    idx: int
    artists: list
    title: str
    album: str = ""
    duration: int = 0
    state: str = QUEUED
    detail: str = ""
    percent: float = 0.0
    place: object = None
    saved_as: str = ""
    label: str = ""
    user: str = ""
    tid: str = ""
    allow_low: bool = False
    busy: bool = False
    next_try: float = 0.0
    pos_at: float = 0.0
    lost: int = 0
    ver: int = 0
    candidates: list = field(default_factory=list)
    bad_users: set = field(default_factory=set)

    @property
    def display(self):
        if self.artists:
            return "%s - %s" % (self.artists[0], self.title)
        return self.title

    @property
    def dest(self):
        return "t%05d" % self.idx


class Engine:
    def __init__(self, slskd, session_dir, session_name, tracks, mode="best", max_active=10,
                 retry_seconds=RETRY_SECONDS, search_timeout_ms=25000, log=lambda m: None):
        self.slskd = slskd
        self.session_dir = Path(session_dir)
        self.session_name = session_name
        self.tracks = tracks
        self.mode = mode
        self.max_active = max_active
        self.retry_seconds = retry_seconds
        self.search_timeout_ms = search_timeout_ms
        self.log = log
        self.lock = threading.RLock()
        self.dirty = set()
        self.stop_evt = threading.Event()
        self._gate = threading.Lock()
        self._last_search = 0.0
        self.width = max(2, len(str(len(tracks))))
        self.pending = deque(t for t in tracks if t.state == QUEUED)
        self.by_idx = {t.idx: t for t in tracks}
        self.thread = None
        self.notice = ""
        self.engine_down = False
        self._health_fail = 0
        self._last_health = 0.0
        self._restarts = deque(maxlen=6)

    # ---------- lifecycle ----------
    def start(self):
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_evt.set()
        with self.lock:
            live = [t for t in self.tracks if t.tid and t.state in (DOWNLOADING, PLACE)]
        for t in live:
            self._delete_transfer(t)
        with self.lock:
            for t in self.tracks:
                if t.state in (SEARCHING, DOWNLOADING, PLACE):
                    self._set(t, state=QUEUED, tid="", percent=0, place=None, detail="")
        self._save()

    def finished(self):
        with self.lock:
            return all(t.state in (DONE, SKIPPED) for t in self.tracks)

    def _spawn(self, fn, *args):
        threading.Thread(target=fn, args=args, daemon=True).start()

    def _set(self, t, **kw):
        with self.lock:
            changed = False
            for k, v in kw.items():
                if getattr(t, k) != v:
                    setattr(t, k, v)
                    changed = True
            if changed:
                t.ver += 1
                self.dirty.add(t.idx)

    def pop_dirty(self):
        with self.lock:
            d, self.dirty = self.dirty, set()
            return d

    # ---------- user actions ----------
    def allow_low_quality(self, t):
        with self.lock:
            if t.state != NEEDS_OK or t.busy:
                return
            t.allow_low = True
            t.busy = True
            self._set(t, state=SEARCHING, detail="")
        self._spawn(self._work_sources, t)

    def search_again(self, t):
        """Search a 'not found' song right now instead of waiting for its timer."""
        with self.lock:
            if t.state in (NOT_FOUND, NEEDS_OK) and not t.busy:
                t.next_try = 0.0

    def skip(self, t):
        with self.lock:
            if t.state == NEEDS_OK and not t.busy:
                self._set(t, state=SKIPPED, detail=T("Skipped by you"))

    # ---------- main loop ----------
    def _loop(self):
        last_poll = last_save = 0.0
        while not self.stop_evt.wait(0.5):
            now = time.time()
            try:
                if now - self._last_health >= 5:
                    self._last_health = now
                    self._check_engine()
                if not self.engine_down:
                    if now - last_poll >= 2:
                        self._poll()
                        last_poll = now
                    self._dispatch(now)
                if now - last_save >= 20:
                    self._save()
                    last_save = now
            except NotConnected:
                pass
            except Exception as e:
                self.log("loop error: %r" % (e,))

    # ---------- engine watchdog ----------
    def _check_engine(self):
        if self.engine_down or self.slskd.external:
            return
        dead = not self.slskd.running()
        if not dead:
            try:
                self.slskd.api("GET", "/application", timeout=5)
                self._health_fail = 0
            except SlskdError:
                self._health_fail += 1
                dead = self._health_fail >= 4
        if dead:
            self.engine_down = True
            self._spawn(self._restart_engine)

    def _restart_engine(self):
        try:
            now = time.time()
            self._restarts.append(now)
            self.log("Soulseek engine stopped; restarting")
            if len(self._restarts) >= 5 and now - self._restarts[0] < 600:
                self.notice = KEEPS_STOPPING
            else:
                self.notice = T("Soulseek engine stopped, restarting\u2026")
            ok = False
            if self.slskd.restart():
                ok = self.slskd.wait_logged_in(timeout=90, cancel=self.stop_evt.is_set) == "ok"
            if ok:
                self._health_fail = 0
                if self.notice != KEEPS_STOPPING:
                    self.notice = ""
                with self.lock:
                    for t in self.tracks:
                        if t.state == NOT_FOUND and t.detail.startswith(T("Search error")):
                            t.next_try = 0.0
            else:
                self.log("engine restart failed")
                self.notice = T("Couldn't restart the Soulseek engine. Press Stop, then Start download.")
        finally:
            self.engine_down = False

    def _dispatch(self, now):
        with self.lock:
            active = sum(1 for t in self.tracks if t.state in (SEARCHING, DOWNLOADING))
            limit = max(1, int(self.max_active))
            while active < limit and self.pending:
                t = self.pending.popleft()
                if t.state != QUEUED:
                    continue
                t.busy = True
                self._set(t, state=SEARCHING, detail="")
                active += 1
                self._spawn(self._work_search, t)
            # Low-quality songs still waiting for an OK look for something better.
            for t in self.tracks:
                if t.state == NEEDS_OK and not t.busy and not t.allow_low and now >= t.next_try:
                    t.busy = True
                    self._spawn(self._work_search, t, True)
            # Not-found songs search again on their own timer; this ignores the active limit.
            for t in self.tracks:
                if t.state == NOT_FOUND and not t.busy and now >= t.next_try:
                    t.busy = True
                    self._set(t, state=SEARCHING, detail="")
                    self._spawn(self._work_search, t)

    # ---------- workers ----------
    def _work_search(self, t, keep=False):
        """keep=True: a low-quality song searching again; if nothing comes back it keeps its offer."""
        try:
            cands = self._search(t)
            if self.stop_evt.is_set():
                if not keep:
                    self._set(t, state=QUEUED)
                return
            if not cands and keep:
                self._set(t, next_try=time.time() + self.retry_seconds)
                return
            with self.lock:
                t.candidates = cands
                t.bad_users = set()
            if not cands:
                self._not_found(t)
                return
            self._try_sources(t)
        except NotConnected:
            time.sleep(5)
            with self.lock:
                self._set(t, state=QUEUED)
                self.pending.appendleft(t)
        except Exception as e:
            self.log("search error for %s: %r" % (t.display, e))
            self._not_found(t, T("Search error") + ": %s" % str(e)[:120])
        finally:
            t.busy = False

    def _work_sources(self, t, failed_user=None):
        try:
            if failed_user:
                with self.lock:
                    t.bad_users.add(failed_user)
                self._delete_transfer(t)
                self._set(t, tid="", detail=T("Trying another source"))
            self._try_sources(t)
        except NotConnected:
            time.sleep(5)
            with self.lock:
                self._set(t, state=QUEUED, tid="")
                self.pending.appendleft(t)
        except Exception as e:
            self.log("source error for %s: %r" % (t.display, e))
            self._not_found(t)
        finally:
            t.busy = False

    def _not_found(self, t, why=""):
        self._set(t, state=NOT_FOUND, tid="", next_try=time.time() + self.retry_seconds,
                  detail=why, percent=0, place=None)

    def _throttle(self):
        with self._gate:
            wait = 1.2 - (time.time() - self._last_search)
            if wait > 0:
                time.sleep(wait)
            self._last_search = time.time()

    def _search(self, t):
        for q in matching.queries(t):
            self._throttle()
            sid = str(uuid.uuid4())
            rejected = False
            resp = []
            try:
                # Some versions answer this call immediately, before results have arrived.
                try:
                    self.slskd.api("POST", "/searches", timeout=self.search_timeout_ms / 1000 + 60, json={
                        "id": sid, "searchText": q, "searchTimeout": self.search_timeout_ms,
                        "filterResponses": True, "minimumResponseFileCount": 1,
                        "responseLimit": 100, "fileLimit": 10000})
                except NotConnected:
                    raise
                except SlskdError as e:
                    if str(e).startswith("400"):  # Soulseek rejected this query; try the next one
                        self.log("query %r rejected: %s" % (q, e))
                        continue
                    raise
                deadline = time.time() + self.search_timeout_ms / 1000 + 45
                while time.time() < deadline and not self.stop_evt.is_set():
                    try:
                        info = self.slskd.api("GET", "/searches/" + sid) or {}
                    except NotConnected:
                        raise
                    except SlskdError:
                        break
                    if info.get("isComplete") or "completed" in str(info.get("state", "")).lower():
                        break
                    time.sleep(1)
                resp = self.slskd.api("GET", "/searches/%s/responses" % sid, timeout=60)
            finally:
                try:
                    self.slskd.api("DELETE", "/searches/" + sid)
                except SlskdError:
                    pass
            cands = matching.rank(resp or [], t, self.mode)
            self.log("search %r: %d responses, %d usable" % (q, len(resp or []), len(cands)))
            if resp and not cands:
                names = [f.get("filename", "") for r in resp[:3] for f in (r.get("files") or [])[:1]]
                self.log("  none accepted; sample results: %r" % (names,))
            if cands:
                return cands
        return []

    def _try_sources(self, t):
        while not self.stop_evt.is_set():
            with self.lock:
                cand = next((c for c in t.candidates if c["user"] not in t.bad_users), None)
            if cand is None:
                self._not_found(t)
                return
            if cand["tier"] == matching.TIER_LOW and not t.allow_low:
                self._set(t, state=NEEDS_OK, label=cand["label"], user=cand["user"], tid="",
                          next_try=time.time() + self.retry_seconds,
                          detail=T("Best found: %s from %s. Not downloading until you say so.")
                                 % (cand["label"], cand["user"]))
                return
            if self._enqueue(t, cand):
                return
            with self.lock:
                t.bad_users.add(cand["user"])

    def _enqueue(self, t, cand):
        shutil.rmtree(self.slskd.incoming / t.dest, ignore_errors=True)
        body = {"id": str(uuid.uuid4()), "username": cand["user"],
                "files": [{"filename": cand["filename"], "size": cand["size"]}],
                "options": {"destination": t.dest}}
        try:
            res = self.slskd.api("POST", "/transfers/downloads/batches", json=body)
        except NotConnected:
            raise
        except SlskdError as e:
            self.log("enqueue refused (%s): %s" % (cand["user"], e))
            return False
        try:
            tid = res["batch"]["transfers"][0]["id"]
        except (TypeError, KeyError, IndexError):
            return False
        self._set(t, state=DOWNLOADING, tid=tid, label=cand["label"], user=cand["user"],
                  percent=0, place=None, lost=0,
                  detail="%s from %s" % (cand["label"], cand["user"]))
        return True

    def _delete_transfer(self, t):
        if not (t.tid and t.user):
            return
        try:
            self.slskd.api("DELETE", "/transfers/downloads/%s/%s" % (t.user, t.tid),
                           params={"remove": "true"})
        except SlskdError:
            pass

    # ---------- polling transfers ----------
    def _poll(self):
        data = self.slskd.api("GET", "/transfers/downloads")
        flat = {}

        def walk(x):
            if isinstance(x, dict):
                if "id" in x and "state" in x and "filename" in x:
                    flat[x["id"]] = x
                    return
                for v in x.values():
                    walk(v)
            elif isinstance(x, list):
                for v in x:
                    walk(v)

        walk(data)
        with self.lock:
            watched = [t for t in self.tracks
                       if t.tid and t.state in (DOWNLOADING, PLACE) and not t.busy]
        position_calls = 0
        for t in watched:
            tr = flat.get(t.tid)
            if tr is None:
                t.lost += 1
                if t.lost >= 3:
                    self._source_failed(t)
                continue
            t.lost = 0
            st = (tr.get("state") or "").lower()
            if st.startswith("completed"):
                if "succeeded" in st:
                    with self.lock:
                        t.busy = True
                    self._spawn(self._finish, t)
                else:
                    self.log("transfer failed (%s): %s" % (t.user, st))
                    self._source_failed(t)
            elif "queued" in st and "remotely" in st:
                place = tr.get("placeInQueue")
                self._set(t, state=PLACE, place=place, percent=0)
                if position_calls < 3 and time.time() - t.pos_at > 30:
                    t.pos_at = time.time()
                    position_calls += 1
                    try:
                        p = self.slskd.api("GET", "/transfers/downloads/%s/%s/position" % (t.user, t.tid))
                        if isinstance(p, int):
                            self._set(t, place=p)
                        elif isinstance(p, dict) and p.get("placeInQueue") is not None:
                            self._set(t, place=p["placeInQueue"])
                    except SlskdError:
                        pass
            elif "inprogress" in st:
                self._set(t, state=DOWNLOADING, percent=float(tr.get("percentComplete") or 0), place=None)
            else:
                self._set(t, state=DOWNLOADING, place=None)

    def _source_failed(self, t):
        with self.lock:
            if t.busy:
                return
            t.busy = True
            user = t.user
            self._set(t, state=SEARCHING, detail=T("Trying another source"))
        self._spawn(self._work_sources, t, user)

    # ---------- finishing ----------
    def _finish(self, t):
        try:
            folder = self.slskd.incoming / t.dest
            files = [p for p in folder.rglob("*")
                     if p.is_file() and p.suffix.lower() in (".flac", ".mp3")]
            if not files:
                self.log("finished transfer but no file found for %s" % t.display)
                self._work_sources(t, t.user)
                return
            src = max(files, key=lambda p: p.stat().st_size)
            name = self._final_name(t, src)
            self.session_dir.mkdir(parents=True, exist_ok=True)
            target = self.session_dir / name
            n = 2
            while target.exists():
                target = self.session_dir / ("%s (%d)%s" % (name[:-len(src.suffix)], n, src.suffix.upper()))
                n += 1
            shutil.move(str(src), str(target))
            shutil.rmtree(folder, ignore_errors=True)
            self._delete_transfer(t)
            self._set(t, state=DONE, saved_as=target.name, percent=100, place=None, tid="",
                      detail=t.label)
            self._save()
        except Exception as e:
            self.log("finish error for %s: %r" % (t.display, e))
            self._set(t, state=NOT_FOUND, next_try=time.time() + 60, detail="")
        finally:
            t.busy = False

    def _final_name(self, t, src):
        artist = t.artists[0] if t.artists else ""
        title, album = t.title, t.album
        if not (artist and title and album):
            tags = _read_tags(src)
            artist = artist or tags.get("artist") or "Unknown Artist"
            title = title or tags.get("title") or src.stem
            album = album or tags.get("album") or "Unknown Album"
        parts = [
            "%0*d" % (self.width, t.idx),
            matching.sanitize(artist, 60),
            matching.sanitize(album, 60),
            matching.sanitize(title, 80),
        ]
        return " - ".join(parts) + src.suffix.upper()

    # ---------- display helpers ----------
    @staticmethod
    def status_text(t):
        if t.state == PLACE:
            return T("Place: %s") % (t.place if t.place is not None else "?")
        if t.state == DOWNLOADING:
            return T("Downloading %d%%") % int(t.percent)
        if t.state == NEEDS_OK:
            return T("Low quality only")
        return {QUEUED: T("Queued"), SEARCHING: T("Searching"), NOT_FOUND: T("Not found"),
                NEEDS_OK: T("Low quality only"), DONE: T("Done"), SKIPPED: T("Skipped")}[t.state]

    @staticmethod
    def detail_text(t, now=None):
        now = now or time.time()
        if t.state == DONE:
            return T("%s  |  Saved as: %s") % (t.label, t.saved_as)
        if t.state == NOT_FOUND:
            mins = max(1, int((t.next_try - now) / 60 + 0.99))
            return T("%s, searching again in %d min") % (t.detail or T("No matching files"), mins)
        if t.state == NEEDS_OK:
            mins = max(1, int((t.next_try - now) / 60 + 0.99))
            return T("%s from %s. Waiting for your OK, searching for better in %d min") % (t.label, t.user, mins)
        if t.state == PLACE:
            return T("%s from %s, starts automatically when a slot opens") % (t.label, t.user)
        return t.detail

    def counts(self):
        with self.lock:
            c = {s: 0 for s in (QUEUED, SEARCHING, NOT_FOUND, NEEDS_OK, PLACE, DOWNLOADING, DONE, SKIPPED)}
            for t in self.tracks:
                c[t.state] += 1
            return c

    # ---------- progress file ----------
    def _save(self):
        try:
            with self.lock:
                done = [{"idx": t.idx, "title": t.title, "saved_as": t.saved_as, "label": t.label}
                        for t in self.tracks if t.state == DONE]
            self.session_dir.mkdir(parents=True, exist_ok=True)
            (self.session_dir / PROGRESS_FILE).write_text(json.dumps(done), encoding="utf-8")
        except Exception as e:
            self.log("save error: %r" % (e,))


def restore_progress(tracks, session_dir):
    """Mark songs already saved in this session folder as done (lets you resume)."""
    f = Path(session_dir) / PROGRESS_FILE
    try:
        saved = json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return 0
    by_idx = {t.idx: t for t in tracks}
    n = 0
    for d in saved:
        t = by_idx.get(d.get("idx"))
        if t and matching.norm(t.title) == matching.norm(d.get("title", "")) \
                and (Path(session_dir) / d.get("saved_as", "?")).exists():
            t.state, t.saved_as, t.label = DONE, d["saved_as"], d.get("label", "")
            n += 1
    return n


def apply_saved(tracks, done, skipped, session_dir):
    """Apply progress stored in a .slsk session file (done and skipped songs)."""
    by_idx = {t.idx: t for t in tracks}
    for d in done or []:
        t = by_idx.get(d.get("idx"))
        if t and matching.norm(t.title) == matching.norm(d.get("title", "")) \
                and (Path(session_dir) / d.get("saved_as", "?")).exists():
            t.state, t.saved_as, t.label = DONE, d["saved_as"], d.get("label", "")
    for idx in skipped or []:
        t = by_idx.get(idx)
        if t and t.state == QUEUED:
            t.state = SKIPPED


def _read_tags(path):
    out = {}
    try:
        import mutagen
        m = mutagen.File(str(path), easy=True)
        if m:
            for k in ("artist", "album", "title"):
                v = m.get(k)
                if v:
                    out[k] = str(v[0])
    except Exception:
        pass
    return out
