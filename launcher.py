"""单文件启动器：拉起本地服务并打开浏览器。

源码运行：
    python launcher.py --archive "path/to/save.zip"

打包后（MagiaSaveEditor.exe）双击即可，端口自动选择空闲值。
"""

import argparse
import os
import sys
import threading
import webbrowser
from http.server import ThreadingHTTPServer

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from magiasave import paths, server as server_mod  # noqa: E402


def main(argv=None):
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass
    parser = argparse.ArgumentParser(description="Magia☆Record 离线存档编辑器")
    parser.add_argument("--archive", help="启动时打开的存档 zip")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址（默认只本机）")
    parser.add_argument("--port", type=int, default=0, help="端口，0 = 自动挑空闲端口")
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    args = parser.parse_args(argv)

    session = server_mod.Session(args.archive)
    server_mod.Handler.session = session
    httpd = ThreadingHTTPServer((args.host, args.port), server_mod.Handler)
    port = httpd.server_address[1]
    url = "http://%s:%d/" % (args.host, port)

    print("Magia☆Record 存档编辑器")
    print("  界面地址: %s" % url)
    if args.archive:
        print("  已打开存档: %s" % args.archive)
    else:
        print("  未指定存档：在网页里填入 zip 路径，或点「浏览…」选择。")
    print("  资源目录: %s" % paths.bundle_root())
    print("  输出目录建议: %s" % paths.app_dir())
    print("  关闭这个窗口即退出。")

    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        print("已停止。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
