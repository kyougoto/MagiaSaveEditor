"""角色剧情 / 衣装剧情 / 衣装获取状态的回归测试。

硬约束：
  1. 默认服装（live2dId 00）永远算已获取，且不能取消；
  2. 正在穿着的衣装不能直接取消获取（要先换掉）；
  3. 剧情段「通关 / 回退」会把段内任务一起处理，NONE 标记不被动。
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from magiasave import archive as archive_mod  # noqa: E402
from magiasave.errors import ValidationError  # noqa: E402
from magiasave.model import Editor  # noqa: E402

SAMPLE = os.environ.get("MAGIA_SAMPLE", r"H:/magia_server/magia-save-chino-1794718180238.zip")
WORK = os.path.join(ROOT, "_work")
CHARA = 1001


def check(label, condition, detail=""):
    print(("PASS " if condition else "FAIL ") + label + ((" :: " + detail) if detail else ""))
    if not condition:
        raise SystemExit(1)


def expect_error(label, fn, code):
    try:
        fn()
    except ValidationError as exc:
        check(label, exc.code == code, "%s (%s)" % (exc.code, exc))
        return
    except Exception as exc:  # noqa: BLE001
        check(label, False, "意外异常 %r" % (exc,))
        return
    check(label, False, "没有抛错")


def main():
    os.makedirs(WORK, exist_ok=True)
    arc = archive_mod.SlotArchive.load(SAMPLE)
    editor = Editor(arc)

    # ---- 衣装表
    costumes = editor.costumes_view(CHARA)
    check("衣装总数与官方表一致", costumes["total"] >= 10, "%d 件" % costumes["total"])
    default_row = next(row for row in costumes["rows"] if row["live2dId"] == "00")
    check("默认服装标为 default 且已获取", default_row["default"] and default_row["owned"],
          json.dumps(default_row, ensure_ascii=False))
    check("默认服装是当前穿着", costumes["current"] == "00", costumes["current"])

    # ---- 获取 / 取消 / 穿着
    unowned = next(row for row in costumes["rows"]
                   if not row["owned"] and not row["default"] and not row["current"])
    editor.apply([{"op": "costume.add", "charaId": CHARA, "live2dId": unowned["live2dId"]}])
    after_add = editor.costumes_view(CHARA)
    check("获取衣装写入 userLive2dList",
          next(row for row in after_add["rows"] if row["live2dId"] == unowned["live2dId"])["owned"],
          unowned["live2dId"])
    check("获取后已获取数 +1", after_add["ownedCount"] == costumes["ownedCount"] + 1,
          "%d -> %d" % (costumes["ownedCount"], after_add["ownedCount"]))

    editor.apply([{"op": "costume.equip", "charaId": CHARA, "live2dId": unowned["live2dId"]}])
    check("设为当前穿着", editor.costumes_view(CHARA)["current"] == unowned["live2dId"],
          editor.costumes_view(CHARA)["current"])

    expect_error("默认服装不能取消获取",
                 lambda: editor.apply([{"op": "costume.remove", "charaId": CHARA, "live2dId": "00"}]),
                 "costume_default_locked")
    expect_error("正在穿着的衣装不能取消获取",
                 lambda: editor.apply([{"op": "costume.remove", "charaId": CHARA,
                                        "live2dId": unowned["live2dId"]}]),
                 "costume_in_use")

    editor.apply([{"op": "costume.equip", "charaId": CHARA, "live2dId": "00"}])
    editor.apply([{"op": "costume.remove", "charaId": CHARA, "live2dId": unowned["live2dId"]}])
    check("换回默认后可以取消获取",
          editor.costumes_view(CHARA)["ownedCount"] == costumes["ownedCount"],
          str(editor.costumes_view(CHARA)["ownedCount"]))
    expect_error("不存在的衣装不能获取",
                 lambda: editor.apply([{"op": "costume.add", "charaId": CHARA, "live2dId": "zz"}]),
                 "path_missing")

    # ---- 剧情
    stories = editor.stories_view(CHARA)
    check("角色剧情段来自 master", len(stories["chara"]) > 0, "%d 段" % len(stories["chara"]))
    check("衣装剧情段来自 master", len(stories["costume"]) > 0, "%d 段" % len(stories["costume"]))
    first = stories["chara"][0]
    check("剧情段带任务与标题", first["title"] and len(first["quests"]) >= 1,
          "%s · %s" % (first["title"], [q["questBattleId"] for q in first["quests"]]))

    before = {q["questBattleId"]: q["cleared"] for q in first["quests"]}
    editor.apply([{"op": "story.set", "charaId": CHARA, "sectionId": first["sectionId"], "cleared": True}])
    after = next(row for row in editor.stories_view(CHARA)["chara"] if row["sectionId"] == first["sectionId"])
    check("整段通关写 cleared", after["cleared"] is True, str(after["cleared"]))
    check("段内任务一起通关", all(q["cleared"] for q in after["quests"]),
          json.dumps([q["cleared"] for q in after["quests"]]))

    editor.apply([{"op": "story.set", "charaId": CHARA, "sectionId": first["sectionId"], "cleared": False}])
    after = next(row for row in editor.stories_view(CHARA)["chara"] if row["sectionId"] == first["sectionId"])
    check("回退把段与任务都改回未通关", after["cleared"] is False
          and not any(q["cleared"] for q in after["quests"]), str(after["cleared"]))
    check("回退不碰原本就是 NONE 的任务标记",
          all(q["missions"][index] in (None, "NONE") or q["missions"][index] == "NON_CLEAR"
              for q in after["quests"] for index in range(3)),
          json.dumps([q["missions"] for q in after["quests"]]))

    other = next(row.get("charaId") for row in editor.rows("userCharaList")
                 if str(row.get("charaId")) != str(CHARA))
    expect_error("别人的剧情段不能套到这个角色上",
                 lambda: editor.apply([{"op": "story.set", "charaId": other,
                                        "sectionId": first["sectionId"], "cleared": True}]),
                 "story_owner_mismatch")

    costume_story = stories["costume"][0]
    editor.apply([{"op": "story.set", "charaId": CHARA, "sectionId": costume_story["sectionId"],
                   "cleared": True}])
    after_costume = next(row for row in editor.stories_view(CHARA)["costume"]
                         if row["sectionId"] == costume_story["sectionId"])
    check("衣装剧情同样可以整段通关", after_costume["cleared"] is True,
          "%s · %s" % (costume_story["sectionId"], costume_story["title"]))

    # ---- 魔女化身开关
    doppel = editor.doppel_view(CHARA)
    check("角色有魔女化身映射", bool(doppel["doppelId"]) and bool(doppel["name"]),
          "%s / %s" % (doppel["doppelId"], doppel["name"]))
    if doppel["unlocked"]:
        editor.apply([{"op": "doppel.set", "charaId": CHARA, "unlocked": False}])
    check("初始为未解锁", editor.doppel_view(CHARA)["unlocked"] is False)
    editor.apply([{"op": "doppel.set", "charaId": CHARA, "unlocked": True}])
    check("解锁魔女化身写入 userDoppelList", editor.doppel_view(CHARA)["unlocked"] is True)
    expect_error("重复解锁被拒绝",
                 lambda: editor.apply([{"op": "doppel.set", "charaId": CHARA, "unlocked": True}]),
                 "already_present")
    editor.apply([{"op": "doppel.set", "charaId": CHARA, "unlocked": False}])
    check("取消解锁", editor.doppel_view(CHARA)["unlocked"] is False)
    expect_error("未解锁时取消被拒绝",
                 lambda: editor.apply([{"op": "doppel.set", "charaId": CHARA, "unlocked": False}]),
                 "path_missing")
    editor.apply([{"op": "doppel.set", "charaId": CHARA, "unlocked": True}])

    # ---- 落盘
    out = os.path.join(WORK, "story-out.zip")
    arc2 = archive_mod.SlotArchive.load(SAMPLE)
    editor2 = Editor(arc2)
    editor2.apply([{"op": "costume.add", "charaId": CHARA, "live2dId": unowned["live2dId"]}])
    editor2.apply([{"op": "costume.equip", "charaId": CHARA, "live2dId": unowned["live2dId"]}])
    editor2.apply([{"op": "story.set", "charaId": CHARA, "sectionId": first["sectionId"], "cleared": True}])
    info = arc2.save(out, profile=editor2.profile, label="story")
    reloaded = archive_mod.SlotArchive.load(out)
    state = reloaded.profile["state"]
    check("落盘后衣装记录还在", any(str(row.get("charaId")) == str(CHARA)
                                   and str(row.get("live2dId")) == unowned["live2dId"]
                                   for row in state.get("userLive2dList") or []),
          "%d 件" % len(state.get("userLive2dList") or []))
    check("落盘后角色穿着正确", any(str(row.get("charaId")) == str(CHARA)
                                   and str(row.get("live2dId")) == unowned["live2dId"]
                                   for row in state.get("userCharaList") or []))
    check("落盘后剧情段已通关", any(str(row.get("sectionId")) == str(first["sectionId"])
                                   and row.get("cleared") is True
                                   for row in state.get("userSectionList") or []),
          "%d 字节" % info["bytes"])
    print("\n剧情 / 衣装 全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
