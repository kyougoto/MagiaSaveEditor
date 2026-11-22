"""打包成单个 Windows 可执行文件（PyInstaller onefile）。

用法：
    python build_exe.py

产物：dist/MagiaSaveEditor.exe（双击即启动服务并打开浏览器）。
data / web / assets 全部打进 exe，运行时解包到临时目录；写出的存档仍由用户指定路径。
"""

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
NAME = "MagiaSaveEditor"


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not any(a == "--add-data" for a in argv):
        for folder in ("web", "assets", "data"):
            argv += ["--add-data", "%s;%s" % (os.path.join(HERE, folder), folder)]
    command = [
        sys.executable, "-m", "PyInstaller",
        os.path.join(HERE, "launcher.py"),
        "--name", NAME,
        "--onefile",
        "--noconfirm",
        "--clean",
        "--console",
        "--distpath", os.path.join(HERE, "dist"),
        "--workpath", os.path.join(HERE, "build"),
        "--specpath", os.path.join(HERE, "build"),
    ] + argv
    print("打包命令:", " ".join(command))
    subprocess.run(command, check=True, cwd=HERE)
    exe = os.path.join(HERE, "dist", NAME + ".exe")
    if os.path.isfile(exe):
        size = os.path.getsize(exe) / (1024.0 * 1024.0)
        print("完成: %s (%.1f MB)" % (exe, size))
    return 0


if __name__ == "__main__":
    sys.exit(main())
