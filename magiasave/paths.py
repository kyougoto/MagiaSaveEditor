"""资源路径解析：源码运行、PyInstaller 单文件、Android（Chaquo）打包都能找到 data / web / assets。

三种运行方式：

1. 源码运行：资源就在项目目录下，直接读。
2. PyInstaller onefile：`--add-data` 的内容解到 `sys._MEIPASS`，可写目录取 exe 所在目录。
3. Android（Chaquo for Python）：APK 内的资源不能当普通文件读，因此由宿主 Activity 在
   首次启动时把 `assets/bundle/{data,web,assets}` 解压到 `filesDir/bundle`，再通过环境变量
   `MAGIA_BUNDLE_ROOT` 告诉这里去哪找（见 `android/app/src/main/java/.../BundleInstaller.kt`）。

环境变量（Android 部署时由 Kotlin 侧注入，桌面版一律不设）：

| 变量 | 含义 |
|---|---|
| `MAGIA_BUNDLE_ROOT` | 只读资源根目录（其下有 data / web / assets） |
| `MAGIA_APP_DIR`    | 可写目录（存档输出、日志） |
| `MAGIA_ANDROID`    | 值为 1 表示运行在 Android 上 |
"""

import os
import sys


def frozen():
    return bool(getattr(sys, "frozen", False))


def android():
    """是否运行在 Android（Chaquo）上。"""
    return os.environ.get("MAGIA_ANDROID") == "1"


def bundle_root():
    """只读资源根目录（data / web / assets 都在它下面）。"""
    override = os.environ.get("MAGIA_BUNDLE_ROOT")
    if override:
        return override
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return meipass
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def web_dir():
    return os.path.join(bundle_root(), "web")


def assets_dir():
    return os.path.join(bundle_root(), "assets")


def data_dir():
    return os.path.join(bundle_root(), "data")


def app_dir():
    """可写目录：Android 取宿主给的私有目录，打包后取 exe 所在目录，源码运行取项目目录。"""
    override = os.environ.get("MAGIA_APP_DIR")
    if override:
        os.makedirs(override, exist_ok=True)
        return override
    if frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
