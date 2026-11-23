"""卡片 / 记忆结晶基础数值表（成长推算输入）。

数据来源（按优先级合并）：
  data/cards-full.json / data/pieces-full.json  —— 从 APK 的 MCATBIN1 全量导出（525 卡 / 1041 结晶）
  data/cards.json / data/pieces.json            —— 旧的 offline 快照（445 / 915），只用来补全量里没有的字段

调用方拿到 None 就拒绝推算并提示，不猜数值。
"""

import json
import os

from . import paths


class Masters:
    def __init__(self, data_dir=None):
        self.data_dir = data_dir or paths.data_dir()
        self.cards = {}
        self.pieces = {}
        self.cards_meta = {}
        self.pieces_meta = {}
        self._load()

    def _load(self):
        full_cards = self._read("cards-full.json")
        full_pieces = self._read("pieces-full.json")
        legacy_cards = self._read("cards.json")
        legacy_pieces = self._read("pieces.json")

        cards = {}
        for source in (legacy_cards.get("cards") or {}, full_cards.get("cards") or {}):
            for key, row in source.items():
                merged = dict(cards.get(str(key)) or {})
                merged.update({k: v for k, v in (row or {}).items() if v is not None})
                cards[str(key)] = merged
        pieces = {}
        for source in (legacy_pieces.get("pieces") or {}, full_pieces.get("pieces") or {}):
            for key, row in source.items():
                merged = dict(pieces.get(str(key)) or {})
                merged.update({k: v for k, v in (row or {}).items() if v is not None})
                pieces[str(key)] = merged

        self.cards = cards
        self.pieces = pieces
        self.cards_meta = {key: value for key, value in full_cards.items() if key not in ("cards", "counts")}
        self.pieces_meta = {key: value for key, value in full_pieces.items() if key not in ("pieces", "counts")}

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