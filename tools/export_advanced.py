"""从 APK 的 MCATBIN1 master 导出属性强化 / 觉醒（界限突破＋升星）/ 精神树。

输出（全部相对 data/）：
  attribute.json —— 72 个属性强化 cell、属性分组与消耗材料名（照 attribute-enhancement.js）
  awakening.json —— battle.limitBreak 规则、battle.awakening 规则、卡片定制槽与进化链
  spirit.json    —— 23,248 个精神树节点（含连线、开启消耗、情感技能定义）
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from parse_compact_catalog import CompactCatalog, as_int  # noqa: E402

RANK_CAP = {"RANK_1": 40, "RANK_2": 50, "RANK_3": 60, "RANK_4": 80, "RANK_5": 100}


def dump(path, payload):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
    return os.path.getsize(path)


def main(argv=None):
    argv = argv or sys.argv
    src = argv[1] if len(argv) > 1 else os.path.join(os.path.dirname(ROOT), "_re", "catalog_full.json")
    out_dir = os.path.join(ROOT, "data")
    os.makedirs(out_dir, exist_ok=True)
    root = CompactCatalog(open(src, "rb").read()).root_value()
    tables = root["tables"]
    item_table = tables.get("item") or {}
    item_names = {str(code): (row.get("name") or code) for code, row in item_table.items()}

    # ---------------------------------------------------------------- 属性强化
    rules = root["attributeEnhancement"]
    cells = {}
    for key, row in (tables["atbEnhancementCell"] or {}).items():
        cell_id = as_int(row.get("atbEnhancementCellId"))
        kind = str(row.get("atbEnhancementType") or "")
        attribute, _, stat = kind.partition("_")
        cost = {}
        for index in range(1, 4):
            code = row.get("needItemCode%d" % index)
            if code:
                cost[str(code)] = as_int(row.get("needValue%d" % index))
        gate = str(row.get("openingConditions") or "")
        try:
            revision = int(gate.rsplit("_", 1)[-1])
        except ValueError:
            revision = None
        cells[str(cell_id)] = {
            "cellId": cell_id,
            "type": kind,
            "attribute": attribute,
            "stat": stat,
            "value": as_int(row.get("effectValue")),
            "needCC": as_int(row.get("needCC") or 0),
            "revision": revision,
            "condition": row.get("openingConditions"),
            "groupId": as_int(row.get("atbGroupId")),
            "cost": cost,
        }
    chara_group = {}
    chara_attribute = {}
    for key, row in tables["chara"].items():
        chara_id = as_int(row.get("id") or key)
        if row.get("atbEnhancementGroupId") is not None:
            chara_group[str(chara_id)] = as_int(row.get("atbEnhancementGroupId"))
        if row.get("attributeId"):
            chara_attribute[str(chara_id)] = row.get("attributeId")
    attribute_path = os.path.join(out_dir, "attribute.json")
    size = dump(attribute_path, {
        "policy": rules.get("policy"),
        "bulkOrder": rules.get("bulkOrder"),
        "forcePolicy": rules.get("forcePolicy"),
        "cellOrder": [as_int(x) for x in rules.get("cellIds") or []],
        "cells": cells,
        "charaGroup": chara_group,
        "charaAttribute": chara_attribute,
        "itemNames": {code: item_names.get(code, code) for code in
                      sorted({c for row in cells.values() for c in row["cost"]})},
        "counts": {"cells": len(cells), "characters": len(chara_group), "source": "catalog MCATBIN1"},
    })
    print("attribute.json cells=%d chara=%d bytes=%d" % (len(cells), len(chara_group), size))

    # ---------------------------------------------------------------- 觉醒（突破 + 升星）
    battle = root["battle"]
    limit = battle.get("limitBreak") or {}
    awakening = battle.get("awakening") or {}
    charas = {}
    for key, row in tables["chara"].items():
        chara_id = as_int(row.get("id") or key)
        chain = [as_int(row.get("defaultCardId"))]
        for index in range(1, 6):
            value = row.get("evolutionCardId%d" % index)
            if value:
                chain.append(as_int(value))
        charas[str(chara_id)] = {
            "defaultCardId": as_int(row.get("defaultCardId")),
            "chain": [x for x in chain if x],
            "attribute": row.get("attributeId"),
            "name": row.get("name"),
            "initialType": row.get("initialType"),
        }
    cards = {}
    for key, row in (tables["card"] or {}).items():
        card_id = as_int(row.get("cardId") or key)
        rank = row.get("rank")
        customize = None
        raw_customize = row.get("cardCustomize")
        if isinstance(raw_customize, dict):
            slots = []
            for index in range(1, 7):
                gift_id = as_int(raw_customize.get("giftId%d" % index))
                if not gift_id:
                    continue
                slots.append({
                    "target": index,
                    "giftId": gift_id,
                    "quantity": as_int(raw_customize.get("giftNum%d" % index)),
                    "bonusCode": raw_customize.get("bonusCode%d" % index),
                    "bonusNum": as_int(raw_customize.get("bonusNum%d" % index)),
                })
            customize = slots
        cards[str(card_id)] = {
            "cardId": card_id,
            "rank": rank,
            "maxLevel": RANK_CAP.get(rank),
            "charaNo": as_int(row.get("charaNo")),
            "attributeId": row.get("attributeId"),
            "growthType": row.get("growthType"),
            "initialType": row.get("initialType"),
            "attack": as_int(row.get("attack")),
            "defense": as_int(row.get("defense")),
            "hp": as_int(row.get("hp")),
            "miniCharaNo": as_int(row.get("miniCharaNo")),
            "name": row.get("cardName"),
            "customize": customize,
        }
    awakening_path = os.path.join(out_dir, "awakening.json")
    size = dump(awakening_path, {
        "limitBreak": {
            "policy": limit.get("policy"),
            "costByRevision": [as_int(x) for x in limit.get("costByRevision") or []],
            "gemsByDefaultRank": {str(k): as_int(v) for k, v in (limit.get("gemsByDefaultRank") or {}).items()},
            "forcePerRevision": as_int(limit.get("forcePerRevision")),
            "item": "LIMIT_BREAK_ALL",
        },
        "awakening": {
            "policy": awakening.get("policy"),
            "forcePerSlot": as_int(awakening.get("forcePerSlot")),
            "nextCard": {str(as_int(k)): as_int(v) for k, v in (awakening.get("nextCard") or {}).items()},
            "evolveCost": {str(k): as_int(v) for k, v in (awakening.get("evolveCost") or {}).items()},
        },
        "charas": charas,
        "cards": cards,
        "counts": {"characters": len(charas), "cards": len(cards), "source": "catalog MCATBIN1"},
    })
    print("awakening.json chara=%d cards=%d bytes=%d" % (len(charas), len(cards), size))

    # ---------------------------------------------------------------- 精神树
    mental = root["mentalEnhancement"]
    native = mental.get("nativeSkills") or {}
    unverified = mental.get("unverifiedSkills") or {}
    spirit_cells = {}
    skill_total = 0
    skill_wired = 0
    for key, row in tables["charaEnhancementCell"].items():
        cell_id = as_int(row.get("charaEnhancementCellId"))
        gifts = []
        for index in range(1, 7):
            gift = row.get("openGift%d" % index)
            if isinstance(gift, dict):
                gifts.append({
                    "id": as_int(gift.get("id")),
                    "name": gift.get("name"),
                    "rank": as_int(gift.get("rank")),
                    "quantity": as_int(row.get("openGiftQuantity%d" % index)),
                })
        entry = {
            "cellId": cell_id,
            "groupId": as_int(row.get("groupId")),
            "type": row.get("enhancementType"),
            "value": as_int(row.get("effectValue")),
            "need": as_int(row.get("needOpenedCellId")),
            "needCC": as_int(row.get("needCC") or 0),
            "x": row.get("pointX"),
            "y": row.get("pointY"),
            "links": [as_int(x) for x in row.get("connectedCellIdList") or []],
            "gifts": gifts,
        }
        if row.get("enhancementType") == "SKILL":
            skill = row.get("emotionSkill") or {}
            skill_id = as_int(skill.get("id") or row.get("effectValue"))
            arts = []
            for index in range(1, 11):
                if skill.get("artId%d" % index):
                    arts.append(as_int(skill.get("artId%d" % index)))
            wired = bool(native.get(str(skill_id)))
            skill_total += 1
            if wired:
                skill_wired += 1
            entry["skill"] = {
                "id": skill_id,
                "definition": skill,
                "artList": arts,
                "wired": wired,
                "unverified": bool(unverified.get(str(skill_id))),
            }
        spirit_cells[str(cell_id)] = entry
    spirit_groups = {}
    for key, ids in (mental.get("groups") or {}).items():
        spirit_groups[str(as_int(key))] = [as_int(x) for x in ids]
    chara_group = {}
    for key, row in tables["chara"].items():
        if row.get("enhancementGroupId") is not None:
            chara_group[str(as_int(row.get("id") or key))] = as_int(row.get("enhancementGroupId"))
    spirit_path = os.path.join(out_dir, "spirit.json")
    size = dump(spirit_path, {
        "cells": spirit_cells,
        "groups": spirit_groups,
        "charaGroup": chara_group,
        "counts": {
            "cells": len(spirit_cells),
            "groups": len(spirit_groups),
            "characters": len(chara_group),
            "skills": skill_total,
            "wired": skill_wired,
            "source": "catalog MCATBIN1",
        },
    })
    print("spirit.json cells=%d groups=%d chara=%d skills=%d wired=%d bytes=%d"
          % (len(spirit_cells), len(spirit_groups), len(chara_group), skill_total, skill_wired, size))
    return 0


if __name__ == "__main__":
    sys.exit(main())
