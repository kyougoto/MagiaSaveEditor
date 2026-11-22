"""属性强化 / 精神树技能 / 觉醒与突破的回归测试。

三条硬约束都在这里断言：
  1. 精神树与属性强化的操作不改变持有材料（userGiftList / userItemList / riche）；
  2. 属性强化的数值按「同属性全体角色」结算进 userStatusList 与 userTotalForces；
  3. 觉醒槽位可以单格填充，也可以全部填充而不触发升星。
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


def snapshot_materials(editor):
    state = editor.state
    return (
        json.dumps(state.get("userGiftList"), sort_keys=True, ensure_ascii=False),
        json.dumps(state.get("userItemList"), sort_keys=True, ensure_ascii=False),
        state.get("gameUser", {}).get("riche"),
    )


def forces(editor):
    return int((editor.state.get("userTotalForces") or {}).get("totalForces") or 0)


def main():
    os.makedirs(WORK, exist_ok=True)
    arc = archive_mod.SlotArchive.load(SAMPLE)
    editor = Editor(arc)

    # ---- 精神树：节点来自 APK master，坐标与连线齐全
    spirit = editor.spirit_view(CHARA)
    check("精神树节点数", len(spirit["nodes"]) == 101, "%d 个节点" % len(spirit["nodes"]))
    check("精神树带坐标", all(isinstance(node.get("x"), (int, float)) for node in spirit["nodes"]))
    check("精神树带连线", any(node.get("links") for node in spirit["nodes"]),
          "根 %s 连出 %d 条" % (spirit["nodes"][0]["cellId"], len(spirit["nodes"][0]["links"])))
    check("情感技能节点已解锁", spirit["skillCount"] == 13, "%d 个" % spirit["skillCount"])
    check("边界用于 SVG viewBox", spirit["bounds"]["maxY"] > spirit["bounds"]["minY"],
          json.dumps(spirit["bounds"]))

    before_materials = snapshot_materials(editor)
    skill_cell = next(node for node in spirit["nodes"] if node.get("skill"))
    result = editor.apply([{"op": "spirit.open", "charaId": CHARA, "cellId": skill_cell["cellId"]}])
    check("开启情感技能节点", not result["noop"], "改动 %d 处" % len(result["changed"]))
    chara = next(row for row in editor.rows("userCharaList") if row.get("charaId") == CHARA)
    check("情感技能写入 emotionSkillList", len(chara.get("emotionSkillList") or []) == 1,
          json.dumps(chara.get("emotionSkillList"))[:120])
    check("情感技能 id 写入 emotionSkillIds", str(skill_cell["skill"]["id"]) in chara.get("emotionSkillIds", ""),
          str(chara.get("emotionSkillIds")))
    check("前置链自动补齐", len(editor.spirit_view(CHARA)["nodes"]) and
          editor.spirit_view(CHARA)["ownedCount"] >= 3, "已开启 %d" % editor.spirit_view(CHARA)["ownedCount"])
    check("开启精神节点不改持有材料", snapshot_materials(editor) == before_materials)

    editor.apply([{"op": "spirit.close", "charaId": CHARA, "all": True}])
    chara = next(row for row in editor.rows("userCharaList") if row.get("charaId") == CHARA)
    check("清空精神树只剩起点", editor.spirit_view(CHARA)["ownedCount"] == 1,
          "剩余 %d 个（START）" % editor.spirit_view(CHARA)["ownedCount"])
    check("清空后 addend 归零", (chara.get("addendHp"), chara.get("addendAttack")) == (0, 0))
    check("关闭精神节点不改持有材料", snapshot_materials(editor) == before_materials)

    # ---- 属性强化：同属性全体生效
    editor = Editor(arc)
    attr = editor.attribute_view(CHARA)
    check("属性强化 cell 数", len(attr["cells"]) == 12, "%s 有 %d 格" % (attr["attribute"], len(attr["cells"])))
    check("属性强化影响同属性全体", attr["memberCount"] >= 1,
          "%s 属性共 %d 人" % (attr["attributeLabel"], attr["memberCount"]))
    first_cell = next(cell for cell in attr["cells"] if cell["revisionOk"] and not cell["opened"])
    base_forces = forces(editor)
    before_materials = snapshot_materials(editor)
    editor.apply([{"op": "attribute.open", "charaId": CHARA, "cellId": first_cell["cellId"]}])
    after = editor.attribute_view(CHARA)
    opened = [cell for cell in after["cells"] if cell["opened"]]
    check("属性强化写入 cell 列表", len(opened) == 1, "已开启 %d" % len(opened))
    expected = int(first_cell["value"]) * after["memberCount"]
    check("总战力按同属性人数结算", forces(editor) - base_forces == expected,
          "增加 %d（%d × %d 人）" % (forces(editor) - base_forces, first_cell["value"], after["memberCount"]))
    status_points = {row.get("statusId"): row.get("point") for row in editor.rows("userStatusList")}
    check("属性强化写入 userStatusList", status_points.get(first_cell["type"]) == first_cell["value"],
          "%s = %s" % (first_cell["type"], status_points.get(first_cell["type"])))
    check("属性强化不改持有材料", snapshot_materials(editor) == before_materials)

    editor.apply([{"op": "attribute.close", "charaId": CHARA, "cellId": first_cell["cellId"]}])
    check("关闭属性强化回滚战力", forces(editor) == base_forces, str(forces(editor)))
    check("关闭属性强化清零状态", all(cell["point"] in (0, None) for cell in editor.attribute_view(CHARA)["cells"]
                                if cell["cellId"] == first_cell["cellId"]))

    editor.apply([{"op": "attribute.open", "charaId": CHARA, "all": True}])
    all_open = editor.attribute_view(CHARA)
    available = len([cell for cell in all_open["cells"] if cell["revisionOk"]])
    check("一键开启当前突破可用格", all_open["openedCount"] == available,
          "%d / %d（突破 %d 级可用）" % (all_open["openedCount"], all_open["cellTotal"], all_open["revision"]))
    check("一键开启仍不改材料", snapshot_materials(editor) == before_materials)

    # ---- 觉醒与突破
    editor = Editor(arc)
    awake = editor.awakening_view(chara_id=CHARA)
    check("突破阶段 3 级", len(awake["limitBreak"]["steps"]) == 3, json.dumps(awake["limitBreak"]["steps"]))
    check("命运宝石需求按初始稀有度", awake["limitBreak"]["gems"] == 10, str(awake["limitBreak"]["gems"]))
    check("觉醒链覆盖五张卡", len(awake["evolve"]["chain"]) == 5, json.dumps(awake["evolve"]["chain"]))
    card_id = awake["card"]["cardId"]
    base_forces = forces(editor)
    before_materials = snapshot_materials(editor)
    editor.apply([{"op": "awake.limit", "userCardId": awake["userCardId"], "charaId": CHARA, "count": 3}])
    card = next(row for row in editor.rows("userCardList") if row.get("id") == awake["userCardId"])
    check("突破直接到 3", card.get("revision") == 3, str(card.get("revision")))
    check("突破战力 +500/级", forces(editor) - base_forces == 1500, str(forces(editor) - base_forces))
    check("突破不改命运宝石/道具/魔法石", snapshot_materials(editor) == before_materials)
    check("突破不改卡片等级", card.get("cardId") == card_id)

    editor.apply([{"op": "awake.set", "userCardId": awake["userCardId"], "value": 0}])
    card = next(row for row in editor.rows("userCardList") if row.get("id") == awake["userCardId"])
    check("允许降星级（revision 回 0）", card.get("revision") == 0, str(card.get("revision")))
    check("降级回滚战力", forces(editor) == base_forces, str(forces(editor)))

    slot = next(item["target"] for item in awake["evolve"]["slots"] if not item["done"])
    editor.apply([{"op": "awake.slot", "userCardId": awake["userCardId"], "targets": [slot], "value": True}])
    card = next(row for row in editor.rows("userCardList") if row.get("id") == awake["userCardId"])
    slot_state = editor.awakening_view(chara_id=CHARA)["evolve"]["slots"]
    target_slot = next(item for item in slot_state if item["target"] == slot)
    check("单格填充只改该格", target_slot["done"] is True, json.dumps(target_slot, ensure_ascii=False))
    check("单格填充 +200 战力", forces(editor) - base_forces == 200, str(forces(editor) - base_forces))
    check("单格填充不改材料", snapshot_materials(editor) == before_materials)

    editor.apply([{"op": "awake.slot", "userCardId": awake["userCardId"], "value": True}])
    slots = editor.awakening_view(chara_id=CHARA)["evolve"]["slots"]
    check("全部填充不触发升星", all(item["done"] for item in slots) and
          next(row for row in editor.rows("userCardList") if row.get("id") == awake["userCardId"]).get("cardId")
          == card_id, json.dumps([item["done"] for item in slots]))
    check("全部填充不改材料", snapshot_materials(editor) == before_materials)

    # ---- 落盘后仍然一致
    out = os.path.join(WORK, "advanced.zip")
    arc2 = archive_mod.SlotArchive.load(SAMPLE)
    editor2 = Editor(arc2)
    editor2.apply([{"op": "attribute.open", "charaId": CHARA, "all": True}])
    editor2.apply([{"op": "spirit.open", "charaId": CHARA, "cellIds": [1101, 1201, 1301]}])
    editor2.apply([{"op": "awake.limit", "userCardId": editor2.rows("userCharaList")[0].get("userCardId"),
                    "charaId": editor2.rows("userCharaList")[0].get("charaId"), "count": 1}])
    info = arc2.save(out, profile=editor2.profile, label="advanced")
    reloaded = archive_mod.SlotArchive.load(out)
    check("落盘后可重新加载", reloaded.profile["state"]["userStatusList"] is not None,
          "%d 字节 / %d 片" % (info["bytes"], info["parts"]))
    check("落盘后属性强化记录仍在",
          len(reloaded.profile["state"]["userCharaAtbEnhancementCellList"]) >= 3,
          str(len(reloaded.profile["state"]["userCharaAtbEnhancementCellList"])))
    check("落盘后精神节点仍在",
          len(reloaded.profile["state"]["userCharaEnhancementCellList"]) >= 3,
          str(len(reloaded.profile["state"]["userCharaEnhancementCellList"])))
    expect_error("不属于该属性的 cell 被拒绝",
                 lambda: editor.apply([{"op": "attribute.open", "charaId": CHARA, "cellId": 1}]),
                 "attribute_mismatch")
    return 0


if __name__ == "__main__":
    sys.exit(main())
