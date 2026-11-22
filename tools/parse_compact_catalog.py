"""解析私服的紧凑 master 格式 MCATBIN1（实现见 CNCompactCatalog.java）。

格式：
  magic 8B "MCATBIN1" | count i32 | root i32 | length i32 | data[length]
  节点按 id 顺序紧凑排列，子节点 id 必须小于父节点（forward reference 校验）。
  type: 0 null / 1 false / 2 true / 3 double(8B BE) / 4 string(u32 len + utf8) /
        5 array(u32 n + n*u32) / 6 object(u32 n + n*(keyId,valueId) [+ n*u32 索引])
"""

import json
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAGIC = b"MCATBIN1"


def as_int(value):
    """catalog 里的数字统一是 float（如 3.0），导出前转回整数。"""
    if isinstance(value, bool):
        return value
    if isinstance(value, float) and value == int(value):
        return int(value)
    return value


class CompactCatalog:
    def __init__(self, blob):
        if blob[:8] != MAGIC:
            raise ValueError("not MCATBIN1")
        count, root, length = struct.unpack(">iii", blob[8:20])
        if not (1 <= count <= 2_000_000) or not (0 <= root < count) or length < 1:
            raise ValueError("bad header")
        self.data = blob[20:20 + length]
        if len(self.data) != length:
            raise ValueError("short payload")
        self.count = count
        self.root = root
        self.offsets = [0] * count
        p = 0
        for node_id in range(count):
            self.offsets[node_id] = p
            type_ = self.data[p]
            p += 1
            if type_ <= 2:
                continue
            if type_ == 3:
                p += 8
                continue
            if type_ == 4:
                n = struct.unpack_from(">I", self.data, p)[0]
                p += 4 + n
                continue
            if type_ in (5, 6):
                n = struct.unpack_from(">I", self.data, p)[0]
                p += 4
                if type_ == 5:
                    p += n * 4
                else:
                    p += n * 8 + (n * 4 if n > 16 else 0)
                continue
            raise ValueError("bad type %d at %d" % (type_, p - 1))
        if p != len(self.data):
            raise ValueError("trailing payload")
        self._cache = {}

    def _u32(self, p):
        return struct.unpack_from(">I", self.data, p)[0]

    def value(self, node_id):
        cached = self._cache.get(node_id)
        if cached is not None:
            return cached
        p = self.offsets[node_id]
        type_ = self.data[p]
        if type_ == 0:
            out = None
        elif type_ == 1:
            out = False
        elif type_ == 2:
            out = True
        elif type_ == 3:
            out = struct.unpack_from(">d", self.data, p + 1)[0]
        elif type_ == 4:
            n = self._u32(p + 1)
            out = self.data[p + 5:p + 5 + n].decode("utf-8")
        elif type_ == 5:
            n = self._u32(p + 1)
            out = [self.value(self._u32(p + 5 + i * 4)) for i in range(n)]
        elif type_ == 6:
            n = self._u32(p + 1)
            base = p + 5
            out = {}
            for i in range(n):
                key_id = self._u32(base + i * 8)
                value_id = self._u32(base + i * 8 + 4)
                key = self.value(key_id)
                out[key] = self.value(value_id)
        else:
            raise ValueError("bad type")
        self._cache[node_id] = out
        return out

    def root_value(self):
        return self.value(self.root)


def main(argv=None):
    path = argv[1] if argv and len(argv) > 1 else os.path.join(ROOT, "_re", "catalog_full.json")
    blob = open(path, "rb").read()
    catalog = CompactCatalog(blob)
    print("节点数", catalog.count, "根 id", catalog.root, "数据", len(catalog.data), "字节")
    root = catalog.root_value()
    print("顶层键", list(root.keys())[:12])
    tables = root.get("tables") or {}
    print("tables", len(tables))
    for key in ("charaEnhancementCell", "chara", "card", "emotionSkill", "challenge", "item", "piece", "gift"):
        table = tables.get(key)
        print("   %-22s %s" % (key, len(table) if isinstance(table, (dict, list)) else type(table).__name__))
    mental = root.get("mentalEnhancement") or {}
    groups = mental.get("groups") if isinstance(mental, dict) else None
    if isinstance(groups, dict):
        print("   mentalEnhancement.groups", len(groups), "最大组", max(len(v) for v in groups.values()))

    out_dir = os.path.join(ROOT, "data")
    os.makedirs(out_dir, exist_ok=True)

    # 精神强化
    cells_raw = tables.get("charaEnhancementCell") or {}
    cells = {}
    for key, row in cells_raw.items():
        if not isinstance(row, dict):
            continue
        gifts = []
        for index in range(1, 7):
            gift = row.get("openGift%d" % index)
            if isinstance(gift, dict):
                gifts.append({"id": gift.get("id"), "name": gift.get("name"),
                              "price": gift.get("price"), "rank": gift.get("rank")})
        cells[str(row.get("charaEnhancementCellId") or key)] = {
            "cellId": as_int(row.get("charaEnhancementCellId")),
            "groupId": as_int(row.get("groupId")),
            "type": row.get("enhancementType"),
            "value": as_int(row.get("effectValue")),
            "need": as_int(row.get("needOpenedCellId")),
            "needCC": as_int(row.get("needCC")),
            "x": row.get("pointX"), "y": row.get("pointY"),
            "gifts": gifts,
        }
    groups_out = {}
    if isinstance(groups, dict):
        for key, ids in groups.items():
            groups_out[str(as_int(key))] = [int(as_int(x)) for x in ids]
    chara_group = {}
    for key, row in (tables.get("chara") or {}).items():
        if isinstance(row, dict) and row.get("enhancementGroupId") is not None:
            chara_group[str(as_int(row.get("id")) or key)] = as_int(row.get("enhancementGroupId"))
    with open(os.path.join(out_dir, "spirit.json"), "w", encoding="utf-8") as handle:
        json.dump({"cells": cells, "groups": groups_out, "charaGroup": chara_group,
                   "counts": {"cells": len(cells), "groups": len(groups_out),
                              "characters": len(chara_group), "source": "catalog MCATBIN1"}},
                  handle, ensure_ascii=False, separators=(",", ":"))
    print("spirit.json 节点", len(cells), "组", len(groups_out), "角色", len(chara_group))

    # 挑战
    challenges = {}
    for key, row in (tables.get("challenge") or {}).items():
        if not isinstance(row, dict):
            continue
        challenges[str(as_int(row.get("id")) or key)] = {
            "count": as_int(row.get("count")),
            "bean": row.get("bean"),
            "parameter": row.get("parameter"),
            "displayName": row.get("displayName"),
            "groupId": row.get("groupId"),
            "source": "catalog MCATBIN1",
        }
    with open(os.path.join(out_dir, "challenges.json"), "w", encoding="utf-8") as handle:
        json.dump({"challenges": challenges,
                   "counts": {"challenges": len(challenges), "source": "catalog MCATBIN1"}},
                  handle, ensure_ascii=False, separators=(",", ":"))
    print("challenges.json 定义", len(challenges),
          "带 count", sum(1 for row in challenges.values() if row["count"] is not None))
    for probe in ("15005", "15001", "16001", "17001", "18001", "19001", "6001"):
        row = challenges.get(probe)
        print("   ", probe, "->", row["count"] if row else "MISS", (row or {}).get("displayName"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
