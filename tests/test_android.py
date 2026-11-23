"""Android 适配层的回归测试（不依赖真实存档样本）。

覆盖：
  1. paths 的环境变量覆盖（Android 上靠它找 bundle 与可写目录）
  2. bridge 未安装时 pick/available 的安全降级
  3. dialogs 在「无 tkinter 无 bridge」时返回 None，不抛异常
  4. android_api 的导入 / 工作区列举行为
  5. server.Handler 上确实挂上了新接口

跑法：python tests/test_android.py
"""

import os
import shutil
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from magiasave import android_api, bridge, dialogs, paths, server  # noqa: E402


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + ((" :: " + str(detail)) if detail else ""))
    if not ok:
        raise SystemExit(1)


class FakeHost:
    """模拟 Kotlin 侧的 AndroidBridge。"""

    def __init__(self, result):
        self.result = result
        self.calls = []

    def pickFile(self, mode, suggest, initial):
        self.calls.append((mode, suggest, initial))
        return self.result

    def shareFile(self, path):
        self.calls.append(("share", path))
        return True

    def openFile(self, path):
        self.calls.append(("open", path))
        return True

    def bridgeVersion(self):
        return "fake-1"


def main():
    tmp = tempfile.mkdtemp(prefix="magia-android-test-")
    try:
        # 1) paths 覆盖
        os.environ["MAGIA_BUNDLE_ROOT"] = os.path.join(tmp, "bundle")
        os.environ["MAGIA_APP_DIR"] = os.path.join(tmp, "appdir")
        check("paths.bundle_root 走环境变量", paths.bundle_root() == os.path.join(tmp, "bundle"))
        check("paths.data_dir 跟随 bundle", paths.data_dir().endswith("/bundle/data"))
        check("paths.app_dir 会自动创建", os.path.isdir(paths.app_dir()), paths.app_dir())
        os.environ["MAGIA_ANDROID"] = "1"
        check("paths.android 能识别", paths.android() is True)

        # 2) bridge 未安装时安全降级
        bridge.set_host(None)
        check("bridge.available 无宿主时为 False", bridge.available() is False)
        check("bridge.pick 无宿主时返回 None", bridge.pick() is None)
        check("bridge.share 无宿主时返回 False", bridge.share("/tmp/x") is False)

        # 3) dialogs 在无 tk 无 bridge 时返回 None
        os.environ.setdefault("DISPLAY", "")
        check("dialogs.pick 兜底返回 None", dialogs.pick("open") is None)

        # 4) 装一个假宿主，验证 pick 能拿到路径且被绝对化
        host = FakeHost(os.path.join(tmp, "from-saf.zip"))
        bridge.set_host(host)
        check("bridge.available 有宿主时为 True", bridge.available() is True)
        got = dialogs.pick("open", initial="", suggest="a.zip")
        check("dialogs.pick 走桥并返回绝对路径", got == os.path.abspath(os.path.join(tmp, "from-saf.zip")), got)
        check("桥收到了 mode/suggest", host.calls[0][0] == "open")
        check("bridge.share 转发成功", bridge.share(got) is True)

        # 5) android_api：导入 / 工作区
        fake_handler = type("H", (object,), {})()
        src = os.path.join(tmp, "sample-save.zip")
        with zipfile.ZipFile(src, "w") as zf:
            zf.writestr("manifest.json", "{}")
        res = android_api._api_import(fake_handler, {"path": src})
        check("导入成功", res.get("ok") is True, res)
        check("导入落在 saves/ 下", "/saves/" in res["path"], res["path"])
        res2 = android_api._api_import(fake_handler, {"path": src})
        check("同名导入不覆盖", res2["path"] != res["path"], res2["path"])
        ws = android_api._api_workspace(fake_handler)
        check("工作区列出 2 个 zip", len(ws["rows"]) == 2, len(ws["rows"]))
        check("工作区条目带字节数", all(r["bytes"] > 0 for r in ws["rows"]))

        # 6) Handler 挂载检查
        android_api.install(server.Handler)
        for name in ("api_android", "api_import", "api_export_share", "api_open_external", "api_workspace"):
            check("Handler.%s 已挂载" % name, hasattr(server.Handler, name))

        info = android_api._api_android(fake_handler)
        check("api_android 报告 android=True", info["android"] is True, info)
        check("api_android 给出 inbox", info["inbox"].endswith("/saves"), info["inbox"])

        bad = android_api._api_import(fake_handler, {"path": os.path.join(tmp, "nope.zip")})
        check("导入不存在的文件被拒绝", bad.get("ok") is False and bad.get("code") == "import_missing")

        print("\n全部通过")
    finally:
        for key in ("MAGIA_BUNDLE_ROOT", "MAGIA_APP_DIR", "MAGIA_ANDROID"):
            os.environ.pop(key, None)
        bridge.set_host(None)
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()