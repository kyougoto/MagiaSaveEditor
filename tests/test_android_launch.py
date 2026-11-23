"""模拟安卓启动：走 magiasave.android_main.start_in_thread + 假 Kotlin 桥，全程 HTTP 验证。

这是能在桌面复现「安卓上到底会跑成什么样」的最接近的测试。
"""

import json
import os
import sys
import tempfile
import threading
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class FakeKotlinBridge:
    """模拟 AndroidBridge：pick 返回预置路径，commitSave / shareFile 记录调用。"""

    def __init__(self, open_path=None, save_path=None):
        self.open_path = open_path
        self.save_path = save_path
        self.calls = []

    def pickFile(self, mode, suggest, initial):
        self.calls.append(("pick", mode, suggest))
        return self.save_path if mode == "save" else self.open_path

    def commitSave(self, path):
        self.calls.append(("commitSave", path))
        return os.path.isfile(path)

    def shareFile(self, path):
        self.calls.append(("shareFile", path))
        return True

    def openFile(self, path):
        self.calls.append(("openFile", path))
        return True

    def bridgeVersion(self):
        return "test-1"


def http(port, path, body=None):
    url = "http://127.0.0.1:%d%s" % (port, path)
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.status, json.loads(response.read().decode())


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + ((" :: " + str(detail)) if detail else ""))
    if not ok:
        raise SystemExit(1)


def main():
    tmp = tempfile.mkdtemp(prefix="magia-android-launch-")
    app_dir = os.path.join(tmp, "workspace")
    os.makedirs(app_dir)

    # 模拟 Kotlin 侧设置的三个环境变量
    os.environ["MAGIA_BUNDLE_ROOT"] = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    os.environ["MAGIA_APP_DIR"] = app_dir
    os.environ["MAGIA_ANDROID"] = "1"

    from magiasave import android_main

    # 准备一份「用户选的存档」（内容随意，只为验证导入链路）
    picked = os.path.join(tmp, "user-picked.zip")
    with open(picked, "wb") as handle:
        handle.write(b"PK\x05\x06" + b"\x00" * 18)

    outbox = os.path.join(tmp, "outbox", "edited.zip")
    os.makedirs(os.path.dirname(outbox), exist_ok=True)
    bridge = FakeKotlinBridge(open_path=picked, save_path=outbox)

    port = android_main.start_in_thread("127.0.0.1", 0, None, bridge)
    check("start_in_thread 返回端口", isinstance(port, int) and port > 0, port)
    time.sleep(0.3)

    status, info = http(port, "/api/android")
    check("/api/android 是安卓模式", info["android"] is True, info)
    check("/api/android 认出桥", info["bridge"] is True, info)

    status, result = http(port, "/api/pick", {"mode": "open", "suggest": "", "initial": ""})
    check("/api/pick 走桥拿到路径", result["path"] == picked, result)
    check("桥收到 mode=open", bridge.calls[0][1] == "open", bridge.calls[:1])

    status, imported = http(port, "/api/import", {"path": result["path"]})
    check("/api/import 导入成功", imported["ok"] is True, imported)

    status, ws = http(port, "/api/workspace")
    check("/api/workspace 看到导入件", len(ws["rows"]) == 1, ws)

    status, shared = http(port, "/api/share", {"path": imported["path"]})
    check("/api/share 转发到桥", shared["ok"] is True, shared)
    check("桥收到 shareFile", any(c[0] == "shareFile" for c in bridge.calls), bridge.calls)

    # 桌面模式下的行为不应被破坏
    status, bad = http(port, "/api/import", {"path": "/nope/missing.zip"})
    check("/api/import 拒绝不存在的文件", bad["code"] == "import_missing", bad)

    print("\n安卓启动链路全部通过（端口 %d）" % port)


if __name__ == "__main__":
    main()