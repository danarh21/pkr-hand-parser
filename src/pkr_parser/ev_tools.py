from __future__ import annotations

from typing import Optional, Dict, Any


def _clamp01(x: float) -> float:
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


def ev_fold() -> float:
    # EV фолда относительно точки решения (v1)
    return 0.0


def ev_call_check(pot_before: float, investment: float, equity: float) -> float:
    """
    EV колла (или чека, если investment=0).
    EV = equity * (pot_before + investment) - investment
    """
    pb = float(pot_before)
    inv = float(investment)
    e = _clamp01(float(equity))
    return e * (pb + inv) - inv


def ev_bet_raise(
    pot_before: float,
    investment: float,
    equity_if_called: float,
    fold_equity: Optional[float] = None,
    final_pot_if_called: Optional[float] = None,
) -> float:
    """
    Упрощённый EV ставки/рейза:
      EV = FE * pot_before + (1-FE) * (equity_if_called * final_pot_if_called - investment)

    Если final_pot_if_called не задан:
      final_pot_if_called = pot_before + 2*investment
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


def generate_assumptions(street: str, action_kind: str, context: Optional[Dict[str, Any]] = None) -> str:
    """
    Генерирует человекочитаемые допущения для EV-оценки.
    Оставляем максимально совместимо: возвращает строку.
    """
    context = context or {}
    ak = (action_kind or "unknown").lower()

    parts = [f"street={street}", f"action_kind={ak}"]

    # поддерживаем твою текущую структуру контекста (если есть)
    for k in ("multiway", "hero_ip", "hero_position", "villain_position", "effective_stack", "effective_stack_bb", "board_texture"):
        if k in context:
            parts.append(f"{k}={context.get(k)}")

    return "; ".join(parts)


def generate_context(
    *,
    multiway: bool = False,
    hero_ip: bool = False,
    hero_position: str = "unknown",
    villain_position: str = "unknown",
    effective_stack: float = 0.0,
    board_texture: str = "unknown",
) -> Dict[str, Any]:
    """
    Стандартный контекст для EV.
    """
    return {
        "multiway": bool(multiway),
        "hero_ip": bool(hero_ip),
        "hero_position": hero_position,
        "villain_position": villain_position,
        "effective_stack": float(effective_stack),
        "board_texture": board_texture,
    }


def _make_ev_estimate(
    *,
    street: str,
    action_kind: str,
    ev_value: float,
    ev_action_label: str,
    pot_before: Optional[float],
    investment: Optional[float],
    estimated_equity: Optional[float],
    fold_equity: Optional[float],
    final_pot_if_called: Optional[float],
    model: str,
    assumptions: str,
    confidence: float,
    context: Dict[str, Any],
    alternatives: Dict[str, Any],
    explanation: str,
) -> Dict[str, Any]:
    """
    Центральная функция сборки ev_estimate.

    СОВМЕСТИМОСТЬ:
    - Новый ключ: ev_action (число)
    - Legacy ключ: ev (число)  <-- чтобы старые репорты/код не умерли
    - Новый label: ev_action_label (строка)
    - Legacy string: ev_action_str (строка) <-- если где-то раньше ожидали строку в ev_action
    """
    ev_num = float(ev_value)

    return {
        "street": street,
        "action_kind": action_kind,
        # новый контракт
        "ev_action": ev_num,
        "ev_action_label": ev_action_label,
        # legacy-совместимость
        "ev": ev_num,
        "ev_action_str": ev_action_label,
        # поля контекста
        "pot_before": pot_before,
        "investment": investment,
        "estimated_equity": estimated_equity,
        "fold_equity": fold_equity,
        "final_pot_if_called": final_pot_if_called,
        "model": model,
        "assumptions": assumptions,
        "confidence": float(confidence),
        "context": context,
        "alternatives": alternatives,
        "explanation": explanation,
    }


def compute_ev_estimate_v1(
    *,
    street: str,
    action_kind: str,
    pot_before: Optional[float],
    investment: Optional[float],
    estimated_equity: Optional[float],
    fold_equity: Optional[float] = None,
    final_pot_if_called: Optional[float] = None,
    # НОВОЕ: правильный лейбл
    ev_action_label: Optional[str] = None,
    # СТАРОЕ: раньше у тебя мог быть ev_action=строка (лейбл) — поддержим
    ev_action: Optional[str] = None,
    assumptions: Optional[str] = None,
    confidence: Optional[float] = None,
    context: Optional[Dict[str, Any]] = None,
    alternatives: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    EV (v1 baseline) — теперь всегда возвращает dict.

    Совместимость:
    - если вызвали со старым именем ev_action=... (строка), не ломаемся
    - возвращаем и новый ключ ev_action (число), и legacy ev (число)
    """
    ak = (action_kind or "unknown").lower()
    ctx = context or {}
    alts = alternatives or {}

    label = ev_action_label or ev_action or "unlabeled"

    # если данных не хватает — EV=0, но контракт сохраняем
    if pot_before is None or estimated_equity is None:
        return _make_ev_estimate(
            street=street,
            action_kind=action_kind,
            ev_value=0.0,
            ev_action_label=label if label != "unlabeled" else "missing_inputs",
            pot_before=pot_before,
            investment=investment,
            estimated_equity=estimated_equity,
            fold_equity=fold_equity,
            final_pot_if_called=final_pot_if_called,
            model="v1_baseline",
            assumptions=assumptions or generate_assumptions(street, ak, ctx),
            confidence=float(confidence) if confidence is not None else 0.3,
            context=ctx,
            alternatives=alts,
            explanation="EV=0.0 (недостаточно входных данных для расчёта).",
        )

    pb = float(pot_before)
    eq = _clamp01(float(estimated_equity))

    # пассивные действия без вложений
    if investment is None and ak in ("check", "fold"):
        return _make_ev_estimate(
            street=street,
            action_kind=action_kind,
            ev_value=0.0,
            ev_action_label=label if label != "unlabeled" else ak,
            pot_before=pb,
            investment=investment,
            estimated_equity=eq,
            fold_equity=fold_equity,
            final_pot_if_called=final_pot_if_called,
            model="v1_baseline",
            assumptions=assumptions or generate_assumptions(street, ak, ctx),
            confidence=float(confidence) if confidence is not None else 0.5,
            context=ctx,
            alternatives=alts,
            explanation="EV=0.0 (пасивное действие без вложений).",
        )

    # если investment отсутствует, но действие не пассивное — тоже не ломаемся
    if investment is None:
        return _make_ev_estimate(
            street=street,
            action_kind=action_kind,
            ev_value=0.0,
            ev_action_label=label if label != "unlabeled" else "missing_investment",
            pot_before=pb,
            investment=investment,
            estimated_equity=eq,
            fold_equity=fold_equity,
            final_pot_if_called=final_pot_if_called,
            model="v1_baseline",
            assumptions=assumptions or generate_assumptions(street, ak, ctx),
            confidence=float(confidence) if confidence is not None else 0.35,
            context=ctx,
            alternatives=alts,
            explanation="EV=0.0 (нет investment для расчёта).",
        )

    inv = float(investment)

    # fold
    if ak == "fold":
        return _make_ev_estimate(
            street=street,
            action_kind=action_kind,
            ev_value=0.0,
            ev_action_label=label if label != "unlabeled" else "fold",
            pot_before=pb,
            investment=inv,
            estimated_equity=eq,
            fold_equity=fold_equity,
            final_pot_if_called=final_pot_if_called,
            model="v1_baseline",
            assumptions=assumptions or generate_assumptions(street, ak, ctx),
            confidence=float(confidence) if confidence is not None else 0.6,
            context=ctx,
            alternatives=alts,
            explanation="EV=0.0 (fold в точке решения).",
        )

    # call / check
    if ak in ("call", "check"):
        ev_value = ev_call_check(pb, inv, eq)
        used_label = label
        if used_label == "unlabeled":
            used_label = "check" if inv == 0.0 else "call"

        return _make_ev_estimate(
            street=street,
            action_kind=action_kind,
            ev_value=ev_value,
            ev_action_label=used_label,
            pot_before=pb,
            investment=inv,
            estimated_equity=eq,
            fold_equity=fold_equity,
            final_pot_if_called=final_pot_if_called,
            model="v1_baseline",
            assumptions=assumptions or generate_assumptions(street, ak, ctx),
            confidence=float(confidence) if confidence is not None else 0.5,
            context=ctx,
            alternatives=alts,
            explanation=f"EV(call/check)=equity*(pot_before+investment)-investment = {eq:.3f}*({pb:.2f}+{inv:.2f})-{inv:.2f}",
        )

    # bet/raise/3bet/4bet/allin
    if ak in ("bet", "raise", "3bet", "4bet", "allin", "all-in", "jam"):
        fe = 0.0 if fold_equity is None else _clamp01(float(fold_equity))
        ev_value = ev_bet_raise(
            pot_before=pb,
            investment=inv,
            equity_if_called=eq,
            fold_equity=fe,
            final_pot_if_called=final_pot_if_called,
        )
        used_label = label if label != "unlabeled" else f"{ak}_default"
        return _make_ev_estimate(
            street=street,
            action_kind=action_kind,
            ev_value=ev_value,
            ev_action_label=used_label,
            pot_before=pb,
            investment=inv,
            estimated_equity=eq,
            fold_equity=fe,
            final_pot_if_called=final_pot_if_called,
            model="v1_baseline",
            assumptions=assumptions or generate_assumptions(street, ak, ctx),
            confidence=float(confidence) if confidence is not None else 0.5,
            context=ctx,
            alternatives=alts,
            explanation="EV(bet/raise)=FE*pot_before + (1-FE)*(equity*final_pot_if_called - investment).",
        )

    # неизвестное действие
    return _make_ev_estimate(
        street=street,
        action_kind=action_kind,
        ev_value=0.0,
        ev_action_label=label if label != "unlabeled" else "unknown_action_kind",
        pot_before=pb,
        investment=inv,
        estimated_equity=eq,
        fold_equity=fold_equity,
        final_pot_if_called=final_pot_if_called,
        model="v1_baseline",
        assumptions=assumptions or generate_assumptions(street, ak, ctx),
        confidence=float(confidence) if confidence is not None else 0.35,
        context=ctx,
        alternatives=alts,
        explanation="EV=0.0 (неизвестный action_kind в v1).",
    )
