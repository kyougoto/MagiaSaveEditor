"""记忆结晶筛选 / 详情 / 队伍编成的回归测试。

约束：
  1. 筛选按星级与类型，且不影响未筛选时的总数；
  2. 结晶详情带描述、技能与所在队伍；
  3. 队伍只有 1..4 位可编辑，支援位（questPositionHelper）不参与；
  4. 同一枚结晶不能同时装在两个位置，同一张卡不能重复上阵。
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

    # ---- 筛选
    everything = editor.pieces_view(None, 0, 500)
    check("结晶列表包含全部已拥有", everything["total"] > 0, "%d 枚" % everything["total"])
    check("列表返回可选星级与类型", bool(everything["ranks"]) and bool(everything["types"]),
          "ranks=%s types=%s" % (everything["ranks"], everything["types"]))
    rank = everything["ranks"][0]
    by_rank = editor.pieces_view(None, 0, 500, rank=rank)
    check("按星级筛选", all(row["rank"] == rank for row in by_rank["rows"])
          and 0 < by_rank["total"] <= everything["total"], "%s -> %d 枚" % (rank, by_rank["total"]))
    piece_type = everything["types"][0]
    by_type = editor.pieces_view(None, 0, 500, piece_type=piece_type)
    check("按类型筛选", all(row["type"] == piece_type for row in by_type["rows"])
          and 0 < by_type["total"] <= everything["total"], "%s -> %d 枚" % (piece_type, by_type["total"]))

    # ---- 详情
    sample = everything["rows"][0]
    detail = editor.piece_detail(sample["id"])
    check("详情带描述", bool(detail["description"]), detail["description"][:24])
    check("详情带技能", len(detail["skills"]) >= 1,
          json.dumps(detail["skills"][0], ensure_ascii=False)[:60])
    check("详情带等级上限", detail["maxLevel"] and detail["maxLevel"] >= detail["level"],
          "Lv %s / %s" % (detail["level"], detail["maxLevel"]))
    check("详情列出所在队伍字段", isinstance(detail["decks"], list), "%d 处" % len(detail["decks"]))
    editor.apply([{"op": "piece.set", "id": sample["id"], "field": "lbCount", "value": 2}])
    check("详情页可改突破", editor.piece_detail(sample["id"])["lbCount"] == 2)
    editor.apply([{"op": "piece.set", "id": sample["id"], "field": "lbCount", "value": sample["lbCount"]}])

    # ---- 队伍
    decks = editor.decks_view()
    check("读取队伍列表", decks["total"] > 0, "%d 个编成" % decks["total"])
    playable = [deck for deck in decks["decks"] if deck["editable"]]
    check("存在可编辑的玩家队伍", bool(playable), json.dumps([d["deckType"] for d in decks["decks"]]))
    deck = playable[0]
    check("队伍有 4 个成员位", len(deck["members"]) == 4, str(len(deck["members"])))
    check("支援位单独标出", deck["helperPosition"] is not None, "helper=%s" % deck["helperPosition"])

    filled = [member for member in deck["members"] if member["userCardId"]]
    check("队伍成员能解析到角色", bool(filled) and bool(filled[0]["name"]),
          "%s Lv %s" % (filled[0]["name"], filled[0]["level"]))
    equipped = [item for member in filled for item in member["pieces"]]
    check("队伍里的结晶能解析到名称", bool(equipped) and bool(equipped[0]["name"]),
          equipped[0]["name"] if equipped else "无")

    # ---- 结晶编成
    deck_type = deck["deckType"]
    member_slot = filled[0]["slot"]
    instance = sample["id"]
    # 结晶槽位 = 1 + 魔力解放次数，先把这张卡拉满解放，才能用第 4 个槽
    editor.apply([{"op": "card.set", "id": filled[0].get("userCardId"),
                   "field": "revision", "value": 3}])
    editor.apply([{"op": "deck.piece", "deckType": deck_type, "member": member_slot,
                   "slot": 4, "pieceInstanceId": instance}])
    after = editor.decks_view()
    target = next(item for item in after["decks"] if item["deckType"] == deck_type)
    slots = [piece for member in target["members"] if member["slot"] == member_slot
             for piece in member["pieces"] if piece["id"] == instance]
    check("结晶装到指定槽位", bool(slots) and slots[0]["slot"] == 4, json.dumps(slots, ensure_ascii=False)[:80])
    check("结晶页能反查编成队伍", any(item["deckType"] == deck_type
                                for item in editor.piece_detail(instance)["decks"]),
          json.dumps(editor.piece_detail(instance)["decks"], ensure_ascii=False)[:80])

    other_member = 2 if member_slot != 2 else 1
    other_row = next((m for m in target["members"]
                      if m["slot"] == other_member and m.get("userCardId")), None)
    if other_row:
        editor.apply([{"op": "card.set", "id": other_row["userCardId"],
                       "field": "revision", "value": 3}])
    expect_error("同一枚结晶不能装两处",
                 lambda: editor.apply([{"op": "deck.piece", "deckType": deck_type,
                                        "member": other_member, "slot": 4,
                                        "pieceInstanceId": instance}]),
                 "piece_already_equipped")
    editor.apply([{"op": "deck.removePiece", "deckType": deck_type,
                   "member": member_slot, "slot": 4}])
    check("可以卸下结晶", not any(piece["id"] == instance
                              for member in editor.decks_view()["decks"][0]["members"]
                              for piece in member["pieces"]))

    # ---- 队伍成员
    owned = [row for row in editor.rows("userCardList")]
    in_deck = {member["userCardId"] for member in deck["members"] if member["userCardId"]}
    outsider = next((row for row in owned if str(row.get("id")) not in in_deck), None)
    if outsider:
        editor.apply([{"op": "deck.member", "deckType": deck_type, "slot": 3,
                       "userCardId": outsider["id"]}])
        updated = next(item for item in editor.decks_view()["decks"] if item["deckType"] == deck_type)
        check("换人写入成功", updated["members"][2]["userCardId"] == outsider["id"],
              updated["members"][2]["name"])
        expect_error("同一张卡不能重复上阵",
                     lambda: editor.apply([{"op": "deck.member", "deckType": deck_type,
                                            "slot": 1, "userCardId": outsider["id"]}]),
                     "already_present")
        editor.apply([{"op": "deck.removeMember", "deckType": deck_type, "slot": 3}])
        cleared = next(item for item in editor.decks_view()["decks"] if item["deckType"] == deck_type)
        check("移除成员清空该位", cleared["members"][2]["userCardId"] is None)

    expect_error("非玩家编成不能编辑",
                 lambda: editor.apply([{"op": "deck.member", "deckType": 20, "slot": 1,
                                        "userCardId": owned[0]["id"]}]),
                 "deck_not_editable")

    # ---- 阵型与支援位
    formations = editor.formations_view()
    check("阵型表完整", formations["total"] >= 10,
          "%d 个，已获取 %d" % (formations["total"], formations["ownedCount"]))
    check("阵型带格子与中文名",
          bool(formations["rows"][0]["slots"]) and bool(formations["rows"][0]["name"]),
          "%s slots=%s" % (formations["rows"][0]["name"], formations["rows"][0]["slots"]))

    deck_row = next(row for row in editor.rows("userDeckList")
                    if str(row.get("deckType")) == str(deck_type))
    check("队伍带阵型信息", bool(deck.get("formationName")),
          "%s #%s" % (deck.get("formationName"), deck.get("formationSheetId")))

    target = next(row for row in formations["rows"]
                  if not row["owned"] and len(row["slots"]) >= 5)
    expect_error("未获取的阵型不能用",
                 lambda: editor.apply([{"op": "deck.formation", "deckType": deck_type,
                                        "formationSheetId": target["formationSheetId"]}]),
                 "formation_not_owned")
    editor.apply([{"op": "formation.add", "formationSheetId": target["formationSheetId"]}])
    check("获取阵型", target["formationSheetId"] in
          [row["formationSheetId"] for row in editor.formations_view()["rows"] if row["owned"]])
    editor.apply([{"op": "deck.formation", "deckType": deck_type,
                   "formationSheetId": target["formationSheetId"]}])
    switched = next(item for item in editor.decks_view()["decks"] if item["deckType"] == deck_type)
    slots = sorted(target["slots"])
    check("切换阵型后重排格子",
          [switched["members"][index]["slot"] for index in range(4)]
          and switched["formationSheetId"] == target["formationSheetId"]
          and switched["helperPosition"] == slots[4],
          "%s helper=%s" % (switched.get("formationName"), switched["helperPosition"]))
    expect_error("使用中的阵型不能取消获取",
                 lambda: editor.apply([{"op": "formation.remove",
                                        "formationSheetId": target["formationSheetId"]}]),
                 "formation_in_use")

    deck_row = next(row for row in editor.rows("userDeckList")
                    if str(row.get("deckType")) == str(deck_type))
    taken = {deck_row.get("questPositionId%d" % index) for index in range(1, 5)}
    free = [slot for slot in slots if slot not in taken]
    if free:
        editor.apply([{"op": "deck.helper", "deckType": deck_type, "position": free[0]}])
        moved = next(item for item in editor.decks_view()["decks"] if item["deckType"] == deck_type)
        check("支援位可更换", moved["helperPosition"] == free[0],
              "%s -> 格 %s" % (moved["helperPosition"], free[0]))
    expect_error("支援位不能放到已占用格",
                 lambda: editor.apply([{"op": "deck.helper", "deckType": deck_type,
                                        "position": sorted(taken)[0]}]),
                 "deck_position_taken")

    # ---- 落盘
    out = os.path.join(WORK, "deck-out.zip")
    arc2 = archive_mod.SlotArchive.load(SAMPLE)
    editor2 = Editor(arc2)
    editor2.apply([{"op": "card.set", "id": filled[0].get("userCardId"),
                    "field": "revision", "value": 3}])
    editor2.apply([{"op": "deck.piece", "deckType": deck_type, "member": member_slot,
                    "slot": 4, "pieceInstanceId": instance}])
    info = arc2.save(out, profile=editor2.profile, label="deck")
    reloaded = archive_mod.SlotArchive.load(out)
    deck_rows = reloaded.profile["state"]["userDeckList"]
    check("落盘后编成仍在",
          any(str(deck.get("userPieceId%02d4" % member_slot)) == str(instance) for deck in deck_rows),
          "%d 字节" % info["bytes"])
    print("\n结晶筛选 / 详情 / 队伍编成 全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
