from __future__ import annotations

from typing import Any, Dict, Optional


def _to_float(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None


def compute_ev_estimate_v1(
    *,
    action_kind: Optional[str],
    sizing: Optional[Dict[str, Any]],
    equity_estimate: Optional[Dict[str, Any]],
    facing_bet: bool,
) -> Optional[Dict[str, Any]]:
    """
    EV-модель v1 (очень простая, но стабильная):
    - НЕ солвер.
    - Использует estimated_equity, pot_before и amount (если есть).
    - Даёт EV выбранной линии и базовой альтернативы (passive).
    """

    if not action_kind or not sizing or not equity_estimate:
        return None

    equity = _to_float(equity_estimate.get("estimated_equity"))
    pot_before = _to_float(sizing.get("pot_before"))
    amount = _to_float(sizing.get("amount"))

    if equity is None or pot_before is None:
        return None

    # normalize
    if amount is None:
        amount = 0.0

    action_kind = action_kind.lower().strip()

    # Базовые EV:
    # - fold: 0
    # - check: equity * pot
    # - call: equity*(pot + call) - call
    # - bet/raise: equity*(pot + 2*bet) - bet (если заколлили)
    # В v1 fold_equity = 0 (позже добавим, как только начнём считать FE на постфлопе).
    fold_equity = 0.0

    ev_taken: Optional[float] = None
    ev_passive: Optional[float] = None
    delta_ev: Optional[float] = None
    best_line: Optional[str] = None
    alternative_line: Optional[str] = None

    if action_kind == "fold":
        ev_taken = 0.0
        # альтернативой считаем call (если это фолд против ставки)
        if facing_bet and amount > 0:
            alternative_line = "call"
            ev_passive = (equity * (pot_before + amount)) - amount
        else:
            alternative_line = None
            ev_passive = None

    elif action_kind == "check":
        ev_taken = equity * pot_before
        # В v1 не пытаемся считать EV агрессивной альтернативы, потому что нужен FE и реакция оппа.
        alternative_line = None
        ev_passive = None

    elif action_kind == "call":
        ev_taken = (equity * (pot_before + amount)) - amount
        # пассивная альтернатива против ставки = fold
        if facing_bet:
            alternative_line = "fold"
            ev_passive = 0.0
        else:
            alternative_line = "check"
            ev_passive = equity * pot_before

    elif action_kind in ("bet", "raise"):
        # v1: без FE; если захотим, позже добавим postflop fold_equity и формулу ниже.
        ev_if_called = (equity * (pot_before + 2.0 * amount)) - amount
        ev_taken = (fold_equity * pot_before) + ((1.0 - fold_equity) * ev_if_called)

        alternative_line = "check"
        ev_passive = equity * pot_before

    else:
        return None

    if ev_taken is not None and ev_passive is not None:
        delta_ev = ev_taken - ev_passive
        best_line = action_kind if delta_ev >= 0 else alternative_line

    return {
        "model": "simple_ev_model_v1",
        "inputs": {
            "equity": round(equity, 4),
            "pot_before": round(pot_before, 4),
            "amount": round(amount, 4),
            "facing_bet": facing_bet,
            "fold_equity_used": fold_equity,
        },
        "ev_taken": None if ev_taken is None else round(ev_taken, 6),
        "ev_passive": None if ev_passive is None else round(ev_passive, 6),
        "delta_ev": None if delta_ev is None else round(delta_ev, 6),
        "alternative_line": alternative_line,
        "best_line_by_ev": best_line,
        "comment": (
            "EV v1: упрощённая оценка по equity и поту. "
            "Постфлоп fold equity пока не учитывается (будет в v2)."
        ),
    }
