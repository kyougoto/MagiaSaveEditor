"""往返验证：解包 → 重打包 → 再解包，逐层比对客户端协议不变量。"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from magiasave import archive as archive_mod  # noqa: E402
from magiasave import jsjson, slot, zipfmt  # noqa: E402
from magiasave.model import Editor  # noqa: E402

SAMPLE = os.environ.get("MAGIA_SAMPLE", r"H:/magia_server/magia-save-chino-1794718180238.zip")
WORK = os.path.join(ROOT, "_work")


def check(label, condition, detail=""):
    print(("PASS " if condition else "FAIL ") + label + ((" :: " + detail) if detail else ""))
    if not condition:
        raise SystemExit(1)


def main():
    os.makedirs(WORK, exist_ok=True)
    arc = archive_mod.SlotArchive.load(SAMPLE)
    print(json.dumps(arc.summary(), ensure_ascii=False, indent=1)[:1200])

    # 1) head/part 协议：重分片结果必须满足客户端读取端全部约束
    parts = slot.split_parts(arc.stored_raw, arc.revision, limit=slot.protocol.MAX_PARTS)
    check("分片数量与 head 一致", parts is not None and len(parts) == arc.head["parts"],
          "%s vs %s" % (len(parts) if parts else None, arc.head["parts"]))
    check("重分片拼接等价", "".join(data for _r, _i, data in parts) == arc.stored_raw)
    for index, (rev, idx, data) in enumerate(parts):
        envelope = slot.part_envelope_bytes(rev, idx, data)
        check("第 %d 片 envelope <= 512KB" % index, envelope <= slot.protocol.PART_BYTES,
              "%d bytes" % envelope)
        original = arc.state["off3_%s_%s_%d" % (arc.template, arc.head["bank"], index)]["data"]
        if data != original:
            print("  说明：客户端原片 %d chars，重排 %d chars（客户端 split 的线性收缩会过冲，"
                  "两者都在 512KB 内，读取端不要求片内贪心）" % (len(original), len(data)))
    check("head.bytes 与拼接结果一致", jsjson.utf8_len(arc.stored_raw) == arc.head["bytes"])

    # 2) 语义视图
    editor = Editor(arc)
    overview = editor.overview()
    check("玩家名读取", bool(overview["player"]["loginName"]))
    check("道具名称来自主数据", editor.catalog.item_name("YELL") == "协助Pt",
          editor.catalog.item_name("YELL"))
    check("货币名称来自主数据", editor.catalog.item_name("MONEY") == "魔法石")
    check("角色名称来自主数据", editor.catalog.chara_name(1001) == "环彩羽",
          editor.catalog.chara_name(1001))
    print("道具前 5:", [row["name"] for row in editor.items_view(limit=5)["rows"]])
    print("角色前 3:", [row["name"] for row in editor.charas_view(limit=3)["rows"]])

    # 3) 编辑 + 保存 + 回读
    ops = [
        {"op": "item.set", "itemId": "MONEY", "quantity": 123456},
        {"op": "status.set", "statusId": "ACP", "point": 120, "maxPoint": 200},
        {"op": "quest.bulk", "cleared": True, "missions": True, "onlyUncleared": True},
    ]
    result = editor.apply(ops)
    print("编辑影响路径数:", len(result["changed"]), "noop:", result["noop"])

    BEFORE_REVISION = arc.revision
    BEFORE_BANK = arc.head["bank"]
    out_path = os.path.join(WORK, "edited.zip")
    info = editor.save(out_path, label="chino-edited")
    print("写出:", json.dumps(info, ensure_ascii=False))

    reloaded = archive_mod.SlotArchive.load(out_path)
    check("revision 递增", reloaded.revision == BEFORE_REVISION + 1,
          "%s -> %s" % (BEFORE_REVISION, reloaded.revision))
    check("bank 交替", reloaded.head["bank"] != BEFORE_BANK,
          "%s -> %s" % (BEFORE_BANK, reloaded.head["bank"]))
    money = {row["itemId"]: row for row in reloaded.profile["state"]["userItemList"]}
    check("写入值回读一致", money["MONEY"]["quantity"] == 123456, str(money["MONEY"]["quantity"]))
    status = {row["statusId"]: row for row in reloaded.profile["state"]["userStatusList"]}
    check("AP 数值回读", status["ACP"]["point"] == 120 and status["MAX_ACP"]["point"] == 200,
          "%s/%s" % (status["ACP"]["point"], status["MAX_ACP"]["point"]))
    cleared = sum(1 for row in reloaded.profile["state"]["userQuestBattleList"] if row.get("cleared") is True)
    print("已通关任务数:", cleared)

    # 4) 严格 zip 校验器复查（模拟客户端 inspect）
    with open(out_path, "rb") as handle:
        records = zipfmt.inspect(handle.read())
    check("zip 通过客户端同款结构校验", "manifest.json" in records and len(records) >= 2,
          "entries=%d" % len(records))

    # 5) json-shapes-v1 编解码往返
    raw = jsjson.dumps(arc.profile)
    packed = slot.encode_profile(raw, arc.profile)
    value, canonical = slot.decode_profile(packed)
    check("shapes 编解码等价", jsjson.dumps(value) == raw,
          "packed=%d raw=%d" % (jsjson.utf8_len(packed), jsjson.utf8_len(raw)))
    print("压缩率: %.1f%%" % (100.0 * jsjson.utf8_len(packed) / jsjson.utf8_len(raw)))

    print("\n全部检查通过")


if __name__ == "__main__":
    main()
