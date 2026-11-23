"""资源路径解析：源码运行与 PyInstaller 单文件运行时都能找到 data / web / assets。

PyInstaller onefile 会把 --add-data 的内容解到 sys._MEIPASS；
可写目录（存档输出）始终取 exe 所在目录，绝不写进临时解包目录。
"""

import os
import sys


def frozen():
    return bool(getattr(sys, "frozen", False))


def bundle_root():
    """只读资源根目录（data / web / assets 都在它下面）。"""
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
    """exe 所在目录（打包后）；源码运行时为项目目录的上一级。"""
    if frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
