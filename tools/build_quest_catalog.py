"""从数据包提取完整剧情任务表（存档里只有已解锁的那部分）。

扫描 MAGIA 源码/数据包 offline/data/*.json，收集所有
{"questBattleId": int, "sectionId": int, ...} 记录，合并成：
  data/quests.json
    quests:   {questBattleId: {sectionId, questType, missions[3], ap, difficulty}}
    sections: {sectionId: [questBattleId, ...]}
    counts:   {quests, sections}

任务条件文本取自记录里的 mission1..3 与 missionMaster1..3.description（官方文案）。
"""

import argparse
import json
import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def merge_quest(target, node):
    qid = node.get("questBattleId")
    section_id = node.get("sectionId")
    if not isinstance(qid, int) or isinstance(qid, bool) or not isinstance(section_id, int):
        return False
    missions = []
    for index in (1, 2, 3):
        code = node.get("mission%d" % index)
        master = node.get("missionMaster%d" % index) or {}
        text = master.get("description") if isinstance(master, dict) else None
        missions.append({"code": code if isinstance(code, str) else None, "text": text})
    current = target.get(qid)
    candidate = {
        "sectionId": section_id,
        "sectionIndex": node.get("sectionIndex") if isinstance(node.get("sectionIndex"), int) else None,
        "bossFlag": bool(node.get("bossFlag")),
        "questType": node.get("questBattleType") if isinstance(node.get("questBattleType"), str) else None,
        "missions": missions,
        "ap": node.get("ap") if isinstance(node.get("ap"), int) else None,
        "difficulty": node.get("difficulty") if isinstance(node.get("difficulty"), int) else None,
    }
    if current is None:
        target[qid] = candidate
        return True
    # 保留信息更全的一份
    score_new = sum(1 for m in candidate["missions"] if m["code"] or m["text"]) + (1 if candidate["sectionIndex"] else 0)
    score_old = sum(1 for m in current["missions"] if m["code"] or m["text"]) + (1 if current.get("sectionIndex") else 0)
    if score_new > score_old:
        target[qid] = candidate
    return False


def main(argv=None):
    parser = argparse.ArgumentParser(description="提取完整剧情任务表")
    parser.add_argument("--zip", required=True)
    parser.add_argument("--max-mb", type=float, default=60)
    args = parser.parse_args(argv)

    limit = int(args.max_mb * 1024 * 1024)
    quests = {}
    files = 0
    archive = zipfile.ZipFile(args.zip)
    for name in archive.namelist():
        if not (name.startswith("offline/data/") and name.endswith(".json")):
            continue
        info = archive.getinfo(name)
        if info.file_size > limit:
            continue
        try:
            raw = archive.read(name)
        except Exception:
            continue
        if b'"questBattleId"' not in raw:
            continue
        try:
            data = json.loads(raw)
        except Exception:
            continue
        files += 1
        stack = [data]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                if "questBattleId" in node:
                    merge_quest(quests, node)
                stack.extend(node.values())
            elif isinstance(node, list):
                stack.extend(node)
        del data

    sections = {}
    for qid, row in quests.items():
        sections.setdefault(row["sectionId"], []).append(qid)
    for section_id in sections:
        sections[section_id].sort()

    out = {"quests": {str(k): v for k, v in sorted(quests.items())},
           "sections": {str(k): v for k, v in sorted(sections.items())},
           "counts": {"quests": len(quests), "sections": len(sections), "files": files}}
    path = os.path.join(ROOT, "data", "quests.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(out, handle, ensure_ascii=False, separators=(",", ":"))
    print("扫描文件", files, "任务", len(quests), "小节", len(sections))
    with_missions = sum(1 for row in quests.values() if any(m["code"] for m in row["missions"]))
    print("带任务条件", with_missions)
    return 0


if __name__ == "__main__":
    sys.exit(main())
