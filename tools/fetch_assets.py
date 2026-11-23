"""把编辑器要用到的素材图复制进 magia_save_editor/assets/。

运行后编辑器完全自包含，不再依赖 17G 游戏数据目录。

素材来源（APK 数据目录）：
  madomagi/resource/image_native/gift/item_gift_<giftId>.png
  madomagi/resource/image_native/chara/chara_<charaId>_h.png
  madomagi/resource/image_native/card/image/card_<cardId>_s.png
  madomagi/resource/image_native/memoria/memoria_<pieceId>_s.png
  magica/resource/image_web/item/main/<itemCode 小写>.png

用法：
  python tools/fetch_assets.py --data-root "H:/magia_server/io.kamihama.totentanz/files"
"""

import argparse
import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATALOG = os.path.join(ROOT, "data", "catalog.json")
ASSETS = os.path.join(ROOT, "assets")


def load_catalog():
    with open(CATALOG, encoding="utf-8") as handle:
        return json.load(handle)


def copy_all(pairs):
    copied = 0
    missing = []
    for source, target in pairs:
        if not os.path.isfile(source):
            missing.append(target)
            continue
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copyfile(source, target)
        copied += 1
    return copied, missing


def main(argv=None):
    parser = argparse.ArgumentParser(description="复制编辑器所需的素材图")
    parser.add_argument("--data-root", required=True, help="APK 数据目录（…/files）")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    root = args.data_root
    native = os.path.join(root, "madomagi", "resource", "image_native")
    web = os.path.join(root, "magica", "resource", "image_web", "item", "main")
    catalog = load_catalog()

    groups = []

    gift_pairs = []
    for gift_id in catalog["gifts"]:
        gift_pairs.append((os.path.join(native, "gift", "item_gift_%s.png" % gift_id),
                           os.path.join(ASSETS, "gifts", "%s.png" % gift_id)))
    groups.append(("gifts", gift_pairs))

    # chara_<id>_h.png 是命运宝石（デスティニージェム）图标，不是头像；
    # 头像统一用该角色卡的卡面 card_<cardId>_s.png（游戏内一览界面同样用卡面）。
    gem_pairs = []
    for chara_id in catalog["chara"]:
        gem_pairs.append((os.path.join(native, "chara", "chara_%s_h.png" % chara_id),
                          os.path.join(ASSETS, "gem", "%s.png" % chara_id)))
    groups.append(("gem", gem_pairs))

    card_pairs = []
    for card_id in catalog["cards"]:
        card_pairs.append((os.path.join(native, "card", "image", "card_%s_s.png" % card_id),
                           os.path.join(ASSETS, "cards", "%s.png" % card_id)))
    groups.append(("cards", card_pairs))

    piece_pairs = []
    for piece_id in catalog["pieces"]:
        piece_pairs.append((os.path.join(native, "memoria", "memoria_%s_s.png" % piece_id),
                            os.path.join(ASSETS, "pieces", "%s.png" % piece_id)))
    groups.append(("pieces", piece_pairs))

    item_pairs = []
    for code in catalog["items"]:
        item_pairs.append((os.path.join(web, "%s.png" % code.lower()),
                           os.path.join(ASSETS, "items", "%s.png" % code.lower())))
    groups.append(("items", item_pairs))

    legacy = os.path.join(ASSETS, "chara")
    if os.path.isdir(legacy):
        shutil.rmtree(legacy, ignore_errors=True)

    report = {}
    total_bytes = 0
    for name, pairs in groups:
        copied, missing = copy_all(pairs)
        folder = os.path.join(ASSETS, name)
        size = 0
        if os.path.isdir(folder):
            for entry in os.listdir(folder):
                path = os.path.join(folder, entry)
                if os.path.isfile(path):
                    size += os.path.getsize(path)
        total_bytes += size
        report[name] = {"total": len(pairs), "copied": copied, "missing": len(missing),
                        "bytes": size, "missingSample": missing[:10]}
        print("%-8s 复制 %4d / %4d，缺失 %3d，%.1f MB" % (name, copied, len(pairs), len(missing), size / 1048576.0))

    with open(os.path.join(ROOT, "data", "assets.json"), "w", encoding="utf-8") as handle:
        json.dump({"generated": True, "dataRoot": os.path.abspath(root), "groups": report},
                  handle, ensure_ascii=False, indent=1)
    print("总计 %.1f MB -> %s" % (total_bytes / 1048576.0, ASSETS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
