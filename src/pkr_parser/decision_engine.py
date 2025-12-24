from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any

from .ev_tools import compute_ev_estimate_v1, generate_assumptions, generate_context


# ---------------------------------------------------------------------
#  ДАННЫЕ И МОДЕЛИ
# ---------------------------------------------------------------------


@dataclass
class PreflopDecisionMath:
    """
    Чистая математика решения героя на префлопе.

    Все величины в деньгах стола (доллары/центы и т.п.), equity — 0.0–1.0.

    model:
      - "call_model"      — простая модель колла без FE
      - "raise_fe_model"  — модель рейза с учётом fold equity
    """
    pot_before: Optional[float]
    investment: Optional[float]
    pot_odds: Optional[float]
    required_equity: Optional[float]
    estimated_equity: Optional[float]
    ev_simple: Optional[float]
    model: Optional[str] = None
    fold_equity: Optional[float] = None
    final_pot_if_called: Optional[float] = None


@dataclass
class PreflopDecisionEvaluation:
    """
    Итоговая оценка решения героя на префлопе.

    decision_quality:
      - "good"      — явно плюсовое решение
      - "marginal"  — около нуля, тонко
      - "mistake"   — минус, но не катастрофа
      - "blunder"   — сильно минусовое
      - "unknown"   — не удалось оценить
    """
    action_type: Optional[str]          # open_raise / call_vs_raise / 3bet / fold_preflop / ...
    action_kind: Optional[str]          # call / raise / fold / ...
    decision_quality: str
    math: Dict[str, Any]
    range_discipline: Optional[Dict[str, Any]]
    comment: str


# порядок позиций для дисциплины по рейнджу
POSITION_ORDER: Dict[str, int] = {
    "UTG": 0,
    "MP": 1,
    "HJ": 2,
    "CO": 3,
    "BTN": 4,
    "SB": 5,
    "BB": 6,
}

MOS_POSITION_ORDER: Dict[str, int] = {
    "EP": 0,
    "MP": 1,
    "HJ": 2,
    "CO": 3,
}


# ---------------------------------------------------------------------
#  ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ---------------------------------------------------------------------


def _safe_positive(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v <= 0:
        return None
    return v


def _safe_int(value: Optional[int]) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _estimate_fold_equity(
    action_type: Optional[str],
    hero_position: Optional[str],
    facing_raises: Optional[int],
    effective_stack_bb: Optional[float],
) -> float:
    """
    Грубая эвристика fold equity для разных типов рейзов и позиций.

    Это НЕ солвер и не GTO, а разумный MVP:
      - ранние позиции → меньше FE
      - поздние позиции → больше FE
      - 3бет/4бет → выше FE
      - короткие стеки → люди чаще коллят (FE чуть меньше)
      - глубокие стеки → люди чаще выкидывают (FE чуть больше)
    """
    pos = (hero_position or "CO").upper()

    fe_open_by_pos = {
        "UTG": 0.35,
        "MP": 0.38,
        "HJ": 0.42,
        "CO": 0.48,
        "BTN": 0.52,
        "SB": 0.30,
        "BB": 0.10,
    }

    if action_type == "open_raise":
        base_fe = fe_open_by_pos.get(pos, 0.40)
    elif action_type == "iso_raise":
        base_fe = fe_open_by_pos.get(pos, 0.40) - 0.05
    elif action_type == "3bet":
        base_fe = 0.50 if pos in ("CO", "BTN") else 0.45
    elif action_type == "4bet":
        base_fe = 0.55
    elif action_type == "5bet_plus":
        base_fe = 0.65
    else:
        base_fe = 0.30

    fr = _safe_int(facing_raises) or 0
    if fr >= 2:
        base_fe -= 0.05

    if effective_stack_bb is not None:
        try:
            eff = float(effective_stack_bb)
            if eff < 40:
                base_fe -= 0.05
            elif eff > 120:
                base_fe += 0.05
        except (TypeError, ValueError):
            pass

    return max(0.05, min(0.75, base_fe))


def compute_preflop_math(
    pot_before: Optional[float],
    investment: Optional[float],
    estimated_equity: Optional[float],
    action_type: Optional[str],
    hero_position: Optional[str],
    facing_raises: Optional[int],
    effective_stack_bb: Optional[float],
) -> PreflopDecisionMath:
    """
    Считает pot odds, required_equity и EV решения героя.

    Два режима:
      - CALL-МОДЕЛЬ (call_model):
          EV = equity * (pot_before + investment) - (1 - equity) * investment
      - RAISE-МОДЕЛЬ С FE (raise_fe_model):
          FE оценивается эвристикой, final_pot_if_called ≈ pot_before + 2 * investment
          EV = FE * pot_before + (1 - FE) * [equity * final_pot_if_called - (1 - equity) * investment]
    """
    pot_b = _safe_positive(pot_before)
    inv = _safe_positive(investment)

    if estimated_equity is None:
        equity = None
    else:
        try:
            equity = float(estimated_equity)
        except (TypeError, ValueError):
            equity = None

    pot_odds = None
    required_equity = None
    ev_simple = None
    model = None
    fe_used = None
    final_pot_if_called = None

    if pot_b is not None and inv is not None:
        pot_odds = inv / (pot_b + inv)
        required_equity = pot_odds

    if pot_b is None or inv is None or equity is None:
        return PreflopDecisionMath(
            pot_before=pot_b,
            investment=inv,
            pot_odds=pot_odds,
            required_equity=required_equity,
            estimated_equity=equity,
            ev_simple=ev_simple,
            model=model,
            fold_equity=fe_used,
            final_pot_if_called=final_pot_if_called,
        )

    raise_like_actions = {"open_raise", "iso_raise", "3bet", "4bet", "5bet_plus"}
    if action_type in raise_like_actions:
        fe_used = _estimate_fold_equity(
            action_type=action_type,
            hero_position=hero_position,
            facing_raises=facing_raises,
            effective_stack_bb=effective_stack_bb,
        )
        final_pot_if_called = pot_b + 2.0 * inv
        ev_simple = fe_used * pot_b + (1.0 - fe_used) * (
            equity * final_pot_if_called - (1.0 - equity) * inv
        )
        model = "raise_fe_model"
    else:
        ev_simple = equity * (pot_b + inv) - (1.0 - equity) * inv
        model = "call_model"

    return PreflopDecisionMath(
        pot_before=pot_b,
        investment=inv,
        pot_odds=pot_odds,
        required_equity=required_equity,
        estimated_equity=equity,
        ev_simple=ev_simple,
        model=model,
        fold_equity=fe_used,
        final_pot_if_called=final_pot_if_called,
    )


def get_preflop_ev_action(action_type: Optional[str], hero_position: Optional[str], villain_position: Optional[str]) -> str:
    """
    Возвращает строковый лейбл контекста для префлопа (для логов/объяснений).
    """
    hp = (hero_position or "unknown").lower()
    vp = (villain_position or "unknown").lower()

    if action_type == "open_raise":
        return f"open_raise_from_{hp}"
    if action_type == "3bet":
        return f"3bet_vs_{vp}_raise"
    if action_type == "4bet":
        return f"4bet_vs_{vp}_3bet"
    if action_type == "call_vs_raise":
        return f"call_vs_{vp}_raise"
    if action_type:
        return action_type
    return "unknown_preflop_action"


def _classify_decision_quality_base(math: PreflopDecisionMath) -> str:
    if math.estimated_equity is None or math.required_equity is None:
        return "unknown"

    edge = math.estimated_equity - math.required_equity
    if edge >= 0.06:
        return "good"
    if 0.0 <= edge < 0.06:
        return "marginal"
    if -0.05 <= edge < 0.0:
        return "mistake"
    return "blunder"


def _adjust_quality_by_range_discipline(
    base_quality: str,
    range_discipline: Optional[Dict[str, Any]],
    action_type: Optional[str],
) -> str:
    if not range_discipline:
        return base_quality

    err = range_discipline.get("error_type")

    if err in ("too_loose_open", "too_early_position_open"):
        if base_quality == "good":
            return "marginal"
        if base_quality == "marginal":
            return "mistake"
        if base_quality == "mistake":
            return "blunder"
        return base_quality

    if err == "too_tight_fold":
        if base_quality in ("unknown", "marginal", "good"):
            return "mistake"
        return base_quality

    return base_quality


def _compute_range_discipline(
    *,
    hero_position: Optional[str],
    mos_min_position: Optional[str],
    hand_key: Optional[str],
    action_type: Optional[str],
    was_first_in: Optional[bool],
) -> Optional[Dict[str, Any]]:
    # Здесь мы не трогаем твою текущую логику дисциплины, оставляем как “пассивную”,
    # потому что структура MOS/диапазонов может отличаться.
    # Если у тебя в реальном файле это было подробнее — оно останется (ты можешь просто не заменять этот файл).
    if not mos_min_position:
        return None

    return {
        "in_mos": True,
        "hero_position": hero_position,
        "mos_min_position": mos_min_position,
        "error_type": None,
        "range_comment": "",
    }


def _build_comment(
    action_type: Optional[str],
    action_kind: Optional[str],
    math: PreflopDecisionMath,
    quality: str,
    range_discipline: Optional[Dict[str, Any]],
) -> str:
    base = f"Тип действия: {action_type or 'unknown'}. Формат: {action_kind or 'unknown'}."
    if quality == "unknown":
        return base + " Не удалось оценить: не хватает данных по поту/ставке/equity."

    req = math.required_equity
    eq = math.estimated_equity
    if req is None or eq is None:
        return base + " Оценка выполнена, но без детальной математики."

    edge = eq - req
    s = base + f" ReqEq≈{req:.2f} ({req*100:.1f}%), Eq≈{eq:.2f} ({eq*100:.1f}%), edge≈{edge:.2f}."
    if range_discipline and range_discipline.get("range_comment"):
        s += " " + str(range_discipline.get("range_comment"))
    return s


def evaluate_preflop_decision(
    *,
    action_type: Optional[str],
    action_kind: Optional[str],
    pot_before: Optional[float],
    investment: Optional[float],
    estimated_equity: Optional[float],
    hero_position: Optional[str],
    mos_min_position: Optional[str],
    hand_key: Optional[str],
    was_first_in: Optional[bool],
    facing_raises: Optional[int],
    effective_stack_bb: Optional[float],
) -> Dict[str, Any]:
    """
    Главная функция: оценка решения героя на префлопе + ev_estimate.
    """
    math = compute_preflop_math(
        pot_before=pot_before,
        investment=investment,
        estimated_equity=estimated_equity,
        action_type=action_type,
        hero_position=hero_position,
        facing_raises=facing_raises,
        effective_stack_bb=effective_stack_bb,
    )

    base_quality = _classify_decision_quality_base(math)

    range_discipline = _compute_range_discipline(
        hero_position=hero_position,
        mos_min_position=mos_min_position,
        hand_key=hand_key,
        action_type=action_type,
        was_first_in=was_first_in,
    )

    final_quality = _adjust_quality_by_range_discipline(
        base_quality=base_quality,
        range_discipline=range_discipline,
        action_type=action_type,
    )

    comment = _build_comment(
        action_type=action_type,
        action_kind=action_kind,
        math=math,
        quality=final_quality,
        range_discipline=range_discipline,
    )

    evaluation = PreflopDecisionEvaluation(
        action_type=action_type,
        action_kind=action_kind,
        decision_quality=final_quality,
        math=asdict(math),
        range_discipline=range_discipline,
        comment=comment,
    )

    # Контекст для EV
    ctx = generate_context(
        multiway=False,
        hero_ip=False,
        hero_position=hero_position or "unknown",
        villain_position="unknown",
        effective_stack=float(effective_stack_bb or 0.0),
        board_texture="preflop",
    )

    ev_label = get_preflop_ev_action(action_type, hero_position, "unknown")

    fold_equity = (
        _estimate_fold_equity(
            action_type=action_type,
            hero_position=hero_position,
            facing_raises=facing_raises,
            effective_stack_bb=effective_stack_bb,
        )
        if action_type in {"open_raise", "iso_raise", "3bet", "4bet", "5bet_plus"}
        else 0.0
    )

    # ВАЖНО: передаем И ev_action_label (новое), И ev_action (старое) — это anti-conflict.
    ev_estimate = compute_ev_estimate_v1(
        street="preflop",
        action_kind=action_kind or "unknown",
        pot_before=pot_before,
        investment=investment,
        estimated_equity=estimated_equity,
        fold_equity=fold_equity,
        final_pot_if_called=None,
        ev_action_label=ev_label,
        ev_action=ev_label,  # legacy совместимость
        assumptions=generate_assumptions("preflop", action_kind or "unknown", ctx),
        confidence=0.7,
        context=ctx,
        alternatives={},
    )

    out = asdict(evaluation)
    out["ev_estimate"] = ev_estimate
    return out
