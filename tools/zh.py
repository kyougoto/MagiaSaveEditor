"""中文化收尾：只处理「整句日文」的条目，中文里的日文标点一律保留。

官方中文 libs 里少数条目整句仍是日文（libs 缺该段），这类用人工翻译表覆盖：
    data/zh-overrides.json
        {"sections": {"505301": {"title": "..."}}, "pieces": {...}, "doppels": {...}}

中文文本里夹的 ー ・ 是原文风格（角色台词、拖长音），不改 —— 英文专有名词同理。
"""

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OVERRIDES_PATH = os.path.join(ROOT, "data", "zh-overrides.json")


def normalize(text):
    """保留原文（不再替换标点）。"""
    return text


def load_overrides():
    try:
        with open(OVERRIDES_PATH, encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        return {}


def translated(table, key, field, fallback):
    """overrides 里有就用人工译文，否则原样返回。"""
    entry = (load_overrides().get(table) or {}).get(str(key)) or {}
    if field in entry:
        return entry[field]
    return fallback
