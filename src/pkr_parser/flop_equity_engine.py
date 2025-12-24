from __future__ import annotations

from typing import Optional, Dict, Any


def _clamp(value: float, min_value: float = 0.05, max_value: float = 0.95) -> float:
    """Ограничиваем значение в разумных границах equity (5%–95%)."""
    if value < min_value:
        return min_value
    if value > max_value:
        return max_value
    return value


def estimate_flop_equity_simple(
    category: Optional[str],
    pair_kind: Optional[str],
    strength_score: Optional[float],
    multiway: bool,
    hero_ip: bool,
    preflop_role: str,
) -> Optional[Dict[str, Any]]:
    """
    Очень грубая оценка equity героя на флопе против диапазона оппонента.

    ВХОД:
      - category: high_card / pair / two_pair / set / straight / flush / ...
      - pair_kind: top_pair / overpair / middle_pair / bottom_pair / board_pair / None
      - strength_score: 0..1 (наша внутренняя шкала силы руки на флопе)
      - multiway: True, если мультипот
      - hero_ip: True, если герой в позиции на флопе
      - preflop_role: aggressor / caller / checked_bb / ...

    ВЫХОД:
      {
        "estimated_equity": float (0..1),
        "model": "simple_flop_category_model",
        "explanation": str
      }

    Это НЕ солвер и НЕ точная equity, а приближённая модель на основе категории руки и контекста.
    """

    if category is None or strength_score is None:
        return None

    # Базовая линейка: переводим strength_score (0..1) в "более полярную" equity вокруг 0.5
    #  - сильные руки чуть приближаем к 0.8–0.9
    #  - слабые — к 0.1–0.2
    base_equity = 0.5 + (strength_score - 0.5) * 1.3
    base_equity = _clamp(base_equity, 0.08, 0.92)

    explanation_parts = []

    explanation_parts.append(
        f"Базовая оценка equity построена от strength_score={strength_score:.2f} "
        f"и категории руки на флопе ({category})."
    )

    # Коррекция за мультивей
    if multiway:
        base_equity -= 0.07
        explanation_parts.append(
            "Мультипот (несколько оппонентов) снижает твою equity примерно на 7 п.п."
        )

    # Коррекция за позицию
    if not hero_ip:
        base_equity -= 0.03
        explanation_parts.append(
            "Игра без позиции (OOP) снижает эффективную equity примерно на 3 п.п."
        )
    else:
        base_equity += 0.02
        explanation_parts.append(
            "Игра в позиции (IP) слегка повышает эффективную equity (около 2 п.п.)."
        )

    # Роль префлоп
    if preflop_role == "aggressor":
        # Как префлоп-агрессор, у тебя априори более сильный диапазон
        base_equity += 0.02
        explanation_parts.append(
            "Ты префлоп-агрессор, поэтому твой диапазон в среднем сильнее — добавляем около 2 п.п. equity."
        )
    elif preflop_role == "caller":
        base_equity -= 0.01
        explanation_parts.append(
            "Ты префлоп-коллер, твой диапазон слегка слабее диапазона агрессора — вычитаем около 1 п.п. equity."
        )

    # Специальные поправки для некоторых категорий
    # high_card: обычно переоценён, чуть режем
    if category == "high_card":
        base_equity -= 0.05
        explanation_parts.append(
            "Рука без попадания (high_card) редко хорошо реализует equity — дополнительно уменьшаем оценку."
        )

    # board_pair: твоя пара только на доске => твой SDV слабый
    if pair_kind == "board_pair":
        base_equity -= 0.03
        explanation_parts.append(
            "Пара полностью на борде (board_pair), твой showdown value слабый — ещё немного снижаем equity."
        )

    # set+, наоборот, чуть апаем
    if category in ("set", "full_house", "quads", "straight_flush"):
        base_equity += 0.03
        explanation_parts.append(
            "Очень сильная made-hand (set+) — слегка повышаем оценку equity."
        )

    estimated_equity = _clamp(base_equity, 0.05, 0.95)

    explanation = " ".join(explanation_parts)

    return {
        "estimated_equity": float(f"{estimated_equity:.3f}"),
        "model": "simple_flop_category_model",
        "explanation": explanation,
    }


def get_flop_ev_action(action_type: str, hero_ip: bool, multiway: bool) -> str:
    """
    Возвращает конкретное действие контекста для флопа.
    """
    if action_type == "bet_vs_check":
        if hero_ip:
            return "cbet_ip" if not multiway else "cbet_multiway_ip"
        else:
            return "donk_bet_oop" if not multiway else "cbet_multiway_oop"
    elif action_type == "check":
        if hero_ip:
            return "check_raise_setup_ip" if not multiway else "check_call_multiway_ip"
        else:
            return "check_oop" if not multiway else "check_multiway_oop"
    elif action_type == "call_vs_bet":
        if hero_ip:
            return "call_raise_ip" if not multiway else "call_multiway_ip"
        else:
            return "call_oop" if not multiway else "call_multiway_oop"
    elif action_type == "raise_vs_bet":
        if hero_ip:
            return "raise_bluff_ip" if not multiway else "raise_bluff_multiway_ip"
        else:
            return "raise_value_oop" if not multiway else "raise_value_multiway_oop"
    else:
        return action_type
