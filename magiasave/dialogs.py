"""原生文件对话框（tkinter）。

只在本机使用：网页里点「浏览…」时由服务端弹窗，返回绝对路径。
tkinter 不可用时返回 None，前端退回手动输入路径。
"""

import os
import threading

_LOCK = threading.Lock()


def available():
    try:
        import tkinter  # noqa: F401
        from tkinter import filedialog  # noqa: F401
        return True
    except Exception:
        return False


def pick(mode="open", initial=None, suggest=None):
    """mode: open / save。返回绝对路径或 None（用户取消 / 无 tkinter）。"""
    if not available():
        return None
    import tkinter as tk
    from tkinter import filedialog

    start_dir = os.path.dirname(initial) if initial else None
    if start_dir and not os.path.isdir(start_dir):
        start_dir = None
    with _LOCK:
        root = tk.Tk()
        root.withdraw()
        try:
            root.attributes("-topmost", True)
        except Exception:
            pass
        try:
            if mode == "save":
                path = filedialog.asksaveasfilename(
                    title="另存为新的存档 zip（不会覆盖原存档）",
                    defaultextension=".zip",
                    filetypes=[("存档 zip", "*.zip"), ("全部文件", "*.*")],
                    initialdir=start_dir,
                    initialfile=suggest or "",
                )
            else:
                path = filedialog.askopenfilename(
                    title="选择 MagiaOfflineSlotArchive/v1 存档 zip",
                    filetypes=[("存档 zip", "*.zip"), ("全部文件", "*.*")],
                    initialdir=start_dir,
                )
        finally:
            root.destroy()
    return os.path.abspath(path) if path else None
