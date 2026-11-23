"""主数据索引（ID → 官方中文名称）。

索引由 tools/build_catalog.py 从客户端主数据生成，不在代码里硬编码任何名称。
"""

import json
import os

from . import paths

_DEFAULT_CANDIDATES = [
    os.path.join(paths.data_dir(), "catalog.json"),
]

STATUS_META = {
    "ACP": {"label": "AP（行动点）", "max": "MAX_ACP", "unit": "点"},
    "MAX_ACP": {"label": "AP 上限", "of": "ACP", "unit": "点"},
    "BTP": {"label": "BP（支援点）", "max": "MAX_BTP", "unit": "点"},
    "MAX_BTP": {"label": "BP 上限", "of": "BTP", "unit": "点"},
    "CP": {"label": "CP（竞技场点数）", "max": "MAX_CP", "unit": "点"},
    "MAX_CP": {"label": "CP 上限", "of": "CP", "unit": "点"},
    "RP": {"label": "RP（排名战点数）", "max": "MAX_RP", "unit": "点"},
    "MAX_RP": {"label": "RP 上限", "of": "RP", "unit": "点"},
    "MAX_FOLLOW": {"label": "好友上限", "unit": "人"},
}

ATTRIBUTE_LABELS = {
    "FIRE": "火",
    "WATER": "水",
    "TIMBER": "木",
    "LIGHT": "光",
    "DARK": "暗",
    "VOID": "无",
    "ALL": "全",
}


class Catalog:
    def __init__(self, path=None):
        self.path = None
        self.data = {}
        for candidate in ([path] if path else []) + _DEFAULT_CANDIDATES:
            if candidate and os.path.isfile(candidate):
                try:
                    with open(candidate, encoding="utf-8") as handle:
                        self.data = json.load(handle)
                    self.path = candidate
                    break
                except Exception:
                    continue
        for key in ("items", "chara", "cards", "pieces", "gifts", "sections", "chapters", "events", "doppels", "challenges", "emotionSkills"):
            self.data.setdefault(key, {})
        self.overrides = self._load_overrides()
        # 缺失的本地化文案（挑战等）直接并进索引，运行时无需再判断
        for section, values in (self.overrides or {}).items():
            if section == "challenges" and isinstance(values, dict):
                for key, text in values.items():
                    if text:
                        self.data["challenges"][key] = text

    @staticmethod
    def _load_overrides():
        path = os.path.join(paths.data_dir(), "zh-overrides.json")
        if not os.path.isfile(path):
            return {}
        try:
            with open(path, encoding="utf-8") as handle:
                return json.load(handle) or {}
        except Exception:
            return {}

    # ---------------------------------------------------------------- 查询

    def item(self, code):
        row = self.data["items"].get(str(code))
        if row:
            return row
        return {"name": str(code)}

    def item_name(self, code):
        return self.item(code).get("name") or str(code)

    def chara(self, chara_id):
        row = self.data["chara"].get(str(chara_id))
        return row or {"name": str(chara_id)}

    def chara_name(self, chara_id):
        """同名角色靠 title 区分（如「环彩羽（泳装）」「环彩羽（动画ver.）」）。"""
        row = self.chara(chara_id)
        name = row.get("name") or str(chara_id)
        title = row.get("title")
        return ("%s（%s）" % (name, title)) if title else name

    def card(self, card_id):
        row = self.data["cards"].get(str(card_id))
        return row or {"name": str(card_id)}

    def card_name(self, card_id):
        return self.card(card_id).get("name") or str(card_id)

    def piece(self, piece_id):
        row = self.data["pieces"].get(str(piece_id))
        return row or {"name": str(piece_id)}

    def piece_name(self, piece_id):
        return self.piece(piece_id).get("name") or str(piece_id)

    def emotion_skill(self, skill_id):
        return self.data["emotionSkills"].get(str(skill_id)) or {}

    def gift_name(self, gift_id):
        return self.data["gifts"].get(str(gift_id)) or ("礼物 %s" % gift_id)

    def section(self, section_id):
        row = self.data["sections"].get(str(section_id))
        return row or {"title": str(section_id), "area": None, "questType": None}

    def chapter(self, chapter_id):
        row = self.data["chapters"].get(str(chapter_id))
        return row or {"no": str(chapter_id), "title": None, "questType": None}

    def event_name(self, event_id):
        return self.data["events"].get(str(event_id)) or str(event_id)

    def doppel_name(self, doppel_id):
        return (self.data["doppels"].get(str(doppel_id)) or {}).get("name") or str(doppel_id)

    def challenge_text(self, table, challenge_id):
        key = "%s_%s" % (table, challenge_id)
        return self.data["challenges"].get(key)

    def attribute_label(self, attribute):
        return ATTRIBUTE_LABELS.get(str(attribute), str(attribute))

    def status_label(self, status_id):
        meta = STATUS_META.get(status_id)
        if meta:
            return meta["label"]
        if "_" in str(status_id):
            attribute, _, stat = str(status_id).partition("_")
            if attribute in ATTRIBUTE_LABELS and stat in ("ATTACK", "DEFENSE", "HP"):
                label = {"ATTACK": "攻击力", "DEFENSE": "防御力", "HP": "生命值"}[stat]
                return "%s属性强化（%s）" % (ATTRIBUTE_LABELS[attribute], label)
        return str(status_id)

    def stats(self):
        return {key: len(value) for key, value in self.data.items() if isinstance(value, dict)}
