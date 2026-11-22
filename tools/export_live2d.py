"""从 MCATBIN1 导出「角色 → 可用衣装（live2dId）」表。

libs 的衣装清单与主数据不完全一致（例如 1015 的 "51" 在 master 里没有），
游戏端按 master 校验 userLive2dList，写了不存在的编号会让客户端加载失败。
所以编辑器以这份表为准，只允许添加 master 里存在的衣装。

输出：data/live2d.json
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from parse_compact_catalog import CompactCatalog, as_int  # noqa: E402

DEFAULT_CATALOG = os.path.join(os.path.dirname(ROOT), "_re", "catalog_full.json")


def main(argv=None):
    argv = argv or sys.argv
    catalog_path = argv[1] if len(argv) > 1 else DEFAULT_CATALOG
    root = CompactCatalog(open(catalog_path, "rb").read()).root_value()
    table = root["tables"].get("live2d") or {}
    by_chara = {}
    for key, row in table.items():
        if not isinstance(row, dict):
            continue
        chara_id = as_int(row.get("charaId"))
        live2d_id = str(row.get("live2dId") or "")
        if not chara_id or not live2d_id:
            continue
        entry = by_chara.setdefault(str(chara_id), {})
        entry[live2d_id] = {
            "default": bool(row.get("defaultOpened")),
            "description": row.get("description"),
        }
    payload = {"chara": {key: dict(sorted(value.items())) for key, value in sorted(by_chara.items())},
               "counts": {"chara": len(by_chara), "costumes": sum(len(v) for v in by_chara.values()),
                          "source": "catalog MCATBIN1 tables.live2d"}}
    target = os.path.join(ROOT, "data", "live2d.json")
    with open(target, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
    print("live2d.json chara=%d costumes=%d bytes=%d"
          % (len(by_chara), payload["counts"]["costumes"], os.path.getsize(target)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
