"""Small cross-thread dialogs without creating Tk on Windows."""

import platform

from src.tk_runtime import exclusive_tk_root


def _messagebox_win32(title, message, flags):
    import ctypes

    MB_TOPMOST = 0x00040000
    MB_SETFOREGROUND = 0x00010000
    return ctypes.windll.user32.MessageBoxW(
        None,
        str(message or ""),
        str(title or "Vox AI Input"),
        flags | MB_TOPMOST | MB_SETFOREGROUND,
    )


def _messagebox_tk(kind, title, message):
    import tkinter as tk
    from tkinter import messagebox

    with exclusive_tk_root("dialog"):
        root = tk.Tk()
        root.withdraw()
        try:
            if kind == "ask_yes_no":
                return messagebox.askyesno(title, message, parent=root)
            if kind == "error":
                messagebox.showerror(title, message, parent=root)
                return None
            messagebox.showinfo(title, message, parent=root)
            return None
        finally:
            root.destroy()


def show_info(title, message):
    """Show an informational dialog."""
    if platform.system() == "Windows":
        _messagebox_win32(title, message, 0x00000040)
        return
    _messagebox_tk("info", title, message)


def show_error(title, message):
    """Show an error dialog."""
    if platform.system() == "Windows":
        _messagebox_win32(title, message, 0x00000010)
        return
    _messagebox_tk("error", title, message)


def ask_yes_no(title, message):
    """Return True when the user chooses Yes."""
    if platform.system() == "Windows":
        IDYES = 6
        return _messagebox_win32(title, message, 0x00000004 | 0x00000020) == IDYES
    return bool(_messagebox_tk("ask_yes_no", title, message))
