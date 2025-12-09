from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any, List


# ---------------------------------------------------------------------
#  БАЗОВЫЕ НАСТРОЙКИ
# ---------------------------------------------------------------------


RANKS = "23456789TJQKA"
RANK_TO_INDEX: Dict[str, int] = {r: i for i, r in enumerate(RANKS)}


@dataclass
class PreflopEquityEstimate:
    """
    Оценка силы руки героя на префлопе.

    ВАЖНО:
    - Для первой версии мы жёстко опираемся на твой MOS-чарт RFI
      с диапазонами открытия EP/MP/HJ/CO.
    - Рука попадает в одну из категорий в зависимости от того,
      с какой минимальной позиции она у тебя открывается.
    """
    hand_key: str                     # "AKs", "QJo", "77"
    category: str                     # premium / strong / medium / speculative / trash
    strength_score: float             # 0.0–1.0 — индекс силы, привязанный к MOS
    estimated_equity_vs_unknown: float  # 0.0–1.0 — примерная equity
    hero_position: Optional[str] = None
    villain_position: Optional[str] = None
    mos_min_position: Optional[str] = None   # EP / MP / HJ / CO / None
    notes: Optional[str] = None


# ---------------------------------------------------------------------
#  ТВОЙ MOS-RFI (ИЗ ЧАРТА RFI-MOS)
#  Канонизирован под формат hand_key: старшая карта первой (A9o, KQo и т.п.)
# ---------------------------------------------------------------------


RFI_MOS_RANGES: Dict[str, set[str]] = {
    # EP минимум
    "EP": {
        "22", "33", "44", "55", "66",
        "76s", "77", "87s", "88", "98s", "99",
        "A2s", "A3s", "A4s", "A5s", "A6s", "A7s", "A8s", "A9s",
        "AA",
        "AJo", "AJs", "AKo", "AKs", "AQo", "AQs", "ATo", "ATs",
        "J8s", "J9s",
        "JJ", "JTs",
        "K8s", "K9s", "KJo", "KJs", "KK", "KQo", "KQs", "KTs",
        "Q8s", "Q9s", "QJs", "QQ", "QTs",
        "T8s", "T9s", "TT",
    },

    # MP минимум
    "MP": {
        "65s", "86s", "97s",
        "A6s", "A7s", "A9o",
        "J7s", "JTo",
        "K6s", "K7s", "KTo",
        "Q7s", "QJo", "QQ", "QTo",
        "T7s",
    },

    # HJ минимум
    "HJ": {
        "54s", "96s",
        "A2s", "A3s", "A4s", "A5s", "A8o",
        "J6s", "J9o",
        "K2s", "K3s", "K4s", "K5s", "K6s", "K9o",
        "Q5s", "Q6s", "Q9o",
        "T6s", "T9o",
    },

    # CO минимум
    "CO": {
        "32s", "43s", "64s", "74s", "75s", "84s", "85s", "94s", "95s",
        "98o",
        "A2o", "A3o", "A4o", "A5o", "A6o", "A7o",
        "J2s", "J3s", "J4s", "J5s", "J8o",
        "K2s", "K3s", "K4s", "K8o",
        "Q2s", "Q3s", "Q4s", "Q5s", "Q8o",
        "T4s", "T5s", "T8o",
    },
}

RFI_MOS_ORDER = ["EP", "MP", "HJ", "CO"]


# ---------------------------------------------------------------------
#  ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ РАБОТЫ С КАРТАМИ
# ---------------------------------------------------------------------


def _get_rank(card: str) -> str:
    """
    card: строка вида "Td", "Ah", "5c".
    Возвращает символ ранга: "T", "A", "5".
    """
    if not card or len(card) < 2:
        raise ValueError(f"Некорректная карта: {card!r}")
    return card[0].upper()


def _get_suit(card: str) -> str:
    """
    card: строка вида "Td", "Ah", "5c".
    Возвращает символ масти: "d", "h", "c", "s".
    """
    if not card or len(card) < 2:
        raise ValueError(f"Некорректная карта: {card!r}")
    return card[1].lower()


def normalize_hand_key(hero_cards: List[str]) -> str:
    """
    Приводит 2 карты героя к каноничному виду:
    - пара: "77", "AA"
    - разные ранги:
        - suited:   "AKs"
        - offsuit:  "AKo"

    hero_cards: ["Td", "5h"], ["Ah", "Ad"], etc.
    """
    if len(hero_cards) != 2:
        raise ValueError(f"Ожидалось ровно 2 карты героя, получено: {hero_cards!r}")

    c1, c2 = hero_cards
    r1, s1 = _get_rank(c1), _get_suit(c1)
    r2, s2 = _get_rank(c2), _get_suit(c2)

    if r1 not in RANK_TO_INDEX or r2 not in RANK_TO_INDEX:
        raise ValueError(f"Некорректные ранги карт: {hero_cards!r}")

    # пара
    if r1 == r2:
        return r1 + r2

    # сортируем по силе, чтобы "AK" а не "KA"
    if RANK_TO_INDEX[r1] > RANK_TO_INDEX[r2]:
        high, low = r1, r2
        suit_high, suit_low = s1, s2
    else:
        high, low = r2, r1
        suit_high, suit_low = s2, s1

    suited = suit_high == suit_low
    return f"{high}{low}{'s' if suited else 'o'}"


# ---------------------------------------------------------------------
#  MOS-ЛОГИКА: МИНИМАЛЬНАЯ ПОЗИЦИЯ ОТКРЫТИЯ
# ---------------------------------------------------------------------


def get_mos_min_position(hand_key: str) -> Optional[str]:
    """
    Возвращает минимальную позицию открытия для данной руки по твоему MOS-чарту:
    - "EP", "MP", "HJ", "CO"
    - или None, если рука вообще не входит в RFI-диапазоны.
    """
    for pos in RFI_MOS_ORDER:
        if hand_key in RFI_MOS_RANGES[pos]:
            return pos
    return None


def _classify_hand_category_from_mos(hand_key: str) -> tuple[str, float, Optional[str], str]:
    """
    На основе MOS-диапазонов:
      - определяем минимальную позицию открытия,
      - маппим её в категорию и strength_score,
      - формируем поясняющий текст.
    """
    mos_pos = get_mos_min_position(hand_key)

    if mos_pos is None:
        # Рука вообще не внутри твоего MOS-RFI → по дефолту "trash"
        category = "trash"
        strength_score = 0.45
        notes = (
            f"{hand_key} не входит в твой MOS-диапазон RFI (EP–CO). "
            f"В базовой стратегии такая рука чаще всего фолдится префлоп "
            f"или играет только как защита против открытия."
        )
        return category, strength_score, None, notes

    if mos_pos == "EP":
        category = "premium"
        strength_score = 0.95
        notes = (
            f"{hand_key} входит в твой EP-RFI диапазон по MOS-чарту. "
            f"Это одна из самых сильных стартовых рук в твоей системе открытий."
        )
    elif mos_pos == "MP":
        category = "strong"
        strength_score = 0.85
        notes = (
            f"{hand_key} входит в MP-RFI диапазон по MOS-чарту. "
            f"Рука сильная, стандартный опен с мид-позиций."
        )
    elif mos_pos == "HJ":
        category = "medium"
        strength_score = 0.75
        notes = (
            f"{hand_key} входит в HJ-RFI диапазон по MOS-чарту. "
            f"Рука средняя/играбельная, чаще открывается с середины стола и позднее."
        )
    else:  # "CO"
        category = "speculative"
        strength_score = 0.65
        notes = (
            f"{hand_key} входит только в CO-RFI диапазон по MOS-чарту. "
            f"Это более спекулятивная рука, которая открывается в основном с поздних позиций."
        )

    return category, strength_score, mos_pos, notes


# ---------------------------------------------------------------------
#  ЭВРИСТИЧЕСКАЯ EQUITY НА ОСНОВЕ MOS
# ---------------------------------------------------------------------


def estimate_preflop_equity_vs_unknown_range(
    hero_cards: List[str],
    hero_position: Optional[str] = None,
    villain_position: Optional[str] = None,
) -> PreflopEquityEstimate:
    """
    Оценка префлоп-equity героя против "усреднённого неизвестного диапазона".

    Для первой версии:
    - мы НЕ считаем реальную equity через перебор — вместо этого используем
      твою MOS-классификацию (EP/MP/HJ/CO) как базу силы руки;
    - по ней выдаём:
        * категорию (premium/strong/medium/speculative/trash)
        * strength_score (0–1)
        * примерную equity (0–1)
        * комментарий, завязанный на MOS.

    Дальше сюда можно будет подставить:
    - реальные диапазоны оппонента по позиции,
    - внешний hand/equity-движок.
    """
    hand_key = normalize_hand_key(hero_cards)
    category, strength_score, mos_pos, notes = _classify_hand_category_from_mos(hand_key)

    # Базовая карта "категория → примерная equity".
    # Это НЕ точные цифры по солверу, а калиброванная шкала
    # специально под твою MOS-систему:
    #
    # premium     ~ 0.68
    # strong      ~ 0.60
    # medium      ~ 0.56
    # speculative ~ 0.52
    # trash       ~ 0.47
    #
    base_equity_by_category: Dict[str, float] = {
        "premium": 0.68,
        "strong": 0.60,
        "medium": 0.56,
        "speculative": 0.52,
        "trash": 0.47,
    }

    base_equity = base_equity_by_category.get(category, 0.50)

    # Чуть подмешаем strength_score, чтобы внутри категории были микродвижения.
    # Делаем небольшую поправку ±0.03 вокруг базового значения.
    # Это можно будет потом затюнить по ощущениям/данным.
    delta = (strength_score - 0.7) * 0.08  # маленький коэффициент
    estimated_equity = base_equity + delta

    # ограничим интервал [0.35, 0.80] на всякий случай
    estimated_equity = max(0.35, min(0.80, estimated_equity))

    return PreflopEquityEstimate(
        hand_key=hand_key,
        category=category,
        strength_score=round(strength_score, 3),
        estimated_equity_vs_unknown=round(estimated_equity, 3),
        hero_position=hero_position,
        villain_position=villain_position,
        mos_min_position=mos_pos,
        notes=notes,
    )


# ---------------------------------------------------------------------
#  ОБЁРТКА ДЛЯ JSON
# ---------------------------------------------------------------------


def estimate_preflop_equity_as_dict(
    hero_cards: List[str],
    hero_position: Optional[str] = None,
    villain_position: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Обёртка над estimate_preflop_equity_vs_unknown_range, которая сразу
    возвращает dict (удобно класть прямо в JSON).

    Структура:

    {
      "hand_key": "AKs",
      "category": "premium",
      "strength_score": 0.95,
      "estimated_equity_vs_unknown": 0.71,
      "hero_position": "CO",
      "villain_position": "UTG",
      "mos_min_position": "EP",
      "notes": "AKs входит в твой EP-RFI диапазон..."
    }
    """
    estimate = estimate_preflop_equity_vs_unknown_range(
        hero_cards=hero_cards,
        hero_position=hero_position,
        villain_position=villain_position,
    )
    return asdict(estimate)
