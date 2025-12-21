from __future__ import annotations

from typing import Optional, Dict, Any, List


def _clamp_river(value: float, min_value: float = 0.02, max_value: float = 0.98) -> float:
    """Ограничиваем значение equity в разумных границах."""
    if value < min_value:
        return min_value
    if value > max_value:
        return max_value
    return value


def _get_preflop_role(
    hero_preflop_analysis: Optional[Any],
    hero_position: Optional[str],
) -> str:
    """
    Определяем роль героя на префлопе: aggressor / caller / checked_bb / folder / unknown.
    """
    if hero_preflop_analysis is None:
        if hero_position == "BB":
            return "checked_bb"
        return "unknown"

    atype = getattr(hero_preflop_analysis, "action_type", None)
    if atype in ("open_raise", "iso_raise", "3bet", "4bet", "5bet_plus"):
        return "aggressor"
    if atype in ("call_vs_raise", "call_vs_3bet_plus", "open_limp", "overlimp"):
        return "caller"
    if atype == "fold_preflop":
        return "folder"
    if atype is None and hero_position == "BB":
        return "checked_bb"
    return "unknown"


def _estimate_river_equity(
    base_from_turn: Optional[float],
    multiway: bool,
    hero_ip: bool,
    preflop_role: str,
    action_type: str,
) -> Optional[Dict[str, Any]]:
    """
    Очень грубая оценка equity героя на ривере на основе:
      - оценочной equity с тёрна (если есть),
      - контекста (multiway / IP / префлоп-роль),
      - линии на ривере (bet/check/call/raise/fold).

    Это НЕ солвер, а учебная эвристика.
    """

    if base_from_turn is None:
        return None

    explanation_parts = []
    base_equity = float(base_from_turn)

    explanation_parts.append(
        f"Базовая оценка на ривере строится от turn-equity≈{base_equity:.2f}."
    )

    # Мультипот обычно снижает реализуемость
    if multiway:
        base_equity -= 0.02
        explanation_parts.append(
            "Мультипот (несколько оппонентов) снижает реализуемую equity примерно на 2 п.п."
        )

    # Позиция
    if hero_ip:
        base_equity += 0.01
        explanation_parts.append(
            "Игра в позиции на ривере слегка повышает эффективную equity (около 1 п.п.)."
        )
    else:
        base_equity -= 0.01
        explanation_parts.append(
            "Игра без позиции на ривере слегка снижает эффективную equity (примерно на 1 п.п.)."
        )

    # Роль префлоп
    if preflop_role == "aggressor":
        base_equity += 0.01
        explanation_parts.append(
            "Ты префлоп-агрессор, диапазон в среднем сильнее — добавляем около 1 п.п. equity."
        )
    elif preflop_role == "caller":
        base_equity -= 0.005
        explanation_parts.append(
            "Ты префлоп-коллер, диапазон немного слабее — вычитаем около 0.5 п.п. equity."
        )

    # Линия на ривере
    if action_type in ("bet_vs_check", "bet", "raise_vs_bet", "raise"):
        base_equity += 0.01
        explanation_parts.append(
            "Агрессия на ривере (ставка/рейз) немного повышает реализуемость equity (около 1 п.п.)."
        )
    elif action_type == "check":
        base_equity -= 0.005
        explanation_parts.append(
            "Пассивная линия (чек) на ривере слегка снижает реализуемость equity."
        )
    elif action_type in ("call_vs_bet", "call"):
        explanation_parts.append(
            "Колл на ривере сохраняет часть equity, но без fold equity."
        )
    elif action_type in ("fold_vs_bet", "fold"):
        explanation_parts.append(
            "Фолд на ривере завершает раздачу, но оценка equity рассматривает гипотетическую продолженную игру."
        )

    estimated_equity = _clamp_river(base_equity)

    explanation = " ".join(explanation_parts)

    return {
        "estimated_equity": float(f"{estimated_equity:.3f}"),
        "model": "simple_river_model",
        "explanation": explanation,
    }


def _estimate_missed_value_ev_on_river(
    action_type: str,
    river_equity: Optional[float],
    pot_before: Optional[float],
    hero_ip: bool,
    multiway: bool,
) -> Optional[Dict[str, Any]]:
    """
    v1 эвристика "сколько EV недобрали на ривере", если сыграли слишком пассивно.
    Мы НЕ считаем точный солверный EV. Нужна полезная чиселка для отчёта.

    Логика:
      - если чекнули в позиции с достаточно высокой equity => возможный тонкий добор упущен.
      - оценка "недобора" = доля банка * (equity - порог) * коэффициент реализации
    """
    if action_type != "check":
        return None
    if not hero_ip:
        return None
    if river_equity is None:
        return None
    if pot_before is None:
        return None

    try:
        p = float(pot_before)
    except (TypeError, ValueError):
        return None
    if p <= 0:
        return None

    e = float(river_equity)

    # Порог "достаточно сильной" руки для тонкого добора в v1
    threshold = 0.65 if not multiway else 0.70
    if e < threshold:
        return None

    # Сколько максимум мы "можем" добрать тонким вэлью-бетом в этой эвристике:
    # - в HU чаще можно добирать тоньше, в мультипоте осторожнее
    max_fraction_of_pot = 0.25 if not multiway else 0.15

    # Нормируем силу: чем выше equity над порогом — тем больше вероятный недобор
    # cap на (e - threshold) в 0.25 чтобы не улетало в космос
    strength = min(max(e - threshold, 0.0), 0.25) / 0.25  # 0..1

    missed_ev = p * max_fraction_of_pot * strength

    # В отчётах мы хотим "потерю" как отрицательное число относительно выбранного действия
    ev_action = -float(f"{missed_ev:.4f}")

    explanation = (
        "Ривер: эвристика missed value. "
        f"Ты чекнул в позиции при оценочной equity≈{e:.2f} (порог {threshold:.2f}). "
        f"Модель предполагает, что тонкий вэлью-бет мог бы принести дополнительно до ~{max_fraction_of_pot*100:.0f}% банка "
        "пропорционально запасу по equity над порогом. "
        f"Оценка недобора ≈ {missed_ev:.4f} (в валюте стола)."
    )

    return {
        "ev_action": ev_action,
        "model": "river_missed_value_v1",
        "explanation": explanation,
    }


def evaluate_hero_river_decision(
    actions: List[Any],
    hero_name: Optional[str],
    hero_position: Optional[str],
    hero_preflop_analysis: Optional[Any],
    hero_flop_decision: Optional[Dict[str, Any]],
    hero_turn_decision: Optional[Dict[str, Any]],
    board: Optional[List[str]],
) -> Optional[Dict[str, Any]]:
    """
    v1-анализ ПЕРВОГО решения героя на ривере.

    Возвращает словарь:
      - action_type: логическая категория (bet_vs_check / call_vs_bet / raise_vs_bet / check / fold_vs_bet / ...)
      - action_kind: реальное действие (bet/call/check/raise/fold)
      - sizing: { amount, pot_before, pct_pot }
      - context: { players_to_river, multiway, hero_ip, hero_position, preflop_role }
      - hand: { base_from_turn_equity, note }
      - equity_estimate: { estimated_equity, model, explanation }
      - ev_estimate: { ev_action, model, explanation }  # (только если есть что посчитать)
      - decision_quality: оценка качества (good / ok / risky / bad / unknown)
      - quality_comment: текстовое объяснение оценки
      - comment: общий краткий комментарий по споту
    """
    if not hero_name:
        return None

    # -------- Действия на ривере --------
    river_actions = [a for a in actions if getattr(a, "street", None) == "river"]
    if not river_actions:
        return None

    hero_river_actions = [
        a for a in river_actions
        if getattr(a, "player", None) == hero_name
        and getattr(a, "action", None) not in ("uncalled",)
    ]
    if not hero_river_actions:
        return None

    first = hero_river_actions[0]
    idx_first = river_actions.index(first)
    prior = river_actions[:idx_first]

    facing_bet = any(getattr(a, "action", None) in ("bet", "raise") for a in prior)
    raw_action = getattr(first, "action", None)

    # -------- Тип действия на ривере --------
    if raw_action == "bet":
        if facing_bet:
            action_type = "bet"
        else:
            action_type = "bet_vs_check"
    elif raw_action == "check":
        action_type = "check"
    elif raw_action == "call":
        action_type = "call_vs_bet" if facing_bet else "call"
    elif raw_action == "raise":
        action_type = "raise_vs_bet" if facing_bet else "raise"
    elif raw_action == "fold":
        action_type = "fold_vs_bet" if facing_bet else "fold"
    else:
        action_type = raw_action or "unknown"

    # -------- Контекст ривера --------
    players_to_river = len({getattr(a, "player", None) for a in river_actions})

    last_other_idx = -1
    for i, a in enumerate(river_actions):
        if a.player != hero_name:
            last_other_idx = i
    hero_ip = idx_first > last_other_idx if last_other_idx >= 0 else True

    preflop_role = _get_preflop_role(hero_preflop_analysis, hero_position)

    context = {
        "players_to_river": players_to_river,
        "multiway": players_to_river > 2,
        "hero_ip": hero_ip,
        "hero_position": hero_position,
        "preflop_role": preflop_role,
    }

    # -------- База от тёрна --------
    base_from_turn_equity: Optional[float] = None

    if hero_turn_decision:
        eq_info = hero_turn_decision.get("equity_estimate") or {}
        if eq_info.get("estimated_equity") is not None:
            try:
                base_from_turn_equity = float(eq_info["estimated_equity"])
            except (TypeError, ValueError):
                base_from_turn_equity = None

    # Если с тёрна ничего нет — возьмём хотя бы оценку с флопа
    if base_from_turn_equity is None and hero_flop_decision:
        eq_info_flop = hero_flop_decision.get("equity_estimate") or {}
        if eq_info_flop.get("estimated_equity") is not None:
            try:
                base_from_turn_equity = float(eq_info_flop["estimated_equity"])
            except (TypeError, ValueError):
                base_from_turn_equity = None

    # -------- Оценка equity на ривере --------
    equity_estimate = _estimate_river_equity(
        base_from_turn=base_from_turn_equity,
        multiway=context["multiway"],
        hero_ip=context["hero_ip"],
        preflop_role=context["preflop_role"],
        action_type=action_type,
    )

    river_eq_value = None
    if equity_estimate and equity_estimate.get("estimated_equity") is not None:
        try:
            river_eq_value = float(equity_estimate["estimated_equity"])
        except (TypeError, ValueError):
            river_eq_value = None

    hand_block = {
        "base_from_turn_equity": base_from_turn_equity,
        "note": "На ривере в v1 мы опираемся на оценку equity с тёрна, слегка подстраивая её под контекст ривера.",
    }

    # -------- Оценка качества решения (decision_quality) --------
    decision_quality = "unknown"
    quality_comment = "Не удалось оценить качество решения на ривере: не хватает данных о силе руки или equity."

    strength_for_logic = river_eq_value or base_from_turn_equity

    if strength_for_logic is not None:
        s = float(strength_for_logic)

        very_strong = s >= 0.75
        strong = s >= 0.65
        medium = 0.45 <= s < 0.65
        weak = s <= 0.35

        multiway = context["multiway"]
        ip = context["hero_ip"]

        q = "unknown"
        reason = ""

        if action_type in ("bet_vs_check", "bet"):
            if very_strong or strong:
                q = "good"
                reason = "Велью-бет на ривере с сильной готовой рукой выглядит стандартно и логично."
            elif medium:
                if multiway:
                    q = "ok"
                    reason = "Ставка на ривере с рукой средней силы в мультипоте может быть пограничной, но в ряде спотов остаётся ок."
                else:
                    q = "ok"
                    reason = "Ставка на ривере с рукой средней силы может быть ок, если видишь добор с более слабыми руками оппонента."
            else:
                if not multiway and ip:
                    q = "risky"
                    reason = "Блефовая ставка на ривере в хедз-ап поте в позиции — агрессивное, но потенциально оправданное решение."
                else:
                    q = "risky"
                    reason = "Блефовая ставка на ривере со слабой рукой в мультипоте или без позиции чаще всего рискованна."

        elif action_type == "check":
            if very_strong and ip and not multiway:
                q = "risky"
                reason = "Чек на ривере с очень сильной рукой в хедз-ап поте в позиции может недобрать велью."
            elif weak:
                q = "good"
                reason = "Чек на ривере со слабой рукой без хорошего SDV — нормальный контроль банка."
            else:
                q = "ok"
                reason = "Чек на ривере с рукой средней силы часто нейтрален: ты контролируешь банк и не превращаешь руку в блеф."

        elif action_type in ("call_vs_bet", "call"):
            if very_strong or strong:
                q = "good"
                reason = "Колл на ривере с сильной рукой чаще всего выглядит логично против стандартных ставок."
            elif weak:
                q = "risky"
                reason = "Колл ставки на ривере со слабой рукой без явных ридсов — потенциально минусовое решение."
            else:
                q = "ok"
                reason = "Колл на ривере с рукой средней силы может быть ок, если диапазон оппонента включает достаточное количество блефов."

        elif action_type in ("raise_vs_bet", "raise"):
            if very_strong:
                q = "good"
                reason = "Рейз на ривере с очень сильной рукой — стандартный велью-розыгрыш."
            elif strong or medium:
                if multiway:
                    q = "risky"
                    reason = "Чек-рейз или рейз на ривере с ненатсовой рукой в мультипоте выглядит рискованным."
                else:
                    q = "ok"
                    reason = "Рейз на ривере с рукой ненатсовой силы может быть ок против переагрессивных оппонентов, но в целом линия пограничная."
            else:
                q = "risky"
                reason = "Блефовый рейз на ривере со слабой рукой — одна из самых рискованных линий."

        elif action_type in ("fold_vs_bet", "fold"):
            if very_strong or strong:
                q = "bad"
                reason = "Фолд сильной руки на ривере без экстремально узкого диапазона оппонента выглядит слишком тайтовым."
            elif weak:
                q = "good"
                reason = "Фолд слабой руки без SDV против ставки на ривере — нормальное аккуратное решение."
            else:
                q = "ok"
                reason = "Фолд руки средней силы на ривере может быть ок, особенно против крупного сайзинга и тайтового диапазона."

        decision_quality = q
        if reason:
            quality_comment = reason

    # -------- Сайзинг --------
    amount = getattr(first, "amount", None)
    pot_before = getattr(first, "pot_before", None)
    pct_pot = getattr(first, "pct_pot", None)

    sizing = {
        "amount": amount,
        "pot_before": pot_before,
        "pct_pot": pct_pot,
    }

    # -------- EV estimate (только где есть смысл в v1) --------
    # Сейчас добавляем именно то, что тебе важно для варианта A:
    # чек в позиции с высокой equity => missed value => отрицательный EV.
    ev_estimate = _estimate_missed_value_ev_on_river(
        action_type=action_type,
        river_equity=river_eq_value,
        pot_before=pot_before,
        hero_ip=context["hero_ip"],
        multiway=context["multiway"],
    )

    # -------- Финальный комментарий --------
    pct_str = None
    if pct_pot is not None:
        try:
            pct_str = f"{pct_pot * 100:.1f}%"
        except Exception:
            pct_str = None

    multi_part = "в мультипоте" if context["multiway"] else "в хедз-ап банке"
    pos_part = "в позиции" if context["hero_ip"] else "без позиции"

    size_part = ""
    if raw_action in ("bet", "raise") and amount is not None and pot_before is not None:
        size_part = f" Размер ставки на ривере: {amount:.2f} в пот {pot_before:.2f}"
        if pct_str:
            size_part += f" (~{pct_str} пота)."

    quality_part = ""
    if decision_quality != "unknown":
        quality_part = f" Оценка решения движком: {decision_quality}. {quality_comment}"

    equity_part = ""
    if equity_estimate and equity_estimate.get("estimated_equity") is not None:
        equity_part = (
            f" Оценочная equity на ривере против диапазона оппонента ≈ "
            f"{equity_estimate['estimated_equity']:.2f}."
        )

    ev_part = ""
    if ev_estimate and ev_estimate.get("ev_action") is not None:
        try:
            ev_part = f" EV(action)≈{float(ev_estimate['ev_action']):.4f}."
        except Exception:
            ev_part = ""

    comment = (
        f"Тип действия на ривере: {action_type}. "
        f"Ты играешь {multi_part} {pos_part}.{size_part}"
        f"{quality_part}{equity_part} {ev_part}".rstrip()
    )

    return {
        "action_type": action_type,
        "action_kind": raw_action,
        "sizing": sizing,
        "context": context,
        "hand": hand_block,
        "equity_estimate": equity_estimate,
        "ev_estimate": ev_estimate,
        "decision_quality": decision_quality,
        "quality_comment": quality_comment,
        "comment": comment,
    }
