"""导出记忆结晶详情（描述 / 技能 / 稀有度 / 种类）。

数据来源：
  <APK>/assets/magia/offline/catalog.json  MCATBIN1：tables.piece（description / pieceKind / skillId / pieceSkill）
  <APK_DATA>/files/magica/js/libs/pieceList.json     中文名与描述
  <APK_DATA>/files/magica/js/libs/pieceSkillMap.json 技能中文名与简描述

输出：data/pieces-detail.json
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
    table = root["tables"]["piece"]
    zh_list = {str(row.get("pieceId")): row
               for row in load_json(os.path.join(libs_dir, "pieceList.json"), [])}
    skills = load_json(os.path.join(libs_dir, "pieceSkillMap.json"), {})

    pieces = {}
    unnamed_skill = 0
    for key, row in table.items():
        piece_id = as_int(row.get("pieceId") or key)
        if not piece_id:
            continue
        local = zh_list.get(str(piece_id)) or {}
        skill_rows = []
        for index in ("", "2"):
            skill_id = as_int(row.get("skillId" + index))
            if not skill_id:
                continue
            info = skills.get(str(skill_id)) or {}
            if not info:
                unnamed_skill += 1
            skill_rows.append({
                "skillId": skill_id,
                "name": normalize(info.get("name")),
                "description": normalize(info.get("shortDescription")),
                "arts": len((row.get("pieceSkill" + index) or {}) or {}) if isinstance(
                    row.get("pieceSkill" + index), dict) else 0,
            })
        pieces[str(piece_id)] = {
            "pieceId": piece_id,
            "name": local.get("pieceName") or row.get("pieceName"),
            "rank": row.get("rank"),
            "type": row.get("pieceType"),
            "kind": row.get("pieceKind"),
            "attribute": row.get("attributeId"),
            "description": normalize(local.get("description") or row.get("description")),
            "illustrator": row.get("illustrator") or local.get("illustrator"),
            "skills": skill_rows,
        }

    path = os.path.join(out_dir, "pieces-detail.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"pieces": pieces,
                   "counts": {"pieces": len(pieces), "skills": sum(len(p["skills"]) for p in pieces.values()),
                              "unnamedSkills": unnamed_skill}},
                  handle, ensure_ascii=False, separators=(",", ":"))
    print("pieces-detail.json pieces=%d unnamedSkills=%d bytes=%d"
          % (len(pieces), unnamed_skill, os.path.getsize(path)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
