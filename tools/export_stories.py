"""导出角色剧情 / 衣装剧情 / 衣装表。

数据来源（全部来自安装包，不猜）：
  <APK>/assets/magia/offline/catalog.json     MCATBIN1：tables.section（charaId / questType / clearReward）、
                                              battle.storyRules（section → questBattleId）、
                                              battle.costumeStories（section → live2dId）
  <APK_DATA>/files/magica/js/libs/sectionList.json   中文标题与简介
  <APK_DATA>/files/magica/js/libs/live2dList.json    衣装（live2dId / 中文名 / 语音前缀）

输出：data/stories.json（按 sectionId 与 charaId 双向索引）、data/costumes.json
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from parse_compact_catalog import CompactCatalog, as_int  # noqa: E402
from zh import normalize, translated  # noqa: E402

DEFAULT_CATALOG = os.path.join(os.path.dirname(ROOT), "_re", "catalog_full.json")
DEFAULT_LIBS = r"H:/magia_server/io.kamihama.totentanz/files/magica/js/libs"


def dump(path, payload):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
    return os.path.getsize(path)


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        return default


def main(argv=None):
    argv = argv or sys.argv
    catalog_path = argv[1] if len(argv) > 1 else DEFAULT_CATALOG
    libs_dir = argv[2] if len(argv) > 2 else DEFAULT_LIBS
    out_dir = os.path.join(ROOT, "data")
    os.makedirs(out_dir, exist_ok=True)

    root = CompactCatalog(open(catalog_path, "rb").read()).root_value()
    tables = root["tables"]
    battle = root.get("battle") or {}

    zh_sections = {str(row.get("sectionId")): row
                   for row in load_json(os.path.join(libs_dir, "sectionList.json"), [])}
    live2d_rows = load_json(os.path.join(libs_dir, "live2dList.json"), [])

    # section → questBattleId：以 tables.questBattle 为主（覆盖 2397 段），storyRules 作补充
    quest_index = {}
    for row_key, row in (tables.get("questBattle") or {}).items():
        section_id = as_int(row.get("sectionId"))
        battle_id = as_int(row.get("questBattleId") or row_key)
        if section_id and battle_id:
            quest_index.setdefault(str(section_id), []).append(battle_id)

    rules_index = {}
    for key, value in (battle.get("storyRules") or {}).items():
        section_text = str(key).split("-")[0]
        ids = rules_index.setdefault(section_text, [])
        for qid in (value or {}).get("activeQuestIds") or []:
            qid = as_int(qid)
            if qid and qid not in ids:
                ids.append(qid)

    # 衣装剧情：section → live2dId（客户端 CharaQuest.js 用 genericId 末两位）
    costume_live2d = {}
    for row in ((battle.get("costumeStories") or {}).get("sections") or []):
        section_id = as_int(row.get("sectionId"))
        if section_id:
            costume_live2d[str(section_id)] = {
                "live2dId": row.get("live2dId"),
                "charaId": as_int(row.get("charaId")),
                "questBattleIds": [as_int(x) for x in row.get("questBattleIds") or []],
            }
    for key, row in tables["section"].items():
        section_id = as_int(row.get("sectionId") or key)
        if row.get("questType") != "COSTUME" or not section_id:
            continue
        generic = as_int(row.get("genericId"))
        derived = str(generic)[-2:] if generic else None
        entry = costume_live2d.setdefault(str(section_id), {"live2dId": None,
                                                          "charaId": as_int(row.get("charaId")),
                                                          "questBattleIds": []})
        if not entry.get("live2dId"):
            entry["live2dId"] = derived

    sections = {}
    by_chara = {}
    counts = {"CHARA": 0, "COSTUME": 0, "other": 0}
    for key, row in tables["section"].items():
        section_id = as_int(row.get("sectionId") or key)
        if not section_id:
            continue
        quest_type = row.get("questType")
        chara_id = as_int(row.get("charaId"))
        zh = zh_sections.get(str(section_id)) or {}
        costume = costume_live2d.get(str(section_id)) or {}
        entry = {
            "sectionId": section_id,
            "charaId": chara_id or costume.get("charaId"),
            "questType": quest_type,
            "title": translated("sections", section_id, "title", zh.get("title") or row.get("title")),
            "message": normalize(zh.get("message") or row.get("message")),
            "area": zh.get("areaDetailName"),
            "ap": as_int(row.get("ap")),
            "difficulty": as_int(row.get("difficulty")),
            "questBattleIds": sorted(set(
                [as_int(x) for x in (quest_index.get(str(section_id)) or [])]
                + [as_int(x) for x in (rules_index.get(str(section_id)) or [])]
                + [int(x) for x in costume.get("questBattleIds") or []])),
            "live2dId": costume.get("live2dId"),
            "clearReward": None,
        }
        reward = row.get("clearReward")
        if isinstance(reward, dict):
            piece = reward.get("piece") or {}
            entry["clearReward"] = {
                "presentType": reward.get("presentType"),
                "displayName": reward.get("displayName"),
                "quantity": as_int(reward.get("quantity")),
                "itemId": reward.get("itemId"),
                "genericId": as_int(reward.get("genericId")),
                "genericCode": reward.get("genericCode"),
                "pieceId": as_int(piece.get("pieceId")),
            }
        if not entry["questBattleIds"]:
            entry["questBattleIds"] = [section_id * 100 + 1]
        sections[str(section_id)] = entry
        owner = None
        if quest_type == "CHARA":
            # 客户端 CharaQuest.js：charaId === section.genericId 才算这个角色的剧情
            owner = as_int(row.get("genericId"))
        elif quest_type == "COSTUME":
            # 衣装剧情按 section.charaId 归属
            owner = entry["charaId"]
        entry["ownerCharaId"] = owner
        if owner:
            bucket = by_chara.setdefault(str(owner), {"chara": [], "costume": []})
            if quest_type == "CHARA":
                bucket["chara"].append(section_id)
                counts["CHARA"] += 1
            else:
                bucket["costume"].append(section_id)
                counts["COSTUME"] += 1
        else:
            counts["other"] += 1

    for bucket in by_chara.values():
        bucket["chara"].sort()
        bucket["costume"].sort()

    stories_path = os.path.join(out_dir, "stories.json")
    size = dump(stories_path, {"sections": sections, "byChara": by_chara, "counts": counts})
    print("stories.json sections=%d chara_groups=%d chara=%d costume=%d bytes=%d"
          % (len(sections), len(by_chara), counts["CHARA"], counts["COSTUME"], size))

    costumes = {}
    for row in live2d_rows:
        chara_id = as_int(row.get("charaId"))
        live2d_id = row.get("live2dId")
        if not chara_id or live2d_id is None:
            continue
        costumes.setdefault(str(chara_id), []).append({
            "live2dId": str(live2d_id),
            "name": row.get("description"),
            "voicePrefixNo": row.get("voicePrefixNo"),
            "default": str(live2d_id) == "00",
        })
    for rows in costumes.values():
        rows.sort(key=lambda item: item["live2dId"])
    costumes_path = os.path.join(out_dir, "costumes.json")
    size = dump(costumes_path, {
        "charaCostumes": costumes,
        "counts": {"characters": len(costumes), "costumes": sum(len(v) for v in costumes.values())},
    })
    print("costumes.json chara=%d entries=%d bytes=%d"
          % (len(costumes), sum(len(v) for v in costumes.values()), size))
    return 0


if __name__ == "__main__":
    sys.exit(main())
