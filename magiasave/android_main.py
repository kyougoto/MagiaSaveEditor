"""给 Kotlin/Chaquo 用的启动入口。

桌面照旧用 `python -m magiasave.server` / `launcher.py`；安卓上由 MainActivity 调
`PythonRuntime.start()`，它再调 `start_in_thread()`。

返回实际监听的端口（传 0 时由系统挑空闲端口），失败的异常直接抛给 Kotlin。
"""

import threading
from http.server import ThreadingHTTPServer

from . import android_api, bridge, paths, server as server_mod


def bind(host="127.0.0.1", port=0, archive=None):
    """只建服务不阻塞，返回 (httpd, url)。"""
    session = server_mod.Session(archive)
    server_mod.Handler.session = session
    android_api.install(server_mod.Handler)
    httpd = ThreadingHTTPServer((host, port), server_mod.Handler)
    actual = httpd.server_address[1]
    return httpd, "http://%s:%d/" % (host, actual)


def start_in_thread(host="127.0.0.1", port=0, archive=None, py_host=None):
    """启动后台服务线程并返回端口号。py_host 是 Python 侧的 AndroidBridge 替身。

    返回 int 端口，方便 Kotlin 直接拼 URL。
    """
    if py_host is not None:
        bridge.set_host(py_host)
    httpd, url = bind(host, port, archive)

    thread = threading.Thread(target=httpd.serve_forever, name="magia-http", daemon=True)
    thread.start()
    print("magiasave: serving on %s (bundle=%s, app=%s)" % (url, paths.bundle_root(), paths.app_dir()))
    return httpd.server_address[1]