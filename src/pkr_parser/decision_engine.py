from __future__ import annotations
from .ev_tools import compute_ev_estimate_v1
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any


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

    # базовое FE для открытия первым (open-raise) по позициям
    fe_open_by_pos = {
        "UTG": 0.35,
        "MP": 0.38,
        "HJ": 0.42,
        "CO": 0.48,
        "BTN": 0.52,
        "SB": 0.30,
        "BB": 0.10,
    }

    base_fe = 0.30  # дефолт

    if action_type == "open_raise":
        base_fe = fe_open_by_pos.get(pos, 0.40)
    elif action_type == "iso_raise":
        # против лимперов люди чаще коллят → FE чуть ниже, чем у обычного open'а
        base_fe = fe_open_by_pos.get(pos, 0.40) - 0.05
    elif action_type == "3bet":
        # 3бет обычно даёт приличное FE
        if pos in ("CO", "BTN"):
            base_fe = 0.50
        else:
            base_fe = 0.45
    elif action_type == "4bet":
        base_fe = 0.55
    elif action_type == "5bet_plus":
        base_fe = 0.65
    else:
        base_fe = 0.30

    # Учёт количества рейзов до нас: чем больше, тем сложнее всех выбить
    fr = _safe_int(facing_raises) or 0
    if fr >= 2:
        base_fe -= 0.05

    # Учёт эффективного стека
    if effective_stack_bb is not None:
        try:
            eff = float(effective_stack_bb)
            if eff < 40:
                base_fe -= 0.05  # против коротких чипы чаще залетают
            elif eff > 120:
                base_fe += 0.05  # против глубоких чаще фолд
        except (TypeError, ValueError):
            pass

    # ограничиваем FE адекватными рамками
    base_fe = max(0.05, min(0.75, base_fe))
    return base_fe


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

    # Пот-оддсы и required_equity считаем одинаково в обоих режимах
    if pot_b is not None and inv is not None:
        pot_odds = inv / (pot_b + inv)
        required_equity = pot_odds

    # Если нет нормальной информации — возвращаем пустую математику
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

    # Определяем, считаем ли мы это рейзом с FE или обычным коллом
    raise_like_actions = {"open_raise", "iso_raise", "3bet", "4bet", "5bet_plus"}
    if action_type in raise_like_actions:
        # Модель рейза с fold equity
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
        # Модель колла (или рейза, который мы оцениваем как колл)
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


def _classify_decision_quality_base(
    math: PreflopDecisionMath,
) -> str:
    """
    Базовый вердикт только по математике (без учёта MOS и позиции).
    """
    if math.estimated_equity is None or math.required_equity is None:
        return "unknown"

    edge = math.estimated_equity - math.required_equity

    # Пороговые значения можно потом подстроить/вынести в настройки.
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
    """
    Корректируем вердикт в зависимости от дисциплины по MOS-диапазону.

    Логика:
    - слишком лузовый open (рука вне MOS) → штраф
    - слишком ранний open (раньше минимальной MOS-позиции) → штраф
    - слишком тайтовый фолд (fold_preflop с рукой из MOS, герой первый в раздаче и в позиции, где можно открывать) → считаем ошибкой
    """
    if not range_discipline:
        return base_quality

    error_type = range_discipline.get("error_type")

    # Ошибки по open'ам
    if error_type in ("too_loose_open", "too_early_position_open"):
        if base_quality == "good":
            return "marginal"
        if base_quality == "marginal":
            return "mistake"
        if base_quality == "mistake":
            return "blunder"
        return base_quality

    # Ошибка "слишком тайтовый фолд"
    if error_type == "too_tight_fold":
        # базовая математика для фолда обычно "unknown" — назначим хотя бы "mistake"
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
    """
    Анализ дисциплины по твоему MOS-RFI:

    - hero_position: фактическая позиция героя (UTG/MP/HJ/CO/BTN/SB/BB)
    - mos_min_position: минимальная позиция из MOS, где эта рука открывается (EP/MP/HJ/CO)
    - hand_key: каноничный ключ руки (AKs, QJo, 77)
    - action_type: логический тип действия (open_raise, fold_preflop, call_vs_raise, ...)
    - was_first_in: True, если до героя не было добровольных действий (рейз/колл/бет)

    Возвращает dict:

    {
      "in_mos": true/false,
      "position_ok": true/false/None,
      "hero_position": "...",
      "mos_min_position": "..."/null,
      "error_type": "too_loose_open"/"too_early_position_open"/"too_tight_fold"/None,
      "range_comment": "..."
    }
    """
    # --- СЛИШКОМ ТАЙТОВЫЙ ФОЛД ---
    if action_type == "fold_preflop" and was_first_in:
        in_mos = mos_min_position is not None

        if not in_mos:
            return None

        mos_idx = MOS_POSITION_ORDER.get(mos_min_position)
        hero_idx = POSITION_ORDER.get(hero_position) if hero_position else None

        if mos_idx is None or hero_idx is None:
            comment = (
                f"Рука {hand_key or ''} входит в твой MOS-RFI диапазон ({mos_min_position}), "
                f"и ты сфолдил первым ходом. Потенциально это может быть слишком тайтовым фолдом, "
                f"но позицию героя определить не удалось."
            )
            return {
                "in_mos": True,
                "position_ok": None,
                "hero_position": hero_position,
                "mos_min_position": mos_min_position,
                "error_type": "too_tight_fold",
                "range_comment": comment,
            }

        if hero_idx >= mos_idx:
            comment = (
                f"{hand_key or 'Рука'} входит в твой MOS-RFI диапазон (минимальная позиция {mos_min_position}), "
                f"а ты сфолдил первым ходом с позиции {hero_position}. "
                f"Это слишком тайтовый фолд относительно твоего базового плана open-рейзов."
            )
            return {
                "in_mos": True,
                "position_ok": True,
                "hero_position": hero_position,
                "mos_min_position": mos_min_position,
                "error_type": "too_tight_fold",
                "range_comment": comment,
            }

        return {
            "in_mos": True,
            "position_ok": False,
            "hero_position": hero_position,
            "mos_min_position": mos_min_position,
            "error_type": None,
            "range_comment": (
                f"{hand_key or 'Рука'} есть в MOS-RFI, но только начиная с позиции {mos_min_position}. "
                f"Фолд с более ранней позиции {hero_position} — часть тайтового, дисциплинированного плана."
            ),
        }

    # --- ОПЕНЫ / ЛИМПЫ ---
    if action_type not in ("open_raise", "open_limp", "iso_raise", "overlimp"):
        return None

    in_mos = mos_min_position is not None

    if not in_mos:
        comment = (
            f"{hand_key or 'Рука'} не входит в твой MOS-RFI диапазон (EP–CO), "
            f"но была сыграна как {action_type}. Это оверлузовый open относительно твоей базовой стратегии."
        )
        return {
            "in_mos": False,
            "position_ok": False,
            "hero_position": hero_position,
            "mos_min_position": None,
            "error_type": "too_loose_open",
            "range_comment": comment,
        }

    mos_idx = MOS_POSITION_ORDER.get(mos_min_position)
    hero_idx = POSITION_ORDER.get(hero_position) if hero_position else None

    if mos_idx is None or hero_idx is None:
        comment = (
            f"Рука {hand_key or ''} входит в MOS-RFI диапазон ({mos_min_position}), "
            f"но позицию героя определить не удалось."
        )
        return {
            "in_mos": True,
            "position_ok": None,
            "hero_position": hero_position,
            "mos_min_position": mos_min_position,
            "error_type": None,
            "range_comment": comment,
        }

    position_ok = hero_idx >= mos_idx

    if position_ok:
        comment = (
            f"{hand_key or 'Рука'} открыта с позиции {hero_position}, что НЕ раньше минимальной MOS-позиции "
            f"{mos_min_position}. По диапазону открытия ты в рамках своей стратегии."
        )
        return {
            "in_mos": True,
            "position_ok": True,
            "hero_position": hero_position,
            "mos_min_position": mos_min_position,
            "error_type": None,
            "range_comment": comment,
        }

    comment = (
        f"{hand_key or 'Рука'} по MOS-чарту должна впервые открываться не раньше позиции {mos_min_position}, "
        f"но была открыта с более ранней позиции {hero_position}. Это лузовый open относительно твоего RFI."
    )
    return {
        "in_mos": True,
        "position_ok": False,
        "hero_position": hero_position,
        "mos_min_position": mos_min_position,
        "error_type": "too_early_position_open",
        "range_comment": comment,
    }


def _build_comment(
    action_type: Optional[str],
    action_kind: Optional[str],
    math: PreflopDecisionMath,
    quality: str,
    range_discipline: Optional[Dict[str, Any]],
) -> str:
    """
    Человеческий комментарий по решению на основе математики + дисциплины по MOS.
    """
    base_desc = f"Тип действия: {action_type or 'неизвестно'}. Формат: {action_kind or 'неизвестно'}."

    if quality == "unknown":
        comment = (
            base_desc
            + " Не удалось точно оценить решение на префлопе: не хватает данных по поту, "
              "размеру ставки или equity руки."
        )
    else:
        pot_odds = math.pot_odds
        req = math.required_equity
        eq = math.estimated_equity

        if pot_odds is None or req is None or eq is None:
            math_desc = (
                " Недостаточно данных для подробного математического разбора, "
                "но базовая оценка решения выполнена."
            )
        else:
            edge = eq - req
            math_desc = (
                f" Пот-оддсы дают требуемую equity примерно {req:.2f} "
                f"({req * 100:.1f}%), твоя оценочная equity около {eq:.2f} "
                f"({eq * 100:.1f}%). Разница (edge) ≈ {edge:.2f}."
            )

        if quality == "good":
            comment = (
                base_desc
                + " Решение выглядит явно плюсовым с точки зрения математики."
                + math_desc
            )
        elif quality == "marginal":
            comment = (
                base_desc
                + " Решение находится около нуля: математически оно допустимо, но без большого запаса."
                + math_desc
            )
        elif quality == "mistake":
            comment = (
                base_desc
                + " Математически или стратегически решение выглядит минусовым. "
                  "В долгую дистанцию лучше искать более сильные или более дисциплинированные споты."
                + math_desc
            )
        elif quality == "blunder":
            comment = (
                base_desc
                + " Решение выглядит сильно минусовым: вероятность выигрыша слишком низкая "
                  "относительно пот-оддсов или оно явно выходит за рамки твоего диапазона."
                + math_desc
            )
        else:
            comment = base_desc + " Базовая оценка выполнена, но детализировать вывод не удалось."

    if range_discipline:
        rc = range_discipline.get("range_comment")
        if rc:
            comment = comment + " " + rc

    return comment


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
    Главная функция модуля: даёт оценку решения героя на префлопе.
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

    ev_estimate = compute_ev_estimate_v1(
        street="preflop",
        action_kind=action_kind or "unknown",
        pot_before=pot_before,
        investment=investment,
        estimated_equity=estimated_equity,
        fold_equity=None,
        final_pot_if_called=None,
    )

    out = asdict(evaluation)
    out["ev_estimate"] = ev_estimate
    return out
