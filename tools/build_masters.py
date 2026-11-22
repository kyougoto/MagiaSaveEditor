"""从数据包聚合卡片 / 记忆结晶的基础数值表（成长推算的输入）。

来源：MAGIA-1.6.4-b1713001033-current-source-d566da53.zip 内 offline/data/*.json
这些文件里内嵌了官方 card / piece 定义（rank、growthType、attack、defense、hp 等），
本脚本把它们扫描合并成 data/cards.json 与 data/pieces.json。

刻意不做任何推测：只收录同时具备 cardId/pieceId、rank、attack/defense/hp 的对象。

用法：
  python tools/build_masters.py --zip <source.zip> [--max-mb 40]
"""

import argparse
import json
import os
import sys
import zipfile

RANKS = ("RANK_1", "RANK_2", "RANK_3", "RANK_4", "RANK_5")


def is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def walk(node, visit):
    stack = [node]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            visit(current)
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)


def main(argv=None):
    parser = argparse.ArgumentParser(description="聚合 card/piece 基础数值表")
    parser.add_argument("--zip", required=True)
    parser.add_argument("--max-mb", type=float, default=40)
    parser.add_argument("--out", default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"))
    args = parser.parse_args(argv)

    limit = int(args.max_mb * 1024 * 1024)
    archive = zipfile.ZipFile(args.zip)
    names = [n for n in archive.namelist() if n.startswith("offline/data/") and n.endswith(".json")]
    cards = {}
    pieces = {}
    scanned = 0
    skipped = 0

    for name in names:
        info = archive.getinfo(name)
        if info.file_size > limit:
            skipped += 1
            continue
        try:
            raw = archive.read(name)
        except Exception:
            skipped += 1
            continue
        if b'"growthType"' not in raw and b'"pieceId"' not in raw:
            continue
        try:
            data = json.loads(raw)
        except Exception:
            skipped += 1
            continue
        scanned += 1

        def visit(node, source=name):
            card_id = node.get("cardId")
            if (is_int(card_id) and node.get("rank") in RANKS and isinstance(node.get("growthType"), str)
                    and is_int(node.get("attack")) and is_int(node.get("defense")) and is_int(node.get("hp"))
                    and node.get("growthType") in ("BALANCE", "ATTACK", "DEFENSE", "HP", "ATKDEF", "ATKHP", "DEFHP")):
                std = str(card_id)
                if std not in cards:
                    cards[std] = {
                        "cardId": card_id,
                        "rank": node["rank"],
                        "growthType": node["growthType"],
                        "attack": node["attack"],
                        "defense": node["defense"],
                        "hp": node["hp"],
                        "attributeId": node.get("attributeId"),
                        "charaNo": node.get("charaNo"),
                        "cardName": node.get("cardName"),
                        "source": source,
                    }
            piece_id = node.get("pieceId")
            if (is_int(piece_id) and node.get("rank") in ("RANK_1", "RANK_2", "RANK_3", "RANK_4")
                    and is_int(node.get("attack")) and is_int(node.get("defense")) and is_int(node.get("hp"))):
                std = str(piece_id)
                if std not in pieces:
                    pieces[std] = {
                        "pieceId": piece_id,
                        "rank": node["rank"],
                        "attack": node["attack"],
                        "defense": node["defense"],
                        "hp": node["hp"],
                        "attributeId": node.get("attributeId"),
                        "pieceType": node.get("pieceType"),
                        "pieceName": node.get("pieceName"),
                        "skillId": node.get("skillId"),
                        "skillId2": node.get("skillId2"),
                        "source": source,
                    }

        walk(data, visit)
        del data

    out_dir = os.path.abspath(args.out)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "cards.json"), "w", encoding="utf-8") as handle:
        handle.write(json.dumps({"generated": True, "count": len(cards), "cards": cards},
                                ensure_ascii=False, separators=(",", ":")))
    with open(os.path.join(out_dir, "pieces.json"), "w", encoding="utf-8") as handle:
        handle.write(json.dumps({"generated": True, "count": len(pieces), "pieces": pieces},
                                ensure_ascii=False, separators=(",", ":")))
    print("files scanned:", scanned, "skipped:", skipped)
    print("cards:", len(cards), "pieces:", len(pieces))
    ranks = {}
    for row in cards.values():
        ranks[row["rank"]] = ranks.get(row["rank"], 0) + 1
    print("card ranks:", ranks)
    return 0


if __name__ == "__main__":
    sys.exit(main())
