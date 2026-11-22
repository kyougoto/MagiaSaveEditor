"""从 MCATBIN1 导出完整的卡片/结晶基础数值（补全旧 masters 缺的条目）。

旧 data/cards.json（445）与 data/pieces.json（915）来自 offline/data 的快照，不全；
MCATBIN1 的 tables.card（525）与 tables.piece（1041）才是全量。

输出：data/cards-full.json、data/pieces-full.json（字段与 masters.py 兼容）
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

    cards = {}
    for key, row in (tables.get("card") or {}).items():
        card_id = as_int(row.get("cardId") or key)
        if not card_id:
            continue
        cards[str(card_id)] = {
            "cardId": card_id,
            "rank": row.get("rank"),
            "growthType": row.get("growthType"),
            "attack": as_int(row.get("attack")),
            "defense": as_int(row.get("defense")),
            "hp": as_int(row.get("hp")),
            "attributeId": row.get("attributeId"),
            "charaNo": as_int(row.get("charaNo")),
            "cardName": row.get("cardName"),
            "initialType": row.get("initialType"),
            "miniCharaNo": as_int(row.get("miniCharaNo")),
        }
    size = dump(os.path.join(out_dir, "cards-full.json"),
                {"cards": cards, "counts": {"cards": len(cards), "source": "catalog MCATBIN1"}})
    print("cards-full.json cards=%d bytes=%d" % (len(cards), size))

    pieces = {}
    for key, row in (tables.get("piece") or {}).items():
        piece_id = as_int(row.get("pieceId") or key)
        if not piece_id:
            continue
        pieces[str(piece_id)] = {
            "pieceId": piece_id,
            "rank": row.get("rank"),
            "attack": as_int(row.get("attack")),
            "defense": as_int(row.get("defense")),
            "hp": as_int(row.get("hp")),
            "attributeId": row.get("attributeId"),
            "pieceType": row.get("pieceType"),
            "pieceName": row.get("pieceName"),
            "skillId": as_int(row.get("skillId")),
            "skillId2": as_int(row.get("skillId2")),
        }
    size = dump(os.path.join(out_dir, "pieces-full.json"),
                {"pieces": pieces, "counts": {"pieces": len(pieces), "source": "catalog MCATBIN1"}})
    print("pieces-full.json pieces=%d bytes=%d" % (len(pieces), size))
    return 0


if __name__ == "__main__":
    sys.exit(main())
