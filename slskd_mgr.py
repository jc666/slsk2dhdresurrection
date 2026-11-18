"""Downloads, configures and runs slskd (the Soulseek engine) in the background."""
from i18n import T
import json
import os
import socket
import subprocess
import time
import zipfile
from pathlib import Path

import requests


class SlskdError(Exception):
    pass


class NotConnected(SlskdError):
    pass


def _free_port(start, host=""):
    for p in range(start, start + 200):
        with socket.socket() as s:
            try:
                s.bind((host, p))
                return p
            except OSError:
                continue
    raise SlskdError("No free network port found.")


class Slskd:
    def __init__(self, data_dir, log=lambda m: None):
        self.data_dir = Path(data_dir)
        self.bin_dir = self.data_dir / "slskd-bin"
        self.app_dir = self.data_dir / "slskd-app"
        self.incoming = self.data_dir / "incoming"
        self.log = log
        self.proc = None
        self.base = None
        self.key = "vibe" + os.urandom(12).hex()
        self.creds = None
        self.external = bool(os.environ.get("VIBE_SLSKD_URL"))  # used by tests only
        if self.external:
            self.base = os.environ["VIBE_SLSKD_URL"].rstrip("/")
            self.key = os.environ.get("VIBE_SLSKD_KEY", self.key)

    @property
    def exe(self):
        override = os.environ.get("VIBE_SLSKD_BIN")
        if override:
            return Path(override)
        return self.bin_dir / ("slskd.exe" if os.name == "nt" else "slskd")

    # ---- install ----
    def installed(self):
        return self.external or self.exe.exists()

    def ensure_installed(self, progress=lambda done, total: None):
        if self.installed():
            return
        self.bin_dir.mkdir(parents=True, exist_ok=True)
        try:
            r = requests.get("https://github.com/slskd/slskd/releases/latest",
                             allow_redirects=False, timeout=30)
            tag = r.headers["Location"].rstrip("/").split("/")[-1]
            url = "https://github.com/slskd/slskd/releases/download/%s/slskd-%s-win-x64.zip" % (tag, tag)
            part = self.data_dir / "slskd-download.zip.part"
            with requests.get(url, stream=True, timeout=60) as resp:
                resp.raise_for_status()
                total = int(resp.headers.get("Content-Length", 0))
                done = 0
                with open(part, "wb") as fh:
                    for chunk in resp.iter_content(1 << 20):
                        fh.write(chunk)
                        done += len(chunk)
                        progress(done, total)
            with zipfile.ZipFile(part) as z:
                z.extractall(self.bin_dir)
            part.unlink()
        except Exception as e:
            raise SlskdError(T("Couldn't download the Soulseek engine (%s). Check your internet connection "
                               "and that GitHub isn't blocked, then try again.") % e)
        if not self.exe.exists():
            raise SlskdError(T("The Soulseek engine download looks incomplete. Delete the 'data' folder and try again."))

    # ---- run ----
    def _write_config(self, user, password, web_port, listen_port):
        self.app_dir.mkdir(parents=True, exist_ok=True)
        self.incoming.mkdir(parents=True, exist_ok=True)
        q = json.dumps
        cfg = "\n".join([
            "flags:",
            "  no_logo: true",
            "  no_version_check: true",
            "remote_configuration: false",
            "directories:",
            "  downloads: " + q(str(self.incoming)),
            "  incomplete: " + q(str(self.app_dir / "incomplete")),
            "shares:",
            "  directories: []",
            "web:",
            "  port: %d" % web_port,
            "  ip_address: 127.0.0.1",
            "  https:",
            "    disabled: true",
            "  authentication:",
            "    disabled: false",
            "    api_keys:",
            "      vibeseek:",
            "        key: " + self.key,
            "        role: administrator",
            "        cidr: 127.0.0.1/32",
            "soulseek:",
            "  username: " + q(user),
            "  password: " + q(password),
            "  listen_port: %d" % listen_port,
            "logger:",
            "  no_disk: true",
            "",
        ])
        (self.app_dir / "slskd.yml").write_text(cfg, encoding="utf-8")

    def running(self):
        return self.external or (self.proc is not None and self.proc.poll() is None)

    def start(self, user, password):
        if self.external:
            return
        if self.running() and self.creds == (user, password):
            return
        self.stop()
        web_port = _free_port(5030, "127.0.0.1")
        listen_port = _free_port(50300)
        self._write_config(user, password, web_port, listen_port)
        self.base = "http://127.0.0.1:%d" % web_port
        self.creds = (user, password)
        logfile = open(self.app_dir / "engine-console.log", "ab")
        flags = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW
        self.proc = subprocess.Popen([str(self.exe), "--app-dir", str(self.app_dir)],
                                     cwd=str(self.exe.parent), stdout=logfile,
                                     stderr=subprocess.STDOUT, creationflags=flags)

    def wait_logged_in(self, timeout=75, cancel=lambda: False):
        """Returns 'ok', or a text describing what went wrong."""
        end = time.time() + timeout
        reachable = False
        while time.time() < end and not cancel():
            if self.proc is not None and self.proc.poll() is not None:
                return T("The Soulseek engine closed unexpectedly. ") + self._log_hint()
            try:
                info = self.api("GET", "/application", timeout=5)
                reachable = True
                if (info.get("server") or {}).get("isLoggedIn"):
                    return "ok"
                last = "state: " + str(info.get("server") or sorted(info))[:200]
                if last != getattr(self, "_lastlog", None):
                    self._lastlog = last
                    self.log("login wait: " + last)
            except SlskdError as e:
                last = "API error: %s" % str(e)[:150]
                if last != getattr(self, "_lastlog", None):
                    self._lastlog = last
                    self.log("login wait: " + last)
            time.sleep(1)
        if not reachable:
            return T("The Soulseek engine didn't start. ") + self._log_hint()
        return T("Couldn't log in to Soulseek. If this username already exists, the password must match it; "
                 "otherwise pick a different username in Soulseek login.")

    def _log_hint(self):
        return T("(Is Windows Firewall or an antivirus blocking 'slskd.exe' in the data folder?)")

    def restart(self):
        """Start the engine again with the same login (after a crash)."""
        if self.external or not self.creds:
            return False
        user, password = self.creds
        if self.proc is not None and self.proc.poll() is None:
            self.proc.kill()
        self.proc = None
        self.start(user, password)
        return True

    def stop(self):
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(8)
            except Exception:
                self.proc.kill()
        self.proc = None
        self.creds = None

    # ---- API ----
    def api(self, method, path, timeout=30, **kw):
        try:
            r = requests.request(method, self.base + "/api/v0" + path,
                                 headers={"X-API-Key": self.key}, timeout=timeout, **kw)
        except requests.ConnectionError as e:
            raise NotConnected("engine unreachable: %s" % str(e)[:120])
        except requests.RequestException as e:
            raise SlskdError(str(e))
        if r.status_code == 409 or "must be connected" in r.text:
            raise NotConnected(r.text[:200])
        if r.status_code >= 400:
            raise SlskdError("%s: %s" % (r.status_code, r.text[:200]))
        if not r.content:
            return None
        try:
            return r.json()
        except ValueError:
            return None
