from __future__ import annotations

from typing import Optional, Dict, Any


def _clamp01(x: float) -> float:
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


def ev_fold() -> float:
    # В v1 считаем EV фолда = 0 относительно точки решения
    return 0.0


def ev_call(*, pot_before: float, to_call: float, equity: float) -> float:
    """
    EV колла в точке решения (до рейка, без реализации и будущих улиц):
      EV = equity * (pot_before + to_call) - to_call
    """
    e = _clamp01(float(equity))
    pb = float(pot_before)
    tc = float(to_call)
    final_pot = pb + tc
    return e * final_pot - tc


def ev_bet_or_raise(
    *,
    pot_before: float,
    investment: float,
    equity_if_called: float,
    fold_equity: Optional[float] = None,
    final_pot_if_called: Optional[float] = None,
) -> float:
    """
    EV ставки/рейза (простая модель FE + equity):
      EV = FE * pot_before + (1-FE) * (equity * final_pot_if_called - investment)

    Если final_pot_if_called не задан:
      final_pot_if_called = pot_before + 2 * investment
    (грубое приближение: опп коллит твой сайз 1-в-1)
    """
    pb = float(pot_before)
    inv = float(investment)
    e = _clamp01(float(equity_if_called))

    fe = 0.0 if fold_equity is None else _clamp01(float(fold_equity))

    if final_pot_if_called is None:
        final_pot = pb + 2.0 * inv
    else:
        final_pot = float(final_pot_if_called)

    return fe * pb + (1.0 - fe) * (e * final_pot - inv)


def compute_ev_estimate_v1(
    *,
    street: str,
    action_kind: str,
    pot_before: Optional[float],
    investment: Optional[float],
    estimated_equity: Optional[float],
    fold_equity: Optional[float] = None,
    final_pot_if_called: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """
    Унифицированный EV-блок для hero_*_decision.
    Возвращает словарь, который можно прямо класть в JSON.

    Если данных не хватает — возвращает None.
    """
        # --- v1 rule: passive actions with no investment have EV=0 ---
    if investment is None and action_kind in ("check", "fold"):
        return {
            "model": "ev_v1",
            "street": street,
            "action_kind": action_kind,
            "pot_before": pot_before,
            "investment": investment,
            "estimated_equity": estimated_equity,
            "fold_equity": fold_equity,
            "final_pot_if_called": final_pot_if_called,
            "ev_action": 0.0,
            "explanation": "No additional investment (check/fold) => EV(action)=0 in v1 baseline.",
        }

    if pot_before is None or estimated_equity is None:
        return None

    pb = float(pot_before)
    eq = float(estimated_equity)

    ak = (action_kind or "").lower()

    if ak == "fold":
        return {
            "street": street,
            "model": "ev_v1",
            "pot_before": pb,
            "investment": investment,
            "estimated_equity": eq,
            "fold_equity": fold_equity,
            "final_pot_if_called": final_pot_if_called,
            "ev_action": ev_fold(),
        }

    if investment is None:
        # для call/raise без investment мы не можем корректно посчитать EV
        return None

    inv = float(investment)

    if ak == "call":
        return {
            "street": street,
            "model": "ev_v1",
            "pot_before": pb,
            "investment": inv,
            "estimated_equity": eq,
            "fold_equity": None,
            "final_pot_if_called": pb + inv,
            "ev_action": ev_call(pot_before=pb, to_call=inv, equity=eq),
        }

    if ak in ("bet", "raise"):
        return {
            "street": street,
            "model": "ev_v1",
            "pot_before": pb,
            "investment": inv,
            "estimated_equity": eq,
            "fold_equity": fold_equity,
            "final_pot_if_called": final_pot_if_called,
            "ev_action": ev_bet_or_raise(
                pot_before=pb,
                investment=inv,
                equity_if_called=eq,
                fold_equity=fold_equity,
                final_pot_if_called=final_pot_if_called,
            ),
        }

    # неизвестный action_kind
    return None
