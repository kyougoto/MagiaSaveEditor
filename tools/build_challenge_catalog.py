"""聚合数据包里的挑战定义（challenge master）。

来源：offline/data/*.json 中的 "challenges" 表，条目形如
  {"id":121819,"groupId":253,"bean":"EVENT_QUEST_CLEAR","parameter":"52183010","count":1,
   "displayName":"通关挑战BATTLE10", ...}
其中 count 是**官方目标次数**，bean 是条件类型，parameter 是条件参数。
这是权威来源，不再从界面文案里猜数字。

输出 data/challenges.json：{challenges: {id: {count, bean, parameter, displayName, groupId}}, counts}
"""

import argparse
import json
import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main(argv=None):
    parser = argparse.ArgumentParser(description="聚合挑战定义")
    parser.add_argument("--zip", required=True)
    parser.add_argument("--max-mb", type=float, default=60)
    args = parser.parse_args(argv)

    limit = int(args.max_mb * 1024 * 1024)
    table = {}
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
            if b'"challenges"' not in raw:
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
                    rows = node.get("challenges")
                    if isinstance(rows, dict):
                        for key, row in rows.items():
                            if isinstance(row, dict) and row.get("id") is not None:
                                table.setdefault(row["id"], {
                                    "count": row.get("count") if isinstance(row.get("count"), int) else None,
                                    "bean": row.get("bean"),
                                    "parameter": row.get("parameter"),
                                    "displayName": row.get("displayName"),
                                    "groupId": row.get("groupId"),
                                    "source": name,
                                })
                    stack.extend(node.values())
                elif isinstance(node, list):
                    stack.extend(node)
            del data

    out = {"challenges": {str(key): value for key, value in sorted(table.items())},
           "counts": {"challenges": len(table), "files": files}}
    path = os.path.join(ROOT, "data", "challenges.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(out, handle, ensure_ascii=False, separators=(",", ":"))
    print("扫描文件", files, "挑战定义", len(table))
    with_count = sum(1 for row in table.values() if row["count"])
    print("带目标次数", with_count)
    return 0


if __name__ == "__main__":
    sys.exit(main())
