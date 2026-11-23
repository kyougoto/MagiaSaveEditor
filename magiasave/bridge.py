"""Android 桥：把「选文件 / 保存到用户选的位置 / 分享」这类系统交互交回 Kotlin 侧。

设计上不 import 任何 Android 类，因此桌面/CI 环境下 import 本模块也不会崩。
调用链（Kotlin 侧 `AndroidBridge.kt`）：

    py_port = python.getModule("magiasave.android_main").callAttr(
        "start_in_thread", "127.0.0.1", 0, None, bridge)   # bridge 由这里 set_host
    bridge.pick(mode, suggest)        # 阻塞到用户选完，返回路径或 None
    bridge.commit_save(path)          # 「另存为」：把 outbox 文件推回用户选的 Uri
    bridge.share(path)                # 交给系统分享面板
    bridge.open_external(path)        # 用默认应用打开

之所以做成阻塞式，是因为 Python 的 HTTP handler 本来就是同步的：前端 fetch 一直挂着，
等 Kotlin 回调即可，整套逻辑不用改成异步。
"""

import threading

_HOST = None
_TIMEOUT = 300.0  # 用户在文件管理器里翻 5 分钟已经很久了


class BridgeTimeout(Exception):
    """用户迟迟不选，超时放弃。"""


def set_host(host):
    """注入宿主（Chaquo 里传 Kotlin 对象；测试里可传鸭子类型替身）。"""
    global _HOST
    _HOST = host


def host():
    return _HOST


def available():
    return _HOST is not None


def _call(method, *args):
    if _HOST is None:
        raise RuntimeError("Android 桥未安装")
    fn = getattr(_HOST, method, None)
    if fn is None:
        return None
    return fn(*args)


def pick(mode="open", suggest=None, initial=None):
    """mode: open / save。返回路径或 None（取消）。非 Android 环境返回 None。"""
    if _HOST is None:
        return None
    return _call("pickFile", mode or "open", suggest or "", initial or "")


def commit_save(path):
    """「另存为」写完存档后调用，把文件推回用户选的目标。非 Android 返回 False。"""
    if _HOST is None or not path:
        return False
    return bool(_call("commitSave", path))


def share(path):
    if _HOST is None or not path:
        return False
    return bool(_call("shareFile", path))


def open_external(path):
    """用系统默认应用打开（例如把编辑后的 zip 丢给压缩软件 / 网盘）。"""
    if _HOST is None or not path:
        return False
    return bool(_call("openFile", path))


def version():
    if _HOST is None:
        return None
    try:
        return _call("bridgeVersion")
    except Exception:
        return None


class Latch:
    """给 Kotlin 回调用的简单同步闩（测试或自定义宿主可用）。"""

    def __init__(self):
        self._event = threading.Event()
        self._value = None

    def set_result(self, value):
        self._value = value
        self._event.set()

    def wait(self, timeout=_TIMEOUT):
        if not self._event.wait(timeout):
            raise BridgeTimeout("等待系统对话框超时")
        return self._value