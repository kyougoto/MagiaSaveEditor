"""导出阵型（formationSheet）与每格加成。

数据来源：
  <APK>/assets/magia/offline/catalog.json  MCATBIN1：tables.formationSheet（id / placeSkill1..9）
  <APK_DATA>/files/magica/js/libs/formationSheetList.json  中文名与说明

输出：data/formations.json
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from parse_compact_catalog import CompactCatalog, as_int  # noqa: E402

DEFAULT_CATALOG = os.path.join(os.path.dirname(ROOT), "_re", "catalog_full.json")
DEFAULT_LIBS = r"H:/magia_server/io.kamihama.totentanz/files/magica/js/libs"


def main(argv=None):
    argv = argv or sys.argv
    catalog_path = argv[1] if len(argv) > 1 else DEFAULT_CATALOG
    libs_dir = argv[2] if len(argv) > 2 else DEFAULT_LIBS
    out_dir = os.path.join(ROOT, "data")
    os.makedirs(out_dir, exist_ok=True)

    root = CompactCatalog(open(catalog_path, "rb").read()).root_value()
    table = root["tables"].get("formationSheet") or {}
    zh = {}
    try:
        with open(os.path.join(libs_dir, "formationSheetList.json"), encoding="utf-8") as handle:
            for row in json.load(handle):
                zh[str(as_int(row.get("id")))] = row
    except FileNotFoundError:
        zh = {}

    formations = {}
    for key, row in table.items():
        formation_id = as_int(row.get("id") or key)
        if not formation_id:
            continue
        slots = []
        skills = {}
        for index in range(1, 10):
            skill = row.get("placeSkill%d" % index)
            if not isinstance(skill, dict) or not skill:
                continue
            slots.append(index)
            name = skill.get("shortDescription") or skill.get("name")
            if name and name != "0":
                skills[str(index)] = {
                    "name": skill.get("name"),
                    "description": skill.get("shortDescription"),
                    "type": skill.get("type"),
                }
        local = zh.get(str(formation_id)) or {}
        formations[str(formation_id)] = {
            "id": formation_id,
            "name": local.get("name") or row.get("name"),
            "description": local.get("description") or row.get("description"),
            "slots": slots,
            "skills": skills,
        }

    path = os.path.join(out_dir, "formations.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"formations": formations,
                   "counts": {"formations": len(formations),
                              "maxSlots": max((len(f["slots"]) for f in formations.values()), default=0)}},
                  handle, ensure_ascii=False, separators=(",", ":"))
    print("formations.json formations=%d bytes=%d"
          % (len(formations), os.path.getsize(path)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
