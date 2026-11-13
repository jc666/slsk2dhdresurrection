"""The window."""
import json
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import engine as eng
import matching
import i18n
import settings
from i18n import T
from slskd_mgr import Slskd

TITLE = "SLSK 2D HD Remake Remaster ~resurrection~"
TUNE_URL = "https://www.tunemymusic.com/transfer"
BLACK, WHITE, RED, YELLOW = "#000000", "#FFFFFF", "#EF0606", "#EFE806"
BG = BLACK           # window background
FIELD, FG = WHITE, BLACK   # white fields and black text inside them
GREY_TEXT = "#6B6B6B"      # text of disabled buttons
SELECT_ROW = "#DDDDDD"
CYCLE = ["d20000", "d26400", "d2b400", "b4d200", "75d200", "00d288", "00d27e",
         "009fd2", "0068d2", "1100d2", "6d00d2", "9f00d2", "d20075"]  # 1 s fade each, 13 s loop
CYCLE_RGB = [tuple(int(c[i:i + 2], 16) for i in (0, 2, 4)) for c in CYCLE]
TAG_COLORS = {
    eng.DONE: "#1E7A3C", eng.DOWNLOADING: "#8A5F00", eng.SEARCHING: "#8A5F00",
    eng.PLACE: "#1F5FBF", eng.NOT_FOUND: "#B3261E", eng.NEEDS_OK: "#A04E00",
    eng.QUEUED: "#555555", eng.SKIPPED: "#555555",
}
FAMILY = "Segoe UI"


def load_fonts():
    """Make the bundled Open Sans available (Windows: private to this app)."""
    global FAMILY
    if os.name == "nt":
        try:
            import ctypes
            for f in ("OpenSans-Regular.ttf", "OpenSans-Bold.ttf"):
                ctypes.windll.gdi32.AddFontResourceExW(settings.resource_path("fonts/" + f), 0x10, 0)
        except Exception:
            pass
    if "Open Sans" in tkfont.families():
        FAMILY = "Open Sans"


def F(size, style="normal"):
    return (FAMILY, size, style)


class FlatButton(tk.Canvas):
    """Flat coloured button. Its size is exactly what the old Segoe UI 10pt button was
    (so the layout never changes); the label is 58% of the button height when that fits,
    otherwise it falls back to 10pt."""
    TEXT_RATIO = 0.58

    def __init__(self, parent, text, command, fill=YELLOW, bold=False, outline=None, state="normal", bg=BG, always_black=False):
        self._old = tkfont.Font(family="Segoe UI", size=10, weight="bold" if bold else "normal")
        w = self._old.measure(text) + 2 * 12 + 2
        h = self._old.metrics("linespace") + 2 * 6 + 2
        super().__init__(parent, width=w, height=h, bg=bg, bd=0, highlightthickness=0, cursor="hand2")
        self._text, self._cmd, self._fill, self._bold = text, command, fill, bold
        self._outline, self._state = outline, state
        self._always_black = always_black
        self._fonts = {}
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<ButtonRelease-1>", self._release)
        if state == "disabled":
            super().configure(cursor="arrow")

    def _font(self, w, h):
        key = (self._text, w, h, self._bold)
        f = self._fonts.get(key)
        if f is None:
            wt = "bold" if self._bold else "normal"
            px = max(8, round(self.TEXT_RATIO * h))
            while True:  # 58% of the height, or the largest size that fits the button width
                f = tkfont.Font(family=FAMILY, size=-px, weight=wt)
                if px <= 8 or f.measure(self._text.upper()) <= w - 16:
                    break
                px -= 1
            self._fonts[key] = f
        return f

    def _draw(self):
        w, h = self.winfo_width(), self.winfo_height()
        if w < 4 or h < 4:
            return
        self.delete("all")
        lw = 2 if self._outline else 0
        self.create_rectangle(lw // 2, lw // 2, w - 1 - lw // 2, h - 1 - lw // 2, fill=self._fill,
                              outline=self._outline or self._fill, width=max(1, lw), tags="bg")
        self.create_text(w // 2, h // 2, text=self._text.upper(), font=self._font(w, h),
                         fill=GREY_TEXT if self._state == "disabled" and not self._always_black else BLACK)

    def _release(self, e):
        if self._state == "normal" and 0 <= e.x < self.winfo_width() and 0 <= e.y < self.winfo_height():
            self._cmd()

    def set_fill(self, color):
        self._fill = color
        self.itemconfigure("bg", fill=color, outline=self._outline or color)

    def configure(self, cnf=None, **kw):
        redraw = False
        if "state" in kw:
            self._state = kw.pop("state")
            super().configure(cursor="arrow" if self._state == "disabled" else "hand2")
            redraw = True
        if "text" in kw:
            self._text = kw.pop("text")
            redraw = True
        if "bold" in kw:
            self._bold = kw.pop("bold")
            redraw = True
        if "fill" in kw:
            self._fill = kw.pop("fill")
            redraw = True
        if kw or cnf:
            super().configure(cnf, **kw)
        if redraw:
            self._draw()
    config = configure

    def cget(self, key):
        return {"state": self._state, "text": self._text}.get(key) or super().cget(key)


class ArrowButton(tk.Canvas):
    """Black square with a white arrow, held down to repeat."""

    def __init__(self, parent, up, command):
        super().__init__(parent, width=22, height=14, bg=BLACK, bd=0, highlightthickness=0, cursor="hand2")
        self._up, self._cmd, self._job = up, command, None
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<ButtonRelease-1>", self._stop)

    def _draw(self):
        w, h = self.winfo_width(), self.winfo_height()
        self.delete("all")
        cx, cy, a = w / 2, h / 2, max(3, min(w, h) // 4)
        pts = [cx - a - 1, cy + a / 2, cx + a + 1, cy + a / 2, cx, cy - a / 2 - 1] if self._up else \
              [cx - a - 1, cy - a / 2, cx + a + 1, cy - a / 2, cx, cy + a / 2 + 1]
        self.create_polygon(*pts, fill=WHITE, outline=WHITE)

    def _press(self, e):
        self._cmd()
        self._job = self.after(400, self._repeat)

    def _repeat(self):
        self._cmd()
        self._job = self.after(70, self._repeat)

    def _stop(self, e):
        if self._job:
            self.after_cancel(self._job)
            self._job = None
QUALITY_LABELS = {
    "best": T("Best quality (FLAC first, then MP3 320)"),
    "boomer": T("Boomer mode (MP3 only, ignores FLAC)"),
}
STEPS = [
    T("Open TuneMyMusic and select your service"),
    T("Paste the playlist URL (log in to your account if necessary)"),
    T("Click Choose destination"),
    T("Select Export to file at the bottom"),
]
NAME_NOTE = T("Finished files are saved as: 0001 - Artist - Album - Track.")
QUALITY_NOTE = T("Only FLAC and MP3 are used. FLAC 16/44.1 is preferred; higher only if it\u2019s the only FLAC. "
                 "MP3 320 is preferred; V0 only if there\u2019s no 320. V1, V2, 256 and 192 ask for your OK first.")

SESSION_EXT = ".slsk"


def open_folder(path):
    try:
        if os.name == "nt":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        pass


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        load_fonts()
        self._set_icon()
        self.geometry("1120x790")
        self.minsize(1020, 760)
        self.configure(bg=BG)
        self.cfg = settings.load()
        self.msgs = queue.Queue()
        self.engine = None
        self.busy = False
        self.mode = "convert"
        self.session_file = None
        self.saved_done, self.saved_skipped = [], []
        self.slskd = Slskd(settings.DATA_DIR, log=self._log)
        self._last_full = self._last_autosave = 0
        self._style()
        self._build()
        self._build_menu()
        self._update_title()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(400, self._tick)
        self._cycle()

    # ---------- helpers ----------
    def _set_icon(self, win=None):
        win = win or self
        try:
            if os.name == "nt":
                win.iconbitmap(settings.resource_path("icon.ico"))
            else:
                self._icon_img = getattr(self, "_icon_img", None) or tk.PhotoImage(file=settings.resource_path("icon.png"))
                win.iconphoto(True, self._icon_img)
        except Exception:
            pass

    def _cycle(self):
        """Start button colour: 13 stops, 1 s fade between each, forever."""
        t = time.time() % len(CYCLE_RGB)
        i = int(t)
        f = t - i
        a, b = CYCLE_RGB[i], CYCLE_RGB[(i + 1) % len(CYCLE_RGB)]
        col = "#%02x%02x%02x" % tuple(round(a[k] + (b[k] - a[k]) * f) for k in range(3))
        try:
            self.start_btn.set_fill(col)
        except Exception:
            pass
        self.after(40, self._cycle)

    def _log(self, msg):
        try:
            settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
            with open(settings.DATA_DIR / "app.log", "a", encoding="utf-8") as f:
                f.write(time.strftime("%H:%M:%S ") + str(msg) + "\n")
        except Exception:
            pass

    def _style(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure("Treeview", background=WHITE, fieldbackground=WHITE, foreground=BLACK,
                    rowheight=28, borderwidth=0, font=F(10))
        s.configure("Treeview.Heading", background=BLACK, foreground=WHITE, relief="flat",
                    borderwidth=1, bordercolor=BLACK, lightcolor=BLACK, darkcolor=BLACK, font=F(9, "bold"))
        s.map("Treeview.Heading", background=[("active", BLACK)], foreground=[("active", WHITE)])
        s.map("Treeview", background=[("selected", SELECT_ROW)], foreground=[("selected", BLACK)])
        s.configure("TCombobox", fieldbackground=WHITE, background=WHITE, foreground=BLACK,
                    arrowcolor=BLACK, bordercolor=BLACK, lightcolor=WHITE, darkcolor=WHITE,
                    selectbackground=WHITE, selectforeground=BLACK)
        s.map("TCombobox", fieldbackground=[("readonly", WHITE)], foreground=[("readonly", BLACK)],
              background=[("readonly", WHITE), ("active", WHITE)], selectbackground=[("readonly", WHITE)],
              selectforeground=[("readonly", BLACK)])
        s.configure("Horizontal.TProgressbar", troughcolor=WHITE, background=RED,
                    bordercolor=BLACK, lightcolor=RED, darkcolor=RED)
        s.configure("Vertical.TScrollbar", background=WHITE, troughcolor=BLACK, bordercolor=BLACK,
                    arrowcolor=BLACK, lightcolor=WHITE, darkcolor=WHITE)
        self.option_add("*TCombobox*Listbox.background", WHITE)
        self.option_add("*TCombobox*Listbox.foreground", BLACK)
        self.option_add("*TCombobox*Listbox.selectBackground", YELLOW)
        self.option_add("*TCombobox*Listbox.selectForeground", BLACK)
        self.option_add("*TCombobox*Listbox.font", "{%s} 10" % FAMILY)

    def _label(self, parent, text, muted=True, size=9, bold=False, bg=BG, fg=WHITE, **kw):
        return tk.Label(parent, text=text, bg=bg, fg=fg, font=F(size, "bold" if bold else "normal"),
                        anchor="w", **kw)

    def _heading(self, parent, text):
        return self._label(parent, text, size=9, bold=True)

    def _button(self, parent, text, cmd, accent=False, fill=YELLOW, state="normal", bg=BG, **kw):
        return FlatButton(parent, text, cmd, fill=fill, bold=accent, state=state, bg=bg, **kw)

    def _update_title(self):
        name = " - " + Path(self.session_file).name if self.session_file else ""
        self.title(TITLE + name)
        if hasattr(self, "title_lbl"):
            self.title_lbl.configure(text=TITLE + name)

    def _language(self):
        win = tk.Toplevel(self)
        win.title(T("Language"))
        self._set_icon(win)
        win.configure(bg=BG)
        win.resizable(False, False)
        win.transient(self)
        w, h = 460, 210
        x = self.winfo_rootx() + (self.winfo_width() - w) // 2
        y = self.winfo_rooty() + (self.winfo_height() - h) // 2
        win.geometry("%dx%d+%d+%d" % (w, h, max(0, x), max(0, y)))
        msg = tk.Label(win, text=T("Changing the language requires restarting the app."), bg=BG, fg=WHITE,
                       font=F(10), wraplength=400, justify="center")
        msg.pack(pady=(30, 20))
        row = tk.Frame(win, bg=BG)
        row.pack(fill="x", padx=30)
        btns = {}

        def pick(code):
            if code == i18n.LANG:
                return
            self.cfg["lang"] = code
            settings.save(self.cfg)
            msg.configure(text=T("Saved. Close the app and open it again to apply the new language."))
            for c, b in btns.items():
                b.configure(state="disabled")

        for code, name in (("en", "English"), ("es", "Espa\u00f1ol")):
            b = self._button(row, name, lambda c=code: pick(c), state="disabled" if code == i18n.LANG else "normal")
            b.pack(side="left", fill="x", expand=True, padx=6)
            btns[code] = b
        self._button(win, T("OK"), win.destroy).pack(pady=22)
        win.bind("<Escape>", lambda e: win.destroy())
        win.grab_set()
        win.focus_set()

    def _about(self):
        win = tk.Toplevel(self)
        win.title(T("About"))
        self._set_icon(win)
        win.configure(bg=BG)
        win.resizable(False, False)
        win.transient(self)
        w, h = 460, 250
        x = self.winfo_rootx() + (self.winfo_width() - w) // 2
        y = self.winfo_rooty() + (self.winfo_height() - h) // 2
        win.geometry("%dx%d+%d+%d" % (w, h, max(0, x), max(0, y)))
        box = tk.Frame(win, bg=BG, highlightthickness=0)
        box.pack(fill="both", expand=True, padx=14, pady=(14, 0))
        tk.Label(box, text=TITLE, bg=BG, fg=WHITE, font=F(13, "bold"),
                 wraplength=420, justify="center").pack(pady=(30, 14))
        tk.Label(box, text=T("vibe coded by jc"), bg=BG, fg=WHITE, font=F(10)).pack()
        tk.Label(box, text="MALIGNA 2026", bg=BG, fg=WHITE, font=F(10, "bold")).pack(pady=(6, 6))
        link = tk.Label(box, text="http://maligna.net", bg=BG, fg=WHITE, cursor="hand2",
                        font=F(10, "underline"))
        link.pack()
        link.bind("<Button-1>", lambda e: webbrowser.open("http://maligna.net"))
        self._button(win, T("OK"), win.destroy).pack(pady=12)
        win.bind("<Escape>", lambda e: win.destroy())
        win.bind("<Return>", lambda e: win.destroy())
        win.grab_set()
        win.focus_set()

    # ---------- layout ----------
    def _build_menu(self):
        bar = tk.Menu(self, tearoff=0)
        m = tk.Menu(bar, tearoff=0)
        m.add_command(label=T("New session"), accelerator="Ctrl+N", command=self._menu_new)
        m.add_separator()
        m.add_command(label=T("Open session\u2026"), accelerator="Ctrl+O", command=self._menu_open)
        m.add_command(label=T("Save session"), accelerator="Ctrl+S", command=self._menu_save)
        m.add_command(label=T("Save session as\u2026"), command=self._menu_save_as)
        m.add_separator()
        m.add_command(label=T("Language") + "\u2026", command=self._language)
        bar.add_cascade(label=T("File"), menu=m)
        am = tk.Menu(bar, tearoff=0)
        am.add_command(label=T("About\u2026"), command=self._about)
        bar.add_cascade(label=T("About"), menu=am)
        self.config(menu=bar)
        self.bind_all("<Control-s>", lambda e: self._menu_save())
        self.bind_all("<Control-o>", lambda e: self._menu_open())
        self.bind_all("<Control-n>", lambda e: self._menu_new())
        self.src.bind("<Control-o>", lambda e: (self._menu_open(), "break")[1])

    def _textured(self, parent, **kw):
        """A frame showing the noise texture."""
        f = tk.Frame(parent, bg=BG, **kw)
        if self._bg_img is not None:
            lbl = tk.Label(f, image=self._bg_img, bd=0, highlightthickness=0)
            lbl.place(x=0, y=0)
            lbl.lower()
        return f

    def _load_texture(self):
        self._bg_img = None
        try:
            tile = tk.PhotoImage(file=settings.resource_path("bg_tile.png"))
            tw, th = tile.width(), tile.height()
            big = tk.PhotoImage(width=tw * 4, height=th * 3)
            for i in range(4):
                for j in range(3):
                    big.tk.call(big, "copy", tile, "-to", i * tw, j * th)
            self._bg_tile, self._bg_img = tile, big
        except Exception:
            pass

    def _build(self):
        self._load_texture()
        header = tk.Frame(self, bg=RED, height=40, highlightthickness=0)
        header.pack(fill="x")
        header.pack_propagate(False)
        self.title_lbl = tk.Label(header, text=TITLE, bg=RED, fg=BLACK, font=F(11, "bold"))
        self.title_lbl.pack(side="left", padx=16)
        self._button(header, T("Soulseek login"), self._open_login, fill=RED, outline=BLACK, bg=RED).pack(side="right", padx=12, pady=6)
        self.conn_lbl = tk.Label(header, text="", bg=RED, fg=BLACK, font=F(9))
        self.conn_lbl.pack(side="right", padx=6)
        tk.Frame(self, bg=BLACK, height=1).pack(fill="x")

        body = self._textured(self)
        body.pack(fill="both", expand=True)
        left = self._textured(body, width=426)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        tk.Frame(body, bg=BLACK, width=1).pack(side="left", fill="y")
        right = self._textured(body)
        right.pack(side="left", fill="both", expand=True)
        self._build_left(left)
        panel = tk.Frame(right, bg=BG)
        panel.pack(fill="both", expand=True, padx=8, pady=8)
        self._build_right(panel)

    def _build_left(self, p):
        pad = {"padx": 24}
        pa = tk.Frame(p, bg=BG)
        pa.pack(fill="x", padx=8, pady=(8, 0))
        self._heading(pa, T("1. WHAT TO DOWNLOAD")).pack(fill="x", pady=(12, 6), **pad)
        tabs = tk.Frame(pa, bg=BG)
        tabs.pack(fill="x", **pad)
        self.tab_convert = FlatButton(tabs, T("Convert playlist"), lambda: self._set_mode("convert"))
        self.tab_list = FlatButton(tabs, T("Song list"), lambda: self._set_mode("list"))
        self.tab_convert.pack(side="left", fill="x", expand=True)
        self.tab_list.pack(side="left", fill="x", expand=True)

        self.src_area = tk.Frame(pa, bg=BG, height=232)
        self.src_area.pack(fill="x", pady=(8, 10), **pad)
        self.src_area.pack_propagate(False)

        # -- Convert playlist tab --
        cf = self.convert_frame = tk.Frame(self.src_area, bg=BG)
        self._label(cf, T("Turn any playlist into text with TuneMyMusic"), size=10, bold=True).pack(fill="x")
        self._button(cf, T("Open TuneMyMusic"), lambda: webbrowser.open(TUNE_URL)).pack(anchor="w", pady=(4, 3))
        for i, text in enumerate(STEPS, 1):
            row = tk.Frame(cf, bg=BG)
            row.pack(fill="x", pady=0)
            tk.Label(row, text="%d." % i, bg=BG, fg=WHITE, width=2, anchor="ne", font=F(10)).pack(side="left", anchor="n")
            tk.Label(row, text=text, bg=BG, fg=WHITE, anchor="w", justify="left", wraplength=330,
                     font=F(10)).pack(side="left", fill="x")
        row = tk.Frame(cf, bg=BG)
        row.pack(fill="x", pady=1)
        tk.Label(row, text="5.", bg=BG, fg=WHITE, width=2, anchor="ne", font=F(10)).pack(side="left", anchor="n")
        tk.Label(row, text=T("Copy the contents of your text file"), bg=BG, fg=WHITE,
                 font=F(10)).pack(side="left")
        link = tk.Label(row, text=T(" here"), bg=BG, fg=WHITE, cursor="hand2",
                        font=F(10, "bold underline"))
        link.pack(side="left")
        link.bind("<Button-1>", lambda e: self._go_to_song_list())
        self._label(cf, T("\u201chere\u201d takes you to the Song list tab. Paste with Ctrl+V."),
                    wraplength=350, justify="left").pack(fill="x", pady=(2, 0))

        # -- Song list tab --
        lf = self.list_frame = tk.Frame(self.src_area, bg=BG)
        self.src_hint = self._label(lf, T("Paste your songs, one per line, as Artist - Title"), muted=False)
        self.src_hint.pack(fill="x", pady=(0, 4))
        bottom = tk.Frame(lf, bg=BG)
        bottom.pack(side="bottom", fill="x", pady=(4, 0))
        self._label(bottom, T("No limit on length.")).pack(side="left")
        self._button(bottom, T("Swap Artist / Title"), self._swap).pack(side="right")
        self.src = tk.Text(lf, bg=FIELD, fg=FG, insertbackground=FG, relief="flat", wrap="word", height=5,
                           highlightthickness=1, highlightbackground=BLACK, highlightcolor=BLACK,
                           font=F(10), padx=8, pady=6, undo=True)
        self.src.pack(fill="both", expand=True)
        self.src.bind("<Control-a>", lambda e: (self.src.tag_add("sel", "1.0", "end"), "break")[1])
        self.src.bind("<<Paste>>", self._on_paste)
        self._ctx = tk.Menu(self.src, tearoff=0)
        self._ctx.add_command(label=T("Cut"), command=lambda: self.src.event_generate("<<Cut>>"))
        self._ctx.add_command(label=T("Copy"), command=lambda: self.src.event_generate("<<Copy>>"))
        self._ctx.add_command(label=T("Paste"), command=self._on_paste)
        self._ctx.add_separator()
        self._ctx.add_command(label=T("Select all"), command=lambda: self.src.tag_add("sel", "1.0", "end"))
        self.src.bind("<Button-3>", self._show_ctx)

        pb = tk.Frame(p, bg=BG)
        pb.pack(fill="x", padx=8, pady=(8, 0))
        self._heading(pb, T("2. SESSION NAME (REQUIRED)")).pack(fill="x", pady=(12, 6), **pad)
        row = tk.Frame(pb, bg=BG)
        row.pack(fill="x", **pad)
        self.session_var = tk.StringVar()
        self.session_var.trace_add("write", lambda *a: self._update_path())
        tk.Entry(row, textvariable=self.session_var, bg=FIELD, fg=FG, insertbackground=FG, relief="flat",
                 highlightthickness=1, highlightbackground=BLACK, highlightcolor=BLACK,
                 font=F(11)).pack(side="left", fill="x", expand=True, ipady=6)
        self._button(row, T("Browse\u2026"), self._browse).pack(side="left", padx=(8, 0))
        self.save_root = self.cfg.get("save_root") or str(Path(settings.documents_folder()) / "SLSK 2D HD")
        self.path_lbl = self._label(pb, "", wraplength=360, justify="left")
        self.path_lbl.pack(fill="x", pady=(4, 0), **pad)
        self._label(pb, NAME_NOTE, wraplength=360, justify="left").pack(fill="x", pady=(2, 0), **pad)

        self._heading(pb, T("3. QUALITY")).pack(fill="x", pady=(10, 6), **pad)
        self.quality_var = tk.StringVar(value=QUALITY_LABELS.get(self.cfg.get("quality"), QUALITY_LABELS["best"]))
        ttk.Combobox(pb, textvariable=self.quality_var, values=list(QUALITY_LABELS.values()),
                     state="readonly", font=F(10)).pack(fill="x", ipady=4, **pad)
        self._label(pb, QUALITY_NOTE, wraplength=360, justify="left").pack(fill="x", pady=(4, 10), **pad)

        self.start_btn = self._button(p, T("Start download"), self._start, accent=True, fill="#" + CYCLE[0], always_black=True)
        self.start_btn.pack(side="bottom", fill="x", padx=32, pady=(0, 20))
        self._set_mode("convert")
        self._update_path()

    def _build_right(self, p):
        pad = {"padx": 24}
        top = tk.Frame(p, bg=BG)
        top.pack(fill="x", pady=(18, 10), **pad)
        self.queue_lbl = self._heading(top, T("QUEUE"))
        self.queue_lbl.pack(side="left")
        spin = tk.Frame(top, bg=BG)
        spin.pack(side="right")
        self._label(spin, T("Max active downloads:"), size=10).pack(side="left", padx=(0, 8))
        self.max_var = tk.StringVar(value=str(self.cfg.get("max_active", 10)))
        self.max_var.trace_add("write", lambda *a: self._max_changed())
        sp = tk.Frame(spin, bg=BG)
        sp.pack(side="left")
        tk.Entry(sp, width=4, textvariable=self.max_var, bg=FIELD, fg=FG, insertbackground=FG, relief="flat",
                 highlightthickness=1, highlightbackground=BLACK, highlightcolor=BLACK, justify="center",
                 font=F(11)).grid(row=0, column=0, rowspan=2, sticky="ns", ipady=3)
        ArrowButton(sp, True, lambda: self._bump(1)).grid(row=0, column=1, sticky="nsew")
        ArrowButton(sp, False, lambda: self._bump(-1)).grid(row=1, column=1, sticky="nsew")
        sp.grid_rowconfigure((0, 1), weight=1)

        self.progress = ttk.Progressbar(p, maximum=100, style="Horizontal.TProgressbar")
        self.progress.pack(fill="x", **pad)
        self.summary = self._label(p, T("Nothing running yet."), size=10)
        self.summary.pack(fill="x", pady=(8, 8), **pad)

        box = tk.Frame(p, bg=FIELD, highlightthickness=0)
        box.pack(fill="both", expand=True, **pad)
        self.tree = ttk.Treeview(box, columns=("song", "detail", "status"), show="headings", selectmode="extended")
        for col, text, w, stretch in (("song", T("Song"), 200, False), ("detail", T("Details"), 260, True),
                                      ("status", T("Status"), 135, False)):
            self.tree.heading(col, text=text, anchor="w")
            self.tree.column(col, width=w, minwidth=110 if col == "status" else 150, stretch=stretch, anchor="w")
        sb = ttk.Scrollbar(box, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        for state, color in TAG_COLORS.items():
            self.tree.tag_configure(state, foreground=color)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._sel_changed())

        acts = tk.Frame(p, bg=BG)
        acts.pack(fill="x", pady=(10, 0), **pad)
        self.ok_btn = self._button(acts, T("Download anyway"), self._allow_low, state="disabled", fill=WHITE)
        self.ok_btn.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self.skip_btn = self._button(acts, T("Skip"), self._skip_low, state="disabled", fill=WHITE)
        self.skip_btn.pack(side="left", fill="x", expand=True, padx=4)
        self.again_btn = self._button(acts, T("Search again"), self._search_again, state="disabled", fill=WHITE)
        self.again_btn.pack(side="left", fill="x", expand=True, padx=(4, 0))
        bottom = tk.Frame(p, bg=BG)
        bottom.pack(fill="x", pady=(10, 24), **pad)
        self._button(bottom, T("Open session folder"), self._open_session_folder, fill=WHITE).pack(side="left", fill="x", expand=True, padx=(0, 4))
        self.stop_btn = self._button(bottom, T("Stop"), self._stop, state="disabled", fill=WHITE)
        self.stop_btn.pack(side="left", fill="x", expand=True, padx=(4, 0))

    # ---------- source tabs ----------
    def _set_mode(self, mode):
        self.mode = mode
        self.tab_convert.configure(fill=YELLOW if mode == "convert" else WHITE, bold=mode == "convert")
        self.tab_list.configure(fill=YELLOW if mode == "list" else WHITE, bold=mode == "list")
        self.convert_frame.pack_forget()
        self.list_frame.pack_forget()
        (self.convert_frame if mode == "convert" else self.list_frame).pack(fill="both", expand=True)

    def _go_to_song_list(self):
        self._set_mode("list")
        self.src.focus_set()

    def _show_ctx(self, event):
        self.src.focus_set()
        try:
            self._ctx.tk_popup(event.x_root, event.y_root)
        finally:
            self._ctx.grab_release()

    def _on_paste(self, event=None):
        """Normal paste, but turns a pasted CSV export into 'Artist - Title' lines."""
        try:
            raw = self.clipboard_get()
        except tk.TclError:
            return "break"
        try:
            raw = matching.import_text(raw)
        except Exception:
            pass
        try:
            self.src.delete("sel.first", "sel.last")
        except tk.TclError:
            pass
        self.src.insert("insert", raw)
        return "break"

    def _swap(self):
        text = self.src.get("1.0", "end").strip()
        if text:
            self.src.delete("1.0", "end")
            self.src.insert("1.0", matching.swap_lines(text))

    # ---------- small actions ----------
    def _session_path(self):
        name = self.session_var.get().strip()
        return str(Path(self.save_root) / matching.sanitize(name, 60)) if name else ""

    def _update_path(self):
        shown = self._session_path() or str(Path(self.save_root) / T("<session name>"))
        self.path_lbl.configure(text=T("Saves to: ") + shown)

    def _browse(self):
        d = filedialog.askdirectory(initialdir=self.save_root, title=T("Where should the session folder be created?"))
        if d:
            self.save_root = os.path.normpath(d)
            self.cfg["save_root"] = self.save_root
            settings.save(self.cfg)
            self._update_path()

    def _bump(self, d):
        try:
            v = int(self.max_var.get())
        except ValueError:
            v = int(self.cfg.get("max_active", 10))
        self.max_var.set(str(max(1, min(200, v + d))))

    def _max_changed(self):
        try:
            v = max(1, min(200, int(self.max_var.get())))
        except ValueError:
            return
        self.cfg["max_active"] = v
        if self.engine:
            self.engine.max_active = v

    def _selected_tracks(self, state=None):
        if not self.engine:
            return []
        out = []
        for iid in self.tree.selection():
            t = self.engine.by_idx.get(int(iid))
            if t and (state is None or t.state == state):
                out.append(t)
        return out

    def _sel_changed(self):
        low = "normal" if self._selected_tracks(eng.NEEDS_OK) else "disabled"
        self.ok_btn.configure(state=low)
        self.skip_btn.configure(state=low)
        again = self._selected_tracks(eng.NOT_FOUND) or self._selected_tracks(eng.NEEDS_OK)
        self.again_btn.configure(state="normal" if again else "disabled")

    def _allow_low(self):
        for t in self._selected_tracks(eng.NEEDS_OK):
            self.engine.allow_low_quality(t)
        self._sel_changed()

    def _skip_low(self):
        for t in self._selected_tracks(eng.NEEDS_OK):
            self.engine.skip(t)
        self._sel_changed()

    def _search_again(self):
        for t in self._selected_tracks(eng.NOT_FOUND) + self._selected_tracks(eng.NEEDS_OK):
            self.engine.search_again(t)
        self._sel_changed()

    def _open_session_folder(self):
        p = self._session_path()
        if p and os.path.isdir(p):
            open_folder(p)
        else:
            messagebox.showinfo(TITLE, T("The session folder doesn't exist yet. It's created when you start."))

    # ---------- Soulseek login dialog ----------
    def _open_login(self, message=None):
        win = tk.Toplevel(self)
        win.title(T("Soulseek login"))
        self._set_icon(win)
        win.configure(bg=BG)
        win.transient(self)
        win.grab_set()
        win.geometry("460x300")

        def field(label, key, show=None, note=None):
            self._heading(win, label).pack(fill="x", padx=24, pady=(14, 4))
            var = tk.StringVar(value=self.cfg.get(key, ""))
            tk.Entry(win, textvariable=var, show=show, bg=FIELD, fg=FG, insertbackground=FG, relief="flat",
                     highlightthickness=1, highlightbackground=BLACK, highlightcolor=BLACK,
                     font=F(11)).pack(fill="x", padx=24, ipady=5)
            if note:
                self._label(win, note, wraplength=410, justify="left").pack(fill="x", padx=24, pady=(3, 0))
            return var

        if message:
            self._label(win, message, wraplength=410, justify="left").pack(fill="x", padx=24, pady=(16, 0))
        u = field(T("SOULSEEK USERNAME"), "slsk_user",
                  note=T("No sign-up needed: a new name is created the first time you log in."))
        pw = field(T("SOULSEEK PASSWORD"), "slsk_pass", show="*")

        def save():
            self.cfg["slsk_user"], self.cfg["slsk_pass"] = u.get().strip(), pw.get()
            settings.save(self.cfg)
            win.destroy()

        self._button(win, T("Save"), save, accent=True).pack(side="bottom", fill="x", padx=24, pady=20)
        self.wait_window(win)

    # ---------- session files (.slsk, plain JSON) ----------
    def _session_data(self):
        done, skipped = list(self.saved_done), list(self.saved_skipped)
        if self.engine:
            with self.engine.lock:
                done = [{"idx": t.idx, "title": t.title, "saved_as": t.saved_as, "label": t.label}
                        for t in self.engine.tracks if t.state == eng.DONE]
                skipped = [t.idx for t in self.engine.tracks if t.state == eng.SKIPPED]
        return {
            "app": "slsk-remake", "version": 1,
            "session_name": self.session_var.get().strip(), "save_root": self.save_root,
            "quality": "boomer" if self.quality_var.get() == QUALITY_LABELS["boomer"] else "best",
            "max_active": int(self.cfg.get("max_active", 10)),
            "songs": self.src.get("1.0", "end").strip(), "done": done, "skipped": skipped,
        }

    def _write_session(self, path, quiet=False):
        try:
            Path(path).write_text(json.dumps(self._session_data(), indent=1, ensure_ascii=False), encoding="utf-8")
            return True
        except Exception as e:
            self._log("session save error: %r" % (e,))
            if not quiet:
                messagebox.showerror(TITLE, T("Couldn't save the session: %s") % e)
            return False

    def _menu_new(self):
        if self.busy:
            if not messagebox.askyesno(TITLE, T("Downloads are still running. Stop them and start a new session?")):
                return
            self._stop()
        elif self.engine or self.src.get("1.0", "end").strip() or self.session_var.get().strip():
            if not messagebox.askyesno(TITLE, T("Start a new session? Unsaved changes to this one will be lost (use File > Save session first to keep it).")):
                return
        self.engine = None
        self.session_file = None
        self.saved_done, self.saved_skipped = [], []
        self.tree.delete(*self.tree.get_children())
        self.src.delete("1.0", "end")
        self.session_var.set("")
        self.queue_lbl.configure(text=T("QUEUE"))
        self.summary.configure(text=T("Nothing running yet."))
        self.progress["value"] = 0
        self.conn_lbl.configure(text="")
        self.start_btn.configure(state="normal", text=T("Start download"))
        self._sel_changed()
        self._set_mode("convert")
        self._update_title()

    def _menu_save_as(self):
        name = matching.sanitize(self.session_var.get().strip() or "My session", 60)
        path = filedialog.asksaveasfilename(
            title=T("Save session"), defaultextension=SESSION_EXT, initialdir=self.save_root,
            initialfile=name + SESSION_EXT, filetypes=[(T("SLSK session"), "*" + SESSION_EXT), (T("All files"), "*.*")])
        if path and self._write_session(path):
            self.session_file = path
            self._update_title()

    def _menu_save(self):
        if self.session_file:
            self._write_session(self.session_file)
        else:
            self._menu_save_as()

    def _menu_open(self):
        if self.busy:
            return messagebox.showinfo(TITLE, T("Press Stop first, then open a session."))
        path = filedialog.askopenfilename(
            title=T("Open session"), initialdir=self.save_root,
            filetypes=[(T("SLSK session"), "*" + SESSION_EXT), (T("All files"), "*.*")])
        if not path:
            return
        try:
            d = json.loads(Path(path).read_text(encoding="utf-8"))
            if d.get("app") != "slsk-remake":
                raise ValueError(T("That isn't a session file from this app."))
        except Exception as e:
            return messagebox.showerror(TITLE, T("Couldn't open that file: %s") % e)
        self.session_var.set(d.get("session_name", ""))
        self.save_root = d.get("save_root") or self.save_root
        self.quality_var.set(QUALITY_LABELS.get(d.get("quality"), QUALITY_LABELS["best"]))
        self.max_var.set(str(d.get("max_active", 10)))
        self._set_mode("list")
        self.src.delete("1.0", "end")
        self.src.insert("1.0", d.get("songs", ""))
        self.saved_done, self.saved_skipped = d.get("done", []), d.get("skipped", [])
        self.session_file = path
        self._update_path()
        self._update_title()
        tracks = self._tracks_from_text(d.get("songs", ""))
        eng.apply_saved(tracks, self.saved_done, self.saved_skipped, self._session_path())
        e = eng.Engine(self.slskd, self._session_path(), self.session_var.get().strip(), tracks)
        self._show_queue(e)
        self.conn_lbl.configure(text=T("Session loaded. Press Start to continue."))

    # ---------- start / stop ----------
    @staticmethod
    def _tracks_from_text(raw):
        try:
            raw = matching.import_text(raw)
        except Exception:
            pass
        out = []
        for i, (a, t) in enumerate(matching.parse_song_list(raw), 1):
            a = matching.clean_artist(a)
            out.append(eng.Track(idx=i, artists=[a] if a else [], title=t))
        return out

    def _start(self):
        if self.busy:
            return
        raw = self.src.get("1.0", "end").strip()
        if not raw:
            self._set_mode("convert")
            return messagebox.showinfo(TITLE, T("There are no songs yet. Follow the steps in Convert playlist, or paste songs into the Song list tab."))
        if not self.session_var.get().strip():
            return messagebox.showinfo(TITLE, T("Give this session a name first. It becomes the folder name."))
        if not self.cfg.get("slsk_user") or not self.cfg.get("slsk_pass"):
            self._open_login(T("Enter a Soulseek username and password first."))
            if not self.cfg.get("slsk_user") or not self.cfg.get("slsk_pass"):
                return
        self.cfg["quality"] = "boomer" if self.quality_var.get() == QUALITY_LABELS["boomer"] else "best"
        settings.save(self.cfg)
        self.busy = True
        self.start_btn.configure(state="disabled", text=T("Starting\u2026"))
        self.stop_btn.configure(state="normal")
        self.tree.delete(*self.tree.get_children())
        self.engine = None
        params = dict(text=raw, session=self.session_var.get().strip(),
                      session_dir=self._session_path(), quality=self.cfg["quality"])
        threading.Thread(target=self._prepare, args=(params,), daemon=True).start()

    def _post(self, kind, *args):
        self.msgs.put((kind, args))

    def _prepare(self, p):
        try:
            tracks = self._tracks_from_text(p["text"])
            if not tracks:
                raise RuntimeError(T("No songs were found in that."))
            if not self.slskd.installed():
                self._post("conn", T("First run: downloading the Soulseek engine\u2026"))
                self.slskd.ensure_installed(lambda d, t: self._post(
                    "conn", T("Downloading Soulseek engine: %d%%") % (100 * d // t if t else 0)))
            self._post("conn", T("Logging in to Soulseek\u2026"))
            self.slskd.start(self.cfg["slsk_user"], self.cfg["slsk_pass"])
            res = self.slskd.wait_logged_in(cancel=lambda: not self.busy)
            if res != "ok":
                raise RuntimeError(res)
            restored = eng.restore_progress(tracks, p["session_dir"])
            eng.apply_saved(tracks, self.saved_done, self.saved_skipped, p["session_dir"])
            e = eng.Engine(self.slskd, p["session_dir"], p["session"], tracks, mode=p["quality"],
                           max_active=int(self.cfg.get("max_active", 10)), log=self._log)
            self._post("ready", e, restored)
        except Exception as ex:
            self._log("prepare error: %r" % (ex,))
            self._post("error", str(ex))

    def _show_queue(self, e):
        self.engine = e
        self.tree.delete(*self.tree.get_children())
        for t in e.tracks:
            self.tree.insert("", "end", iid=str(t.idx), values=self._row(t), tags=(t.state,))
        self.queue_lbl.configure(text=T("QUEUE \u00b7 {:,} songs").format(len(e.tracks)))
        self._update_summary()

    def _stop(self):
        was = self.engine
        self.busy = False
        if was:
            threading.Thread(target=was.stop, daemon=True).start()
        self.stop_btn.configure(state="disabled")
        self.start_btn.configure(state="normal", text=T("Start download"))
        self.conn_lbl.configure(text=T("Stopped. Press Start to continue where you left off."))
        if self.session_file:
            self.after(1500, lambda: self._write_session(self.session_file, quiet=True))

    def _close(self):
        if self.engine and self.busy and not self.engine.finished():
            if not messagebox.askyesno(TITLE, T("Downloads are still running. Stop and close?\nYou can continue later with the same session name.")):
                return
        try:
            if self.session_file:
                self._write_session(self.session_file, quiet=True)
            if self.engine:
                self.engine.stop()
        finally:
            self.slskd.stop()
            self.destroy()

    # ---------- refresh loop ----------
    def _tick(self):
        try:
            while True:
                kind, args = self.msgs.get_nowait()
                self._handle(kind, *args)
        except queue.Empty:
            pass
        if self.engine:
            for idx in self.engine.pop_dirty():
                self._update_row(self.engine.by_idx[idx])
            now = time.time()
            if now - self._last_full > 15:
                self._last_full = now
                for t in self.engine.tracks:
                    if t.state in (eng.NOT_FOUND, eng.NEEDS_OK):
                        self._update_row(t)
            self._update_summary()
            if self.engine.notice:
                self.conn_lbl.configure(text=self.engine.notice)
                self._had_notice = True
            elif self.busy and getattr(self, "_had_notice", False):
                self._had_notice = False
                self.conn_lbl.configure(text=T("Soulseek: connected as ") + self.cfg["slsk_user"])
            if self.session_file and self.busy and now - self._last_autosave > 60:
                self._last_autosave = now
                self._write_session(self.session_file, quiet=True)
        self.after(400, self._tick)

    def _handle(self, kind, *args):
        if kind == "conn":
            self.conn_lbl.configure(text=args[0])
        elif kind == "error":
            self.busy = False
            self.start_btn.configure(state="normal", text=T("Start download"))
            self.stop_btn.configure(state="disabled")
            self.conn_lbl.configure(text="")
            messagebox.showerror(TITLE, args[0])
        elif kind == "ready":
            e, restored = args
            if not self.busy:
                return
            e.max_active = int(self.cfg.get("max_active", 10))
            self._show_queue(e)
            e.start()
            self.start_btn.configure(text=T("Running\u2026"))
            self.conn_lbl.configure(text=T("Soulseek: connected as ") + self.cfg["slsk_user"] +
                                    (T("  (%d already done)") % restored if restored else ""))

    @staticmethod
    def _row(t):
        return (t.display, eng.Engine.detail_text(t), eng.Engine.status_text(t))

    def _update_row(self, t):
        iid = str(t.idx)
        if self.tree.exists(iid):
            self.tree.item(iid, values=self._row(t), tags=(t.state,))

    def _update_summary(self):
        e = self.engine
        c = e.counts()
        total = len(e.tracks)
        active = c[eng.SEARCHING] + c[eng.DOWNLOADING]
        waiting = c[eng.QUEUED] + c[eng.PLACE]
        self.progress["value"] = 100.0 * c[eng.DONE] / max(1, total)
        parts = [T("{:,} done").format(c[eng.DONE]), T("%d active") % active, T("{:,} waiting in line").format(waiting),
                 T("%d not found") % c[eng.NOT_FOUND]]
        if c[eng.NEEDS_OK]:
            parts.append(T("%d need your OK") % c[eng.NEEDS_OK])
        self.summary.configure(text=" \u00b7 ".join(parts))
        if self.busy and e.finished():
            self.busy = False
            self.start_btn.configure(state="normal", text=T("Start download"))
            self.stop_btn.configure(state="disabled")
            self.conn_lbl.configure(text=T("All done."))

    def run(self):
        self.mainloop()
