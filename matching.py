"""Turning Soulseek search results into a ranked list of acceptable files.

Rules (as requested):
  * Only FLAC and MP3 are considered. Everything else is ignored.
  * FLAC 16-bit/44.1 kHz is preferred. Higher-resolution FLAC is used only if
    no 16/44.1 FLAC exists.
  * MP3: 320 kbps first, V0 only if there is no 320.
  * Any other MP3 (V1, V2, 256, 192, ...) is "low quality only": it is never
    downloaded without the user's OK.
  * "Boomer mode" ignores FLAC completely.
"""
import re
import unicodedata

TIER_FLAC_1644 = 0
TIER_FLAC_UNKNOWN = 1
TIER_FLAC_HIGHER = 2
TIER_MP3_320 = 3
TIER_MP3_V0 = 4
TIER_LOW = 5

VERSION_WORDS = {
    "remix", "rmx", "live", "cover", "instrumental", "acapella", "acappella",
    "karaoke", "edit", "dub", "demo", "bootleg", "mashup", "slowed", "sped",
    "nightcore", "rework", "acoustic", "unplugged",
}
NOISE_WORDS = {
    "original", "mix", "version", "remaster", "remastered", "feat", "ft",
    "featuring", "explicit", "clean", "album", "single", "radio", "official",
    "audio", "hq", "cdq", "web", "flac", "mp3", "320", "kbps", "vbr", "v0",
    "mono", "stereo", "bonus", "track", "the",
}


_STYLED = re.compile(r"(?<=\b\w)[.\u2022\u00b7\u2219*](?=\w(?:[.\u2022\u00b7\u2219*]|\b))")
_FEAT_PAREN = re.compile(r"\s*[\(\[]\s*(?:featuring|feat\.?|ft\.?)\b[^\)\]]*[\)\]]", re.I)
_FEAT_TAIL = re.compile(r"\s+(?:featuring|feat\.?|ft\.?|with)\s+.*$", re.I)


def clean_artist(a):
    """'Rihanna featuring Jay-Z' -> 'Rihanna' (the featured artist lives in the title)."""
    a = _FEAT_PAREN.sub("", a or "")
    a = _FEAT_TAIL.sub("", a)
    return a.strip()


def split_artists(a):
    """Individual artists in a credit like 'Kanye West & JAY-Z'."""
    parts = re.split(r"\s*(?:&|,|;|/|\bx\b|\band\b)\s*", a or "", flags=re.I)
    return [p for p in (x.strip() for x in parts) if p]


def primary_artist(a):
    p = split_artists(clean_artist(a))
    return p[0] if p else (a or "")


def norm(s):
    s = _STYLED.sub("", s or "")  # H\u2022a\u2022m -> Ham, H.A.M -> HAM
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = s.replace("&", " and ")
    return re.sub(r"[\W_]+", " ", s, flags=re.UNICODE).strip()


def tokens(s):
    return norm(s).split()


def base_title(title):
    original = title or ""
    t = re.sub(r"\s*[\(\[][^\)\]]*[\)\]]", "", original)
    t = re.sub(r"\s+-\s+.*(remaster|version|mix|edit|live|mono|stereo|radio|single).*$",
               "", t, flags=re.I)
    t = re.sub(r"\s+(feat\.?|ft\.?|featuring)\s+.*$", "", t, flags=re.I)
    return t.strip() or original.strip()


def queries(track):
    """Search texts to try, most specific first."""
    title = norm(base_title(track.title))
    out = []
    if track.artists:
        out.append((norm(primary_artist(track.artists[0])) + " " + title).strip())
    if title and title not in out:
        out.append(title)
    # Soulseek refuses a search with no word longer than one character.
    return [q for q in out if any(len(w) > 1 for w in q.split())]


def parse_song_list(text):
    """One song per line, 'Artist - Title'. Returns [(artist, title)]."""
    songs = []
    for raw in (text or "").splitlines():
        line = re.sub(r"^\s*\d+\s*[\.\)]\s+", "", raw).strip()
        if not line:
            continue
        parts = re.split(r"\s+[-\u2013\u2014]\s+", line, maxsplit=1)
        if len(parts) == 2 and parts[0].strip() and parts[1].strip():
            songs.append((parts[0].strip(), parts[1].strip()))
        else:
            songs.append(("", line))
    return songs


def _basename(path):
    return path.replace("/", "\\").split("\\")[-1]


def _find_block(hay, needle):
    """Last index where `needle` appears as a contiguous run in `hay`, or -1."""
    n = len(needle)
    for i in range(len(hay) - n, -1, -1):
        if hay[i:i + n] == needle:
            return i
    return -1


def classify(f, mode):
    """Return (tier, sub, label, bitrate) for a file dict, or None to ignore."""
    ext = (f.get("extension") or "").lower().lstrip(".")
    if not ext:
        name = _basename(f.get("filename", ""))
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    size = f.get("size") or 0
    if ext == "flac":
        if mode == "boomer" or size < 1_500_000:
            return None
        depth = f.get("bitDepth") or 0
        rate = f.get("sampleRate") or 0
        br = f.get("bitRate") or 0
        if depth == 16 and rate == 44100:
            return TIER_FLAC_1644, (0, 0), "FLAC 16-bit / 44.1 kHz", br
        if depth and rate:
            label = "FLAC %d-bit / %g kHz" % (depth, rate / 1000.0)
            return TIER_FLAC_HIGHER, (depth, rate), label, br
        if br and br > 1500:
            return TIER_FLAC_HIGHER, (24, 96000), __import__("i18n").T("FLAC (high resolution)"), br
        return TIER_FLAC_UNKNOWN, (0, 0), "FLAC", br
    if ext == "mp3":
        if size < 1_000_000:
            return None
        br = f.get("bitRate") or 0
        length = f.get("length") or 0
        vbr = bool(f.get("isVariableBitRate"))
        if not br and length:
            br = int(size * 8 / length / 1000)
            vbr = False
        if not br:
            return None
        if br >= 315:
            return TIER_MP3_320, (0, 0), "MP3 320 kbps", br
        if vbr:
            if br >= 235:
                return TIER_MP3_V0, (0, 0), "MP3 V0 (~%d kbps)" % br, br
            if br >= 205:
                name = "V1"
            elif br >= 170:
                name = "V2"
            else:
                name = "VBR ~%d kbps" % br
            return TIER_LOW, (-br, 0), "MP3 " + name, br
        return TIER_LOW, (-br, 0), "MP3 %d kbps" % br, br
    return None


def rank(responses, track, mode):
    """Filter and sort search responses into candidates (best first)."""
    title_tok = tokens(base_title(track.title))
    if not title_tok:
        return []
    artist_sets = [set(tokens(p)) for a in track.artists for p in split_artists(clean_artist(a)) if tokens(p)]
    artist_all = set().union(*artist_sets) if artist_sets else set()
    asked_versions = VERSION_WORDS & set(tokens(track.title))
    allowed_after = artist_all | NOISE_WORDS
    best_per_user = {}
    for r in responses or []:
        user = r.get("username")
        if not user:
            continue
        free = bool(r.get("hasFreeUploadSlot"))
        qlen = r.get("queueLength") or 0
        speed = r.get("uploadSpeed") or 0
        for f in r.get("files") or []:
            fn = f.get("filename") or ""
            q = classify(f, mode)
            if not q:
                continue
            tier, sub, label, br = q
            name = _basename(fn)
            stem = name.rsplit(".", 1)[0]
            bt = tokens(stem)
            pos = _find_block(bt, title_tok)
            if pos < 0:
                continue
            after = bt[pos + len(title_tok):]
            if any((t not in allowed_after) and not t.isdigit() for t in after):
                continue
            if (VERSION_WORDS & set(bt)) - asked_versions:
                continue
            if artist_sets:
                ptoks = set(tokens(fn))
                if not any(s <= ptoks for s in artist_sets):
                    continue
            if track.duration and f.get("length"):
                if abs(f["length"] - track.duration) > max(6, track.duration * 0.03):
                    continue
            cand = {
                "user": user, "filename": fn, "size": f.get("size") or 0,
                "tier": tier, "sub": sub, "label": label, "br": br,
                "free": free, "qlen": qlen, "speed": speed,
            }
            key = _sort_key(cand)
            old = best_per_user.get(user)
            if old is None or key < _sort_key(old):
                best_per_user[user] = cand
    return sorted(best_per_user.values(), key=_sort_key)


def _sort_key(c):
    return (c["tier"], c["sub"], 0 if c["free"] else 1, c["qlen"], -c["speed"])


_BAD = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize(s, limit=80):
    s = _BAD.sub("_", s or "")
    s = re.sub(r"\s+", " ", s).strip(" .")
    if len(s) > limit:
        s = s[:limit].rstrip(" .")
    return s or "_"


def import_text(raw, filename=""):
    """Turn an exported playlist file (.txt or .csv) into 'Artist - Title' lines."""
    import csv
    import io
    raw = (raw or "").lstrip("\ufeff")
    first = raw.splitlines()[0] if raw.strip() else ""
    looks_csv = filename.lower().endswith(".csv") or (first.count(",") >= 2 and " - " not in first)
    if not looks_csv:
        return "\n".join("%s - %s" % (a, t) if a else t for a, t in parse_song_list(raw))
    rows = list(csv.reader(io.StringIO(raw)))
    if not rows:
        return ""
    head = [h.strip().lower() for h in rows[0]]

    def col(*names):
        for n in names:
            for i, h in enumerate(head):
                if h == n:
                    return i
        for n in names:
            for i, h in enumerate(head):
                if n in h:
                    return i
        return None

    ia, it = col("artist name(s)", "artist names", "artists", "artist"), col("track name", "track", "title", "song", "name")
    if ia is None or it is None:
        raise ValueError("Couldn't find the Artist and Title columns in that file.")
    out = []
    for r in rows[1:]:
        if len(r) > max(ia, it) and r[it].strip():
            artist = re.split(r"\s*;\s*", r[ia].strip())[0]
            out.append("%s - %s" % (artist, r[it].strip()) if artist else r[it].strip())
    return "\n".join(out)


def swap_lines(text):
    """Swap 'A - B' to 'B - A' on every line (fixes Title - Artist exports)."""
    out = []
    for line in (text or "").splitlines():
        parts = re.split(r"\s+[-\u2013\u2014]\s+", line, maxsplit=1)
        out.append("%s - %s" % (parts[1].strip(), parts[0].strip()) if len(parts) == 2 else line)
    return "\n".join(out)
