"""打包成 Windows 发行包（PyInstaller onedir + zip）。

用法：
    python build_exe.py            # 目录版 + zip（推荐，启动不再解包到临时目录）
    python build_exe.py --onefile  # 单个 exe（每次运行都会解包到 %TEMP%\_MEIxxxx）

产物：
    dist/MagiaSaveEditor/MagiaSaveEditor.exe   目录版主程序（同目录 _internal 是资源）
    dist/MagiaSaveEditor-<时间>.zip            直接分发的压缩包
"""

import datetime
import os
import shutil
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
NAME = "MagiaSaveEditor"


def zip_dir(folder, target):
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for root, _dirs, files in os.walk(folder):
            for name in files:
                full = os.path.join(root, name)
                archive.write(full, os.path.relpath(full, folder))
    return os.path.getsize(target)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    onefile = "--onefile" in argv
    argv = [item for item in argv if item != "--onefile"]
    if not any(a == "--add-data" for a in argv):
        for folder in ("web", "assets", "data"):
            argv += ["--add-data", "%s;%s" % (os.path.join(HERE, folder), folder)]
    command = [
        sys.executable, "-m", "PyInstaller",
        os.path.join(HERE, "launcher.py"),
        "--name", NAME,
        "--noconfirm",
        "--clean",
        "--console",
        "--distpath", os.path.join(HERE, "dist"),
        "--workpath", os.path.join(HERE, "build"),
        "--specpath", os.path.join(HERE, "build"),
        "--onefile" if onefile else "--onedir",
    ] + argv
    print("打包命令:", " ".join(command))
    subprocess.run(command, check=True, cwd=HERE)

    if onefile:
        exe = os.path.join(HERE, "dist", NAME + ".exe")
        if os.path.isfile(exe):
            print("完成: %s (%.1f MB)" % (exe, os.path.getsize(exe) / (1024.0 * 1024.0)))
        return 0

    folder = os.path.join(HERE, "dist", NAME)
    exe = os.path.join(folder, NAME + ".exe")
    if not os.path.isfile(exe):
        print("打包失败：找不到 %s" % exe)
        return 1
    total = 0
    for root, _dirs, files in os.walk(folder):
        for name in files:
            total += os.path.getsize(os.path.join(root, name))
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M")
    target = os.path.join(HERE, "dist", "%s-%s.zip" % (NAME, stamp))
    size = zip_dir(folder, target)
    print("完成: %s（目录 %.1f MB，exe 启动不解包）" % (exe, total / (1024.0 * 1024.0)))
    print("分发包: %s (%.1f MB)" % (target, size / (1024.0 * 1024.0)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
