"""导出关卡解锁图（battle.sectionRules）与完整任务表（tables.questBattle）。

数据来源：APK 的 MCATBIN1 catalog。

  battle.sectionRules[sectionId] = {
      requiredQuestIds: [...]        该小节包含的任务（全通 = 小节通关）
      unlock: {sectionIds, questBattleIds, chapterIds}   通关后开放的东西
      completedChapter: {chapterId, requiredSectionIds}  该小节属于哪个章的完成条件
  }

输出：data/unlocks.json（含前置反查与章节聚合）、data/quests-full.json
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from parse_compact_catalog import CompactCatalog, as_int  # noqa: E402

DEFAULT_CATALOG = os.path.join(os.path.dirname(ROOT), "_re", "catalog_full.json")


def dump(path, payload):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
    return os.path.getsize(path)


def main(argv=None):
    argv = argv or sys.argv
    catalog_path = argv[1] if len(argv) > 1 else DEFAULT_CATALOG
    out_dir = os.path.join(ROOT, "data")
    os.makedirs(out_dir, exist_ok=True)
    root = CompactCatalog(open(catalog_path, "rb").read()).root_value()
    tables = root["tables"]
    battle = root.get("battle") or {}
    rules = battle.get("sectionRules") or {}

    by_section = {}
    prerequisites = {}
    chapter_sections = {}
    for key, row in rules.items():
        section_id = as_int(row.get("sectionId") or key)
        if not section_id:
            continue
        unlock = row.get("unlock") or {}
        entry = {
            "sectionId": section_id,
            "requiredQuestIds": [as_int(x) for x in row.get("requiredQuestIds") or []],
            "unlockSections": [as_int(x) for x in unlock.get("sectionIds") or []],
            "unlockQuests": [as_int(x) for x in unlock.get("questBattleIds") or []],
            "unlockChapters": [as_int(x) for x in unlock.get("chapterIds") or []],
        }
        completed = row.get("completedChapter")
        if isinstance(completed, dict):
            entry["chapterId"] = as_int(completed.get("chapterId"))
            entry["chapterSections"] = [as_int(x) for x in completed.get("requiredSectionIds") or []]
            if entry["chapterId"]:
                bucket = chapter_sections.setdefault(str(entry["chapterId"]), set())
                for sid in entry["chapterSections"]:
                    bucket.add(sid)
        by_section[str(section_id)] = entry
        for target in entry["unlockSections"]:
            prerequisites.setdefault(str(target), set()).add(section_id)

    # 小节布局（分支章的剧情树：坐标 + 连线 + 图标）
    section_meta = {}
    for key, row in tables["section"].items():
        section_id = as_int(row.get("sectionId") or key)
        if not section_id:
            continue
        connect = []
        for token in str(row.get("connectPointIds") or "").split(","):
            token = token.strip()
            if token.isdigit():
                connect.append(int(token))
        section_meta[str(section_id)] = {
            "sectionId": section_id,
            "title": row.get("title"),
            "x": as_int(row.get("pointX")),
            "y": as_int(row.get("pointY")),
            "connect": connect,
            "iconId": as_int(row.get("iconId")),
            "parameter": as_int(row.get("parameter")),
            "secret": bool(row.get("secret")),
            "chapterId": None,
        }

    chapters = {}
    chapter_table = tables.get("chapter") or {}
    for key, row in chapter_table.items():
        chapter_id = as_int(row.get("chapterId") or key)
        if not chapter_id:
            continue
        chapter_section_ids = sorted(chapter_sections.get(str(chapter_id), set()))
        layout = []
        for sid in chapter_section_ids:
            meta = section_meta.get(str(sid))
            if not meta or meta["x"] is None or meta["y"] is None:
                continue
            meta = dict(meta)
            meta["chapterId"] = chapter_id
            layout.append(meta)
        layout.sort(key=lambda item: (item["y"], item["x"], item["sectionId"]))
        chapters[str(chapter_id)] = {
            "chapterId": chapter_id,
            "layout": layout,
            "chapterNo": as_int(row.get("chapterNo")),
            "chapterNoForView": row.get("chapterNoForView"),
            "chapterType": row.get("chapterType"),
            "partNo": as_int(row.get("partNo")),
            "questType": row.get("questType"),
            "title": row.get("title"),
            "sectionCount": as_int(row.get("sectionCount")),
            "sections": chapter_section_ids,
        }

    # 章级前置：通关某一节会解锁哪些章 → 那些章的前置就是这一节所在的章
    chapter_prereq = {}
    for key, entry in by_section.items():
        source = entry.get("chapterId")
        for target in entry.get("unlockChapters") or []:
            if source and target and int(source) != int(target):
                chapter_prereq.setdefault(str(int(target)), set()).add(int(source))

    unlocks_path = os.path.join(out_dir, "unlocks.json")
    size = dump(unlocks_path, {
        "bySection": by_section,
        "prerequisites": {key: sorted(value) for key, value in prerequisites.items()},
        "chapters": chapters,
        "chapterPrerequisites": {key: sorted(value) for key, value in chapter_prereq.items()},
        "counts": {"sections": len(by_section), "prerequisiteEdges": sum(len(v) for v in prerequisites.values()),
                   "chapters": len(chapters), "chapterEdges": sum(len(v) for v in chapter_prereq.values())},
    })
    print("unlocks.json sections=%d chapters=%d bytes=%d" % (len(by_section), len(chapters), size))

    # 完整任务表
    quests = {}
    for key, row in (tables.get("questBattle") or {}).items():
        quest_id = as_int(row.get("questBattleId") or key)
        if not quest_id:
            continue
        missions = []
        for index in range(1, 4):
            master = row.get("missionMaster%d" % index)
            missions.append({
                "code": as_int(row.get("mission%d" % index)),
                "name": (master or {}).get("name") if isinstance(master, dict) else None,
                "description": (master or {}).get("description") if isinstance(master, dict) else None,
            })
        quests[str(quest_id)] = {
            "questBattleId": quest_id,
            "sectionId": as_int(row.get("sectionId")),
            "sectionIndex": as_int(row.get("sectionIndex")),
            "questBattleType": row.get("questBattleType"),
            "bossFlag": bool(row.get("bossFlag")),
            "ap": as_int(row.get("consumeType") and 0 or 0) or None,
            "exp": as_int(row.get("exp")),
            "riche": as_int(row.get("riche")),
            "missions": missions,
        }
    quests_path = os.path.join(out_dir, "quests-full.json")
    size = dump(quests_path, {"quests": quests,
                              "counts": {"quests": len(quests), "source": "catalog MCATBIN1"}})
    print("quests-full.json quests=%d bytes=%d" % (len(quests), size))
    return 0


if __name__ == "__main__":
    sys.exit(main())
