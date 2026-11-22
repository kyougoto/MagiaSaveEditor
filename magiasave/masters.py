"""卡片 / 记忆结晶基础数值表（成长推算输入）。

由 tools/build_masters.py 从数据包中内嵌的官方 card/piece 定义聚合而成：
  data/cards.json   445 条（rank / growthType / attack / defense / hp）
  data/pieces.json  915 条（rank / attack / defense / hp / skillId）

覆盖面不足的卡片或结晶不会被猜：调用方拿到 None 就拒绝推算并提示。
"""

import json
import os

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


class Masters:
    def __init__(self, data_dir=None):
        self.data_dir = data_dir or _DATA_DIR
        self.cards = {}
        self.pieces = {}
        self.cards_meta = {}
        self.pieces_meta = {}
        self._load()

    def _load(self):
        cards = self._read("cards.json")
        pieces = self._read("pieces.json")
        self.cards = cards.get("cards") or {}
        self.pieces = pieces.get("pieces") or {}
        self.cards_meta = {key: value for key, value in cards.items() if key not in ("cards",)}
        self.pieces_meta = {key: value for key, value in pieces.items() if key not in ("pieces",)}

    def _read(self, name):
        path = os.path.join(self.data_dir, name)
        if not os.path.isfile(path):
            return {}
        try:
            with open(path, encoding="utf-8") as handle:
                return json.load(handle)
        except Exception:
            return {}

    def card(self, card_id):
        return self.cards.get(str(card_id))

    def piece(self, piece_id):
        return self.pieces.get(str(piece_id))

    def stats(self):
        return {"cards": len(self.cards), "pieces": len(self.pieces)}
