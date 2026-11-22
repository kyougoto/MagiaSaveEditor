"""聚合精神强化（Spirit Tree）节点表。

来源：offline/data/*.json 中的 charaEnhancementCell 表与 mentalEnhancement.groups
（语义见 offline/src/mental-enhancement.js：enhancementType → 角色 addend*/emotionSkillList，
 needOpenedCellId 是前置节点）。

输出 data/spirit.json：{cells: {cellId: {...}}, groups: {groupId: [cellId...]}, charaGroup: {charaId: groupId}}
"""

import argparse
import json
import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main(argv=None):
    parser = argparse.ArgumentParser(description="聚合精神强化节点表")
    parser.add_argument("--zip", required=True)
    parser.add_argument("--max-mb", type=float, default=60)
    args = parser.parse_args(argv)

    limit = int(args.max_mb * 1024 * 1024)
    cells = {}
    groups = {}
    chara_group = {}
    files = 0
    with zipfile.ZipFile(args.zip) as archive:
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
            if b"charaEnhancementCell" not in raw and b"enhancementGroupId" not in raw:
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
                    table = node.get("charaEnhancementCell")
                    if isinstance(table, dict):
                        for key, row in table.items():
                            if isinstance(row, dict) and row.get("charaEnhancementCellId") is not None:
                                cells.setdefault(row["charaEnhancementCellId"], {
                                    "cellId": row.get("charaEnhancementCellId"),
                                    "groupId": row.get("groupId"),
                                    "type": row.get("enhancementType"),
                                    "value": row.get("effectValue"),
                                    "needOpenedCellId": row.get("needOpenedCellId"),
                                    "column": row.get("columnNo"),
                                    "row": row.get("rowNo"),
                                    "price": row.get("openPrice"),
                                })
                    mental = node.get("mentalEnhancement")
                    if isinstance(mental, dict) and isinstance(mental.get("groups"), dict):
                        for key, ids in mental["groups"].items():
                            if isinstance(ids, list) and key not in groups:
                                groups[key] = ids
                    chara = node.get("chara")
                    if isinstance(chara, dict):
                        for key, row in chara.items():
                            if isinstance(row, dict) and row.get("enhancementGroupId") is not None:
                                chara_group.setdefault(str(row.get("id") or key), row["enhancementGroupId"])
                    stack.extend(node.values())
                elif isinstance(node, list):
                    stack.extend(node)
            del data

    out = {"cells": {str(k): v for k, v in sorted(cells.items())},
           "groups": {str(k): v for k, v in sorted(groups.items())},
           "charaGroup": dict(sorted(chara_group.items())),
           "counts": {"cells": len(cells), "groups": len(groups), "characters": len(chara_group), "files": files}}
    path = os.path.join(ROOT, "data", "spirit.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(out, handle, ensure_ascii=False, separators=(",", ":"))
    print("文件", files, "节点", len(cells), "分组", len(groups), "角色", len(chara_group))
    sample = next(iter(cells.values()), None)
    print("节点样例:", json.dumps(sample, ensure_ascii=False)[:240])
    return 0


if __name__ == "__main__":
    sys.exit(main())
