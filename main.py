import os
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
if not getattr(sys, "frozen", False):
    os.chdir(HERE)
    sys.path.insert(0, str(HERE))


def main():
    try:
        if os.name == "nt":
            import ctypes
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except Exception:
                pass
        from gui import App
        App().run()
    except Exception:
        text = traceback.format_exc()
        try:
            import settings
            settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
            (settings.DATA_DIR / "error.log").write_text(text, encoding="utf-8")
        except Exception:
            pass
        try:
            import tkinter
            from tkinter import messagebox
            r = tkinter.Tk()
            r.withdraw()
            messagebox.showerror("Something went wrong", text[-1500:])
        except Exception:
            pass


if __name__ == "__main__":
    main()
