"""端到端：本地 Web 服务 + 全部关键 API，跑通一次真实编辑与落盘。"""

import json
import os
import sys
import threading
import urllib.request
from http.server import ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from magiasave.server import Handler, Session  # noqa: E402

SAMPLE = os.environ.get("MAGIA_SAMPLE", r"H:/magia_server/magia-save-chino-1794718180238.zip")
WORK = os.path.join(ROOT, "_work")
OUT = os.path.join(WORK, "server-out.zip")


def request(base_url, path, body=None):
    url = base_url + path
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def check(label, condition, detail=""):
    print(("PASS " if condition else "FAIL ") + label + ((" :: " + detail) if detail else ""))
    if not condition:
        raise SystemExit(1)


def main():
    os.makedirs(WORK, exist_ok=True)
    if os.path.exists(OUT):
        os.remove(OUT)
    Handler.session = Session(SAMPLE)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    base_url = "http://127.0.0.1:%d" % server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status = request(base_url, "/api/status")
        check("status 已打开存档", status["loaded"] is True)
        check("catalog 已装载", status["catalog"]["items"] > 1000, json.dumps(status["catalog"], ensure_ascii=False))

        overview = request(base_url, "/api/overview")
        check("overview 玩家名", overview["player"]["loginName"] == "chino", str(overview["player"]["loginName"]))
        check("overview 计数", overview["counts"]["quest"] > 0, json.dumps(overview["counts"], ensure_ascii=False))

        items = request(base_url, "/api/view/items?limit=5")
        check("道具视图带官方名称", items["rows"][0]["name"] not in ("", None), items["rows"][0]["name"])

        quests = request(base_url, "/api/view/quests?limit=3&only=uncleared")
        check("任务视图可分页筛选", len(quests["rows"]) <= 3)

        chars = request(base_url, "/api/view/charas?limit=3")
        check("角色视图", len(chars["rows"]) == 3, str(len(chars["rows"])))

        catalog = request(base_url, "/api/catalog/items?q=YELL")
        check("主数据搜索命中精确 ID", catalog["rows"] and catalog["rows"][0]["itemId"] == "YELL"
              and catalog["rows"][0]["name"] == "协助Pt",
              json.dumps(catalog["rows"][:2], ensure_ascii=False))

        # 视图契约冒烟：前后端结构错配会在这里先炸，而不是等到页面报 undefined
        views = {
            "/api/view/items?limit=3": ["rows", "total"],
            "/api/view/items-families": ["families"],
            "/api/view/items-groups?family=general": ["groups"],
            "/api/view/charas?limit=3": ["rows"],
            "/api/view/pieces?limit=3": ["rows"],
            "/api/view/pieces-catalog?limit=3": ["rows"],
            "/api/view/quests-tree": ["parts", "total"],
            "/api/view/sections-tree": ["parts"],
            "/api/view/chapters": ["rows"],
            "/api/view/challenges": ["groups"],
            "/api/view/gacha": ["kinds", "groups"],
            "/api/view/gifts": ["groups"],
            "/api/view/gifts-catalog": ["rows"],
            "/api/view/status": ["rows"],
        }
        for path, keys in views.items():
            payload = request(base_url, path)
            missing = [key for key in keys if payload.get(key) is None]
            check("视图契约 " + path.split("?")[0], not missing, "缺少 " + str(missing))

        tree = request(base_url, "/api/view/quests-tree")
        first_part = tree["parts"][0]
        first_chapter = first_part["chapters"][0]
        first_section = first_chapter["sections"][0]
        check("任务树字段", all(key in first_part for key in ("key", "label", "chapters", "chapterCount")),
              str(list(first_part.keys())))
        check("任务树章字段", all(key in first_chapter for key in ("key", "label", "sections", "sectionCount")),
              str(list(first_chapter.keys())))
        check("任务树话含任务数组", isinstance(first_section.get("quests"), list) and first_section["quests"],
              str(list(first_section.keys())))
        check("任务树不泄漏内部字段", not any(key.startswith("_") for key in first_section), str(list(first_section.keys())))

        first_card = request(base_url, "/api/view/charas?limit=1")["rows"][0]["userCardId"]
        detail = request(base_url, "/api/chara?userCardId=" + urllib.parse.quote(first_card))
        check("/api/chara 可用", detail.get("card") is not None and detail["icon"].startswith("/assets/cards/"),
              str(detail.get("icon")))

        raw = request(base_url, "/api/raw?path=" + urllib.parse.quote("state.gameUser.riche"))
        check("原始路径读取", isinstance(raw["value"], (int, float)), str(raw["value"]))

        edited = request(base_url, "/api/edit", {"ops": [
            {"op": "money.set", "kind": "MONEY", "value": 3000},
            {"op": "status.set", "statusId": "ACP", "point": 150, "maxPoint": 150},
        ]})
        check("编辑生效", len(edited["changed"]) >= 2, str(edited["changed"]))

        edited2 = request(base_url, "/api/edit", {"ops": [
            {"op": "raw.set", "path": "state.gameUser.comment", "value": "edited-by-magia-save-editor"}
        ]})
        check("raw 写入", edited2["changed"] == ["state.gameUser.comment"], str(edited2["changed"]))

        undo = request(base_url, "/api/undo", {})
        check("撤销可用", undo["ok"] is True)

        bad = None
        try:
            request(base_url, "/api/edit", {"ops": [{"op": "quest.set", "questBattleId": 999, "cleared": True}]})
        except urllib.error.HTTPError as exc:
            bad = exc.code
        check("非法操作返回 400", bad == 400, str(bad))

        saved = request(base_url, "/api/save", {"path": OUT, "label": "chino-server"})
        check("落盘成功", os.path.isfile(OUT), saved["saved"]["path"])
        check("落盘 revision 递增", saved["saved"]["revision"] > 326, str(saved["saved"]["revision"]))
        check("落盘后重新装载", saved["saved"]["parts"] >= 1)

        status2 = request(base_url, "/api/status")
        check("保存后 dirty 归零", status2.get("dirty") in (False, None), str(status2.get("dirty")))

        protection = None
        try:
            request(base_url, "/api/edit", {"ops": [{"op": "raw.set", "path": "state.user.loginName", "value": "hacked"}]})
        except urllib.error.HTTPError as exc:
            protection = exc.code
        check("身份字段受保护", protection == 400, str(protection))

        print("\n服务端端到端检查通过")
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
