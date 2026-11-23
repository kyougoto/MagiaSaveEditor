"""游戏数值推算（移植自 offline/src/growth.js，已用真实存档回归验证）。

来源与证据：
  * 卡片成长：growth.js:18-45  —— MAX/CURVE/TYPES + stats()
  * 结晶成长：growth.js:199-220 —— PIECE_CURVES / pieceMaxLevel / pieceStats
  * 经验表：growth.js:10-17 (EXP) 与 205 (PIECE_EXP)

验证：对 chino 存档 17 张卡（15 张有基础值）与 36 枚结晶（35 张有基础值）逐项比对，
存档内 attack/defense/hp 与推算值 100% 一致（_re/verify_growth.py）。

这些是「游戏逻辑」，编辑器不自己发明数值：改等级/突破 -> 用本模块重算数值。
"""

import math

CARD_MAX_LEVEL = [0, 40, 50, 60, 80, 100]
CARD_CURVE = [0, 200, 220, 240, 260, 300]
CARD_GROWTH_TYPES = {
    "BALANCE": [1, 1, 1],
    "ATTACK": [1.03, 0.97, 0.98],
    "DEFENSE": [0.98, 1.05, 0.97],
    "HP": [0.97, 0.98, 1.04],
    "ATKDEF": [1.02, 1.01, 0.99],
    "ATKHP": [1.01, 0.99, 1.02],
    "DEFHP": [0.99, 1.02, 1.01],
}

CARD_EXP = [0, 110, 250, 430, 660, 950, 1310, 1750, 2280, 2910, 3640, 4470, 5400, 6430, 7560, 8790,
            10120, 11550, 13080, 14710, 16440, 18270, 20200, 22230, 24360, 26590, 28920, 31350, 33880,
            36510, 39240, 42070, 45000, 48030, 51160, 54390, 57720, 61150, 64680, 68310, 72040, 75870,
            79800, 83830, 87960, 92190, 96520, 100950, 105480, 110110, 114840, 119670, 124600, 129630,
            134760, 139990, 145320, 150750, 156280, 161910, 167640, 173470, 179400, 185430, 191560,
            197790, 204120, 210550, 217080, 223710, 230440, 237270, 244200, 251230, 258360, 265590,
            272920, 280350, 287880, 295510, 303240, 311070, 319000, 327030, 335160, 343390, 351720,
            360150, 368680, 377310, 386040, 394870, 403800, 412830, 421960, 431190, 440520, 449950,
            459480, 469110]

PIECE_CURVES = [
    [100, 100, 105, 111, 116, 122, 127, 133, 138, 144, 150, 155, 160, 165, 170, 175, 180, 185, 190, 195,
     200, 205, 210, 215, 220, 225, 230, 235, 240, 245, 250],
    [100, 100, 103, 107, 110, 114, 117, 121, 125, 128, 132, 135, 139, 142, 146, 150, 155, 160, 165, 170,
     175, 180, 185, 190, 195, 200, 205, 210, 215, 220, 225, 230, 235, 240, 245, 250],
    [100, 100, 102, 105, 107, 110, 113, 115, 118, 121, 123, 126, 128, 131, 134, 136, 139, 142, 144, 147,
     150, 155, 160, 165, 170, 175, 180, 185, 190, 195, 200, 205, 210, 215, 220, 225, 230, 235, 240, 245,
     250],
    [100, 100, 101, 103, 105, 106, 108, 110, 112, 113, 115, 117, 118, 120, 122, 124, 125, 127, 129, 131,
     132, 134, 136, 137, 139, 141, 143, 144, 146, 148, 150, 155, 160, 165, 170, 175, 180, 185, 190, 195,
     200, 205, 210, 215, 220, 225, 230, 235, 240, 245, 250],
]
PIECE_BASE_MAX = [10, 15, 20, 30]
PIECE_EXP = [0, 100, 210, 330, 460, 600, 760, 950, 1180, 1460, 1800, 2210, 2690, 3240, 3860, 4550,
             5310, 6140, 7040, 8010, 9050, 10160, 11340, 12590, 13910, 15300, 16760, 18290, 19890, 21560,
             23300, 25110, 26990, 28940, 30960, 33050, 35210, 37440, 39740, 42110, 44550, 47060, 49640,
             52290, 55010, 57800, 60660, 63590, 66590, 69660]

STAT_KEYS = ("attack", "defense", "hp")


class GrowthError(ValueError):
    pass


def _rank(rank_text, allowed=(1, 2, 3, 4, 5)):
    if not isinstance(rank_text, str) or not rank_text.startswith("RANK_"):
        raise GrowthError("rank 缺失: %r" % (rank_text,))
    try:
        value = int(rank_text.split("_")[1])
    except (IndexError, ValueError):
        raise GrowthError("rank 非法: %r" % (rank_text,))
    if value not in allowed:
        raise GrowthError("rank 超出范围: %r" % (rank_text,))
    return value


def card_max_level(rank_text):
    return CARD_MAX_LEVEL[_rank(rank_text)]


def card_stats(master, level):
    """移植 growth.stats()：master 提供 rank/growthType/attack/defense/hp（1 级基础值）。"""
    rank = _rank(master.get("rank"))
    growth = CARD_GROWTH_TYPES.get(master.get("growthType"))
    if not growth:
        raise GrowthError("growthType 未知: %r" % (master.get("growthType"),))
    if not isinstance(level, int) or isinstance(level, bool) or level < 1 or level > CARD_MAX_LEVEL[rank]:
        raise GrowthError("等级超出 %s 的上限 %d: %r" % (master.get("rank"), CARD_MAX_LEVEL[rank], level))
    coefficient = math.floor((level - 1) * CARD_CURVE[rank] / (CARD_MAX_LEVEL[rank] - 1)) / 100.0
    out = {}
    for index, key in enumerate(STAT_KEYS):
        base = master.get(key)
        if not isinstance(base, int) or isinstance(base, bool) or base <= 0:
            raise GrowthError("基础数值非法: %s=%r" % (key, base))
        out[key] = math.floor(base + base * coefficient * growth[index])
    return out


def card_experience_cap(level, rank_text):
    """升到下一级所需经验；满级为 0。"""
    cap = card_max_level(rank_text)
    if level >= cap:
        return 0
    return CARD_EXP[level] - CARD_EXP[level - 1]


def piece_max_level(rank_text, lb_count):
    rank = _rank(rank_text, allowed=(1, 2, 3, 4))
    if not isinstance(lb_count, int) or isinstance(lb_count, bool) or not (0 <= lb_count <= 4):
        raise GrowthError("lbCount 必须在 0-4: %r" % (lb_count,))
    return PIECE_BASE_MAX[rank - 1] + lb_count * 5


def piece_stats(master, level, lb_count):
    """移植 growth.pieceStats()：整数百分比表，与存档 35/35 一致。"""
    rank = _rank(master.get("rank"), allowed=(1, 2, 3, 4))
    cap = piece_max_level(master.get("rank"), lb_count)
    if not isinstance(level, int) or isinstance(level, bool) or level < 1 or level > cap:
        raise GrowthError("结晶等级超出上限 %d: %r" % (cap, level))
    rate = PIECE_CURVES[rank - 1][level]
    out = {}
    for key in STAT_KEYS:
        base = master.get(key)
        if not isinstance(base, int) or isinstance(base, bool) or base < 0:
            raise GrowthError("结晶基础数值非法: %s=%r" % (key, base))
        out[key] = math.floor(base * rate / 100)
    return out


def piece_experience_cap(level, rank_text, lb_count):
    cap = piece_max_level(rank_text, lb_count)
    if level >= cap:
        return 0
    return PIECE_EXP[level] - PIECE_EXP[level - 1]

# 剧情（Episode）等级阈值，来自 growth.js episodePlan 的 [0,1000,4000,14000,64000]
EPISODE_THRESHOLDS = [0, 1000, 4000, 14000, 64000]


def episode_level(points):
    if not isinstance(points, int) or isinstance(points, bool) or points < 0:
        return 0
    level = 0
    for index, threshold in enumerate(EPISODE_THRESHOLDS):
        if points >= threshold:
            level = index
    return level


def episode_next(points):
    level = episode_level(points)
    if level >= len(EPISODE_THRESHOLDS) - 1:
        return None
    return EPISODE_THRESHOLDS[level + 1]
