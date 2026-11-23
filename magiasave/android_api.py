"""补丁：给 server.py 注入 Android 相关能力（由 tools/patch_android.py 应用或直接维护）。

为避免改动原文件的大段结构，这里用「给 Handler 挂方法」的方式扩展；
Handler.do_GET / do_POST 会在补丁里加两行分发。
"""

import os
import shutil
import time

from . import bridge, paths


def install(handler_cls):
    handler_cls.BRIDGE = bridge
    handler_cls.api_android = _api_android
    handler_cls.api_import = _api_import
    handler_cls.api_export_share = _api_export_share
    handler_cls.api_open_external = _api_open_external
    handler_cls.api_workspace = _api_workspace


def _api_android(self):
    """前端据此决定要不要显示「选择文件」按钮、要不要显示「导入/导出」。"""
    return {
        "ok": True,
        "android": bridge.available() or paths.android(),
        "bridge": bridge.available(),
        "workspace": paths.app_dir(),
        "inbox": _inbox(),
        "archive": os.environ.get("MAGIA_APP_DIR") or paths.app_dir(),
    }


def _inbox():
    """存放用户导入的存档 zip 的目录。"""
    path = os.path.join(paths.app_dir(), "saves")
    os.makedirs(path, exist_ok=True)
    return path


def _api_import(self, body):
    """把用户从系统文件选择器拿到的路径，拷进工作区，返回可打开的路径。

    Android 上 SAF 返回的 content:// 已由 Kotlin 侧落成缓存文件，这里只需拷贝。
    桌面不需要这个接口（直接填路径即可），但保留以便统一前端逻辑。
    """
    src = body.get("path")
    if not src or not os.path.isfile(src):
        return {"ok": False, "error": "文件不存在: %s" % src, "code": "import_missing"}
    name = os.path.basename(src.rstrip("/\\")) or ("save-%d.zip" % int(time.time()))
    if not name.lower().endswith(".zip"):
        name += ".zip"
    target = os.path.join(_inbox(), name)
    # 同名时加序号，绝不覆盖已有导入件。
    stem, ext = os.path.splitext(target)
    index = 1
    while os.path.exists(target):
        target = "%s-%d%s" % (stem, index, ext)
        index += 1
    shutil.copyfile(src, target)
    return {"ok": True, "path": target}


def _api_export_share(self, body):
    """把工作区里的文件交给 Android 分享面板（发群、发网盘、发自己）。"""
    path = body.get("path")
    if not path or not os.path.isfile(path):
        return {"ok": False, "error": "文件不存在: %s" % path, "code": "export_missing"}
    if not bridge.available():
        return {"ok": False, "error": "当前环境没有分享面板（桌面请直接用文件管理器）", "code": "no_bridge"}
    return {"ok": bool(bridge.share(path))}


def _api_open_external(self, body):
    path = body.get("path")
    if not path or not os.path.isfile(path):
        return {"ok": False, "error": "文件不存在: %s" % path, "code": "export_missing"}
    if not bridge.available():
        return {"ok": False, "error": "当前环境不能唤起外部应用", "code": "no_bridge"}
    return {"ok": bool(bridge.open_external(path))}


def _api_workspace(self):
    """返回工作区目录，以及里面已有的存档 zip（方便用户直接挑）。"""
    root = _inbox()
    rows = []
    try:
        for name in sorted(os.listdir(root)):
            if not name.lower().endswith(".zip"):
                continue
            full = os.path.join(root, name)
            stat = os.stat(full)
            rows.append({
                "name": name,
                "path": full,
                "bytes": stat.st_size,
                "mtime": int(stat.st_mtime),
            })
    except Exception:
        pass
    return {"ok": True, "dir": root, "rows": rows}
