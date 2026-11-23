"""导出「角色 → 魔女化身」映射（含中文名/称号/简介）。

数据来源：
  <APK>/assets/magia/offline/catalog.json  MCATBIN1：tables.chara（defaultCardId / evolutionCardId1..4）、
                                          tables.card[].doppel（内嵌 doppelId）
  <APK_DATA>/files/magica/js/libs/doppelList.json  中文 name / title / description

输出：data/doppels.json
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from parse_compact_catalog import CompactCatalog, as_int  # noqa: E402
from zh import normalize  # noqa: E402

DEFAULT_CATALOG = os.path.join(os.path.dirname(ROOT), "_re", "catalog_full.json")
DEFAULT_LIBS = r"H:/magia_server/io.kamihama.totentanz/files/magica/js/libs"


def main(argv=None):
    argv = argv or sys.argv
    catalog_path = argv[1] if len(argv) > 1 else DEFAULT_CATALOG
    libs_dir = argv[2] if len(argv) > 2 else DEFAULT_LIBS
    out_dir = os.path.join(ROOT, "data")
    os.makedirs(out_dir, exist_ok=True)

    root = CompactCatalog(open(catalog_path, "rb").read()).root_value()
    tables = root["tables"]
    cards = tables["card"]
    zh = {}
    try:
        with open(os.path.join(libs_dir, "doppelList.json"), encoding="utf-8") as handle:
            for row in json.load(handle):
                zh[str(as_int(row.get("id")))] = row
    except FileNotFoundError:
        zh = {}

    chara_doppel = {}
    for key, row in tables["chara"].items():
        chara_id = as_int(row.get("id") or key)
        if not chara_id:
            continue
        chain = [as_int(row.get("defaultCardId"))]
        for index in range(1, 6):
            if row.get("evolutionCardId%d" % index):
                chain.append(as_int(row.get("evolutionCardId%d" % index)))
        found = None
        for card_id in chain:
            if not card_id:
                continue
            doppel = (cards.get(str(card_id)) or {}).get("doppel")
            if isinstance(doppel, dict) and doppel.get("id"):
                found = (card_id, as_int(doppel.get("id")))
                break
        if not found:
            continue
        card_id, doppel_id = found
        local = zh.get(str(doppel_id)) or {}
        chara_doppel[str(chara_id)] = {
            "doppelId": doppel_id,
            "cardId": card_id,
            "name": normalize(local.get("name")),
            "title": normalize(local.get("title")),
            "description": normalize(local.get("description")),
            "designer": local.get("designer"),
        }

    path = os.path.join(out_dir, "doppels.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"charaDoppel": chara_doppel,
                   "counts": {"characters": len(chara_doppel), "source": "catalog MCATBIN1"}},
                  handle, ensure_ascii=False, separators=(",", ":"))
    missing = sum(1 for row in chara_doppel.values() if not row.get("name"))
    print("doppels.json chara=%d unnamed=%d bytes=%d"
          % (len(chara_doppel), missing, os.path.getsize(path)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
