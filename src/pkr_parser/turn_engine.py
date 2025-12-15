from __future__ import annotations
from .ev_tools import compute_ev_estimate_v1
from typing import Optional, Dict, Any, List


RANK_ORDER = {
    "2": 2,
    "3": 3,
    "4": 4,
    "5": 5,
    "6": 6,
    "7": 7,
    "8": 8,
    "9": 9,
    "T": 10,
    "J": 11,
    "Q": 12,
    "K": 13,
    "A": 14,
}


def _clamp_turn(value: float, min_value: float = 0.05, max_value: float = 0.95) -> float:
    """Ограничиваем значение equity в разумных границах."""
    if value < min_value:
        return min_value
    if value > max_value:
        return max_value
    return value


def _get_preflop_role(hero_preflop_analysis: Optional[Any], hero_position: Optional[str]) -> str:
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


def _parse_rank(card: str) -> Optional[int]:
    """
    Парсим ранг карты вида 'Kh', '9c' и т.п.
    Возвращаем числовое значение или None при ошибке.
    """
    if not card or len(card) < 2:
        return None
    rank_char = card[0].upper()
    return RANK_ORDER.get(rank_char)


def _parse_suit(card: str) -> Optional[str]:
    """
    Парсим масть карты ('h', 'd', 'c', 's').
    """
    if not card or len(card) < 2:
        return None
    return card[1].lower()


def _classify_turn_texture(
    board: Optional[List[str]],
    approx_category_from_flop: Optional[str],
) -> Dict[str, Optional[str]]:
    """
    Очень грубая классификация текстуры тёрна относительно флопа.

    Возвращает словарь:
      {
        "turn_card_type": ...,
        "overall_texture": ...,
        "impact_on_equity": ...
      }

    где:
      - turn_card_type: blank / overcard / undercard / middle_card / paired_board /
                        flush_complete / flush_card / straight_card / unknown
      - overall_texture: dry / semi_wet / wet / monotone / unknown
      - impact_on_equity: positive / neutral / negative / unknown
    """
    if not board or len(board) < 4:
        return {
            "turn_card_type": None,
            "overall_texture": None,
            "impact_on_equity": None,
        }

    flop_cards = board[:3]
    turn_card = board[3]

    flop_ranks = []
    flop_suits = []
    for c in flop_cards:
        r = _parse_rank(c)
        s = _parse_suit(c)
        if r is not None:
            flop_ranks.append(r)
        if s is not None:
            flop_suits.append(s)

    turn_rank = _parse_rank(turn_card)
    turn_suit = _parse_suit(turn_card)

    if len(flop_ranks) != 3 or turn_rank is None or turn_suit is None:
        return {
            "turn_card_type": None,
            "overall_texture": None,
            "impact_on_equity": None,
        }

    # --- базовые характеристики флопа ---
    min_rank = min(flop_ranks)
    max_rank = max(flop_ranks)
    rank_span = max_rank - min_rank

    # Масти
    suit_counts: Dict[str, int] = {}
    for s in flop_suits:
        suit_counts[s] = suit_counts.get(s, 0) + 1
    max_suit_count = max(suit_counts.values()) if suit_counts else 0

    # monotone / two-tone / rainbow
    if max_suit_count == 3:
        flop_texture = "monotone"
    elif max_suit_count == 2:
        flop_texture = "two_tone"
    else:
        flop_texture = "rainbow"

    # Насколько флоп коннектed (straight-потенциал)
    if rank_span <= 4:
        straighty_flop = True
    else:
        straighty_flop = False

    # --- классификация карты тёрна ---
    turn_card_type = "middle_card"
    impact_on_equity = "neutral"

    # Paired board
    if turn_rank in flop_ranks:
        turn_card_type = "paired_board"
    else:
        # over / under / middle
        if turn_rank > max_rank:
            turn_card_type = "overcard"
        elif turn_rank < min_rank:
            turn_card_type = "undercard"
        else:
            turn_card_type = "middle_card"

    # Flush-потенциал
    flush_suit = None
    for s, cnt in suit_counts.items():
        if cnt >= 2:
            flush_suit = s
            break

    flush_complete = False
    flush_card = False
    if flush_suit is not None:
        if turn_suit == flush_suit and suit_counts[flush_suit] == 2:
            flush_complete = True
            turn_card_type = "flush_complete"
        elif turn_suit == flush_suit and suit_counts[flush_suit] == 3:
            flush_card = True

    # Straight-потенциал (очень приблизительно)
    straight_card = False
    if straighty_flop:
        # Если флоп уже "стрейтовый", то карта вокруг диапазона [min_rank-1 .. max_rank+1]
        # считаем усиливающей стрит-потенциал.
        if min_rank - 1 <= turn_rank <= max_rank + 1:
            straight_card = True
            if turn_card_type not in ("flush_complete", "paired_board"):
                turn_card_type = "straight_card"

    # --- overall_texture ---
    if flop_texture == "monotone":
        overall_texture = "monotone"
    elif flush_complete or straight_card or turn_card_type in ("paired_board", "overcard", "flush_complete"):
        # Доска становится более опасной
        if straighty_flop or flush_complete or flush_card:
            overall_texture = "wet"
        else:
            overall_texture = "semi_wet"
    else:
        if straighty_flop or flush_suit is not None:
            overall_texture = "semi_wet"
        else:
            overall_texture = "dry"

    # --- impact_on_equity ---
    # Здесь мы делаем очень грубую эвристику, ориентируясь только на категорию руки с флопа.
    cat = (approx_category_from_flop or "").lower()

    if cat in ("set", "trips", "full_house", "quads"):
        # Для очень сильных рук:
        if turn_card_type == "paired_board":
            impact_on_equity = "positive"
        elif flush_complete or straight_card:
            impact_on_equity = "neutral"
        else:
            impact_on_equity = "positive"
    elif cat in ("two_pair", "overpair", "pair"):
        # Для парных рук:
        if turn_card_type in ("flush_complete", "straight_card", "overcard"):
            impact_on_equity = "negative"
        elif turn_card_type == "paired_board":
            # Борд пары может быть как хорошо, так и плохо; оставим neutral
            impact_on_equity = "neutral"
        else:
            impact_on_equity = "neutral"
    elif cat in ("high_card", ""):
        # Для воздуха:
        if flush_complete or straight_card or turn_card_type in ("overcard", "paired_board"):
            impact_on_equity = "positive"
        else:
            impact_on_equity = "neutral"
    else:
        impact_on_equity = "neutral"

    return {
        "turn_card_type": turn_card_type,
        "overall_texture": overall_texture,
        "impact_on_equity": impact_on_equity,
    }


def _estimate_turn_equity(
    approx_strength: Optional[float],
    flop_equity: Optional[float],
    multiway: bool,
    hero_ip: bool,
    preflop_role: str,
    action_type: str,
) -> Optional[Dict[str, Any]]:
    """
    Очень грубая оценка equity героя на тёрне на основе:
      - примерной силы руки с флопа (strength_score),
      - флоповой equity (если есть),
      - контекста (multiway / IP / префлоп-роль),
      - линии на тёрне (bet/check/call/raise/fold).

    Это НЕ солвер, а эвристика, нужна как учебный ориентир.
    """

    if approx_strength is None and flop_equity is None:
        return None

    explanation_parts = []

    base_source = None
    base_value = None

    if approx_strength is not None:
        base_source = "strength_score"
        base_value = float(approx_strength)
    elif flop_equity is not None:
        base_source = "flop_equity"
        base_value = float(flop_equity)

    if base_value is None:
        return None

    explanation_parts.append(
        f"Базовая оценка на тёрне строится от {base_source}≈{base_value:.2f}."
    )

    # Базовая "сырая" equity
    base_equity = base_value

    # Мультипот всегда уменьшает реализуемость equity
    if multiway:
        base_equity -= 0.05
        explanation_parts.append(
            "Мультипот (несколько оппонентов) снижает реализуемую equity примерно на 5 п.п."
        )

    # Позиция
    if hero_ip:
        base_equity += 0.02
        explanation_parts.append(
            "Игра в позиции на тёрне слегка повышает эффективную equity (около 2 п.п.)."
        )
    else:
        base_equity -= 0.03
        explanation_parts.append(
            "Игра без позиции на тёрне снижает эффективную equity примерно на 3 п.п."
        )

    # Роль префлоп
    if preflop_role == "aggressor":
        base_equity += 0.02
        explanation_parts.append(
            "Ты префлоп-агрессор, диапазон в среднем сильнее — добавляем около 2 п.п. equity."
        )
    elif preflop_role == "caller":
        base_equity -= 0.01
        explanation_parts.append(
            "Ты префлоп-коллер, диапазон немного слабее — вычитаем около 1 п.п. equity."
        )

    # Линия на тёрне: как ты реализуешь свою equity
    if action_type in ("bet_vs_check", "raise_vs_bet"):
        # Агрессия на тёрне повышает реализуемость equity
        base_equity += 0.02
        explanation_parts.append(
            "Агрессия на тёрне (ставка/рейз) увеличивает реализацию equity примерно на 2 п.п."
        )
    elif action_type == "check":
        # Чек чуть-чуть уменьшает реализацию (особенно с сильной рукой)
        base_equity -= 0.01
        explanation_parts.append(
            "Пассивная линия (чек) слегка уменьшает реализуемость equity."
        )
    elif action_type in ("call_vs_bet", "call"):
        # Колл сохраняет реализацию, но без fold equity
        explanation_parts.append(
            "Колл на тёрне сохраняет часть equity, но без fold equity."
        )
    elif action_type in ("fold_vs_bet", "fold"):
        explanation_parts.append(
            "Фолд на тёрне завершает раздачу, но оценка equity рассматривает гипотетическую продолженную игру."
        )

    estimated_equity = _clamp_turn(base_equity, 0.05, 0.95)

    explanation = " ".join(explanation_parts)

    return {
        "estimated_equity": float(f"{estimated_equity:.3f}"),
        "model": "simple_turn_model",
        "explanation": explanation,
    }


def evaluate_hero_turn_decision(
    actions: List[Any],
    hero_name: Optional[str],
    hero_position: Optional[str],
    hero_preflop_analysis: Optional[Any],
    hero_flop_decision: Optional[Dict[str, Any]],
    board: Optional[List[str]],
) -> Optional[Dict[str, Any]]:
    """
    v1-анализ ПЕРВОГО решения героя на тёрне.

    Возвращает словарь:
      - action_type: логическая категория (bet_vs_check / call_vs_bet / raise_vs_bet / check / fold_vs_bet / ...)
      - action_kind: реальное действие (bet/call/check/raise/fold)
      - sizing: { amount, pot_before, pct_pot }
      - context: { players_to_turn, multiway, hero_ip, hero_position, preflop_role }
      - hand: {
            approx_category_from_flop,
            approx_strength_score_from_flop,
            flop_equity_estimate,
            evolution,
            evolution_detail,
            board_texture: { turn_card_type, overall_texture, impact_on_equity }
        }
      - equity_estimate: { estimated_equity, model, explanation }
      - decision_quality: оценка качества (good / ok / risky / bad / unknown)
      - quality_comment: текстовое объяснение оценки
      - comment: общий краткий комментарий по споту
    """
    if not hero_name:
        return None

    # -------- Действия на тёрне --------
    turn_actions = [a for a in actions if getattr(a, "street", None) == "turn"]
    if not turn_actions:
        return None

    hero_turn_actions = [
        a for a in turn_actions
        if getattr(a, "player", None) == hero_name
        and getattr(a, "action", None) not in ("uncalled",)
    ]
    if not hero_turn_actions:
        return None

    first = hero_turn_actions[0]
    idx_first = turn_actions.index(first)
    prior = turn_actions[:idx_first]

    facing_bet = any(getattr(a, "action", None) in ("bet", "raise") for a in prior)
    raw_action = getattr(first, "action", None)

    # -------- Тип действия на тёрне --------
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

    # -------- Контекст тёрна --------
    players_to_turn = len({getattr(a, "player", None) for a in turn_actions})

    last_other_idx = -1
    for i, a in enumerate(turn_actions):
        if getattr(a, "player", None) != hero_name:
            last_other_idx = i
    hero_ip = idx_first > last_other_idx if last_other_idx >= 0 else True

    preflop_role = _get_preflop_role(hero_preflop_analysis, hero_position)

    context = {
        "players_to_turn": players_to_turn,
        "multiway": players_to_turn > 2,
        "hero_ip": hero_ip,
        "hero_position": hero_position,
        "preflop_role": preflop_role,
    }

    # -------- Инфа с флопа --------
    approx_category = None
    approx_strength = None
    flop_equity = None

    if hero_flop_decision:
        hand_info = hero_flop_decision.get("hand") or {}
        approx_category = hand_info.get("category")
        approx_strength = hand_info.get("strength_score")

        eq_info = hero_flop_decision.get("equity_estimate") or {}
        flop_equity = eq_info.get("estimated_equity")

    # Если нет strength_score — попробуем взять flop-equity как суррогат
    if approx_strength is None and flop_equity is not None:
        try:
            approx_strength = float(flop_equity)
        except (TypeError, ValueError):
            approx_strength = None

    # -------- Классификация текстуры тёрна --------
    board_texture = _classify_turn_texture(
        board=board,
        approx_category_from_flop=approx_category,
    )

    # -------- Оценка equity на тёрне --------
    equity_estimate = _estimate_turn_equity(
        approx_strength=approx_strength,
        flop_equity=flop_equity,
        multiway=context["multiway"],
        hero_ip=context["hero_ip"],
        preflop_role=context["preflop_role"],
        action_type=action_type,
    )

    turn_eq_value = None
    if equity_estimate and equity_estimate.get("estimated_equity") is not None:
        try:
            turn_eq_value = float(equity_estimate["estimated_equity"])
        except (TypeError, ValueError):
            turn_eq_value = None

    # -------- Эволюция equity от флопа к тёрну --------
    evolution = "unknown"
    evolution_detail: Optional[str] = None

    if flop_equity is not None and turn_eq_value is not None:
        try:
            fe = float(flop_equity)
        except (TypeError, ValueError):
            fe = None

        if fe is not None:
            diff = turn_eq_value - fe
            threshold = 0.08  # 8 п.п.

            if diff > threshold:
                evolution = "improved"
                evolution_detail = "equity_increased"
            elif diff < -threshold:
                evolution = "worsened"
                evolution_detail = "equity_decreased"
            else:
                evolution = "same"
                evolution_detail = "equity_stable"

    # -------- Блок hand для тёрна --------
    hand_block = {
        "approx_category_from_flop": approx_category,
        "approx_strength_score_from_flop": approx_strength,
        "flop_equity_estimate": flop_equity,
        "evolution": evolution,
        "evolution_detail": evolution_detail,
        "board_texture": board_texture,
    }

    # -------- Оценка качества решения (decision_quality) --------
    decision_quality = "unknown"
    quality_comment = "Не удалось оценить качество решения на тёрне: не хватает данных о силе руки или equity."

    strength_for_logic = approx_strength
    if strength_for_logic is None and turn_eq_value is not None:
        strength_for_logic = turn_eq_value

    if strength_for_logic is not None:
        s = float(strength_for_logic)

        very_strong = s >= 0.75
        strong = s >= 0.65
        medium = 0.45 <= s < 0.65
        weak = s <= 0.35

        multiway = context["multiway"]
        ip = context["hero_ip"]

        impact = (board_texture.get("impact_on_equity") or "neutral").lower()

        q = "unknown"
        reason = ""

        if action_type in ("bet_vs_check", "bet"):
            if very_strong or strong:
                # В мультивее с сильной рукой ставка всё равно ок, но можно пометить чуть менее оптимистично
                if multiway and impact == "negative":
                    q = "ok"
                    reason = "Ставка на тёрне с сильной рукой в мультипоте на опасной карте борда может быть чуть переоценённой, но в целом выглядит приемлемым велью-розыгрышем."
                else:
                    q = "good"
                    reason = "Ставка на тёрне с сильной готовой рукой выглядит стандартным велью-розыгрышем."
            elif medium:
                if multiway and impact == "negative":
                    q = "risky"
                    reason = "Баррель на тёрне с рукой средней силы в мультипоте на опасной карте борда выглядит рискованным."
                else:
                    q = "ok"
                    reason = "Ставка на тёрне с рукой средней силы допустима, но сильно зависит от текстуры борда и диапазона оппонента."
            else:
                # блефовая ставка
                if not multiway and ip and impact != "negative":
                    q = "ok"
                    reason = "Блефовая ставка на тёрне в хедз-ап поте в позиции на не самой опасной карте борда — агрессивный, но допустимый приём."
                else:
                    q = "risky"
                    reason = "Блефовая ставка на тёрне со слабой рукой в мультипоте или без позиции, особенно на опасной карте борда, выглядит рискованной."

        elif action_type == "check":
            if very_strong and not multiway and ip and impact != "negative":
                q = "risky"
                reason = "Чек на тёрне с очень сильной рукой в хедз-ап поте в позиции на относительно безопасной карте борда может недобрать велью."
            elif weak:
                q = "good"
                if ip:
                    reason = "Чек на тёрне с очень слабой рукой в позиции — стандартная линия: ты контролируешь банк и не раздуваешь его с air."
                else:
                    reason = "Чек на тёрне с очень слабой рукой без позиции — аккуратное решение, ты минимизируешь потери с air."
            else:
                q = "ok"
                if ip:
                    reason = "Чек на тёрне с рукой средней силы допустим, особенно на опасных бордах или против агрессивных оппонентов."
                else:
                    reason = "Чек на тёрне с рукой средней силы вне позиции допустим, если ты не хочешь раздувать банк."

        elif action_type in ("call_vs_bet", "call"):
            if strong or very_strong:
                if impact == "negative" and multiway:
                    q = "ok"
                    reason = "Колл ставки на тёрне с достаточно сильной рукой в мультипоте на опасной карте борда выглядит аккуратным, но не всегда максимально прибыльным."
                else:
                    q = "good"
                    reason = "Колл ставки на тёрне с сильной рукой выглядит логичным продолжением линии."
            elif weak:
                q = "risky"
                reason = "Колл ставки на тёрне со слабой рукой без хороших дро может быть минусовым решением."
            else:
                q = "ok"
                reason = "Колл на тёрне с рукой средней силы может быть нормальным, особенно против адекватного сайзинга и не самого опасного борда."

        elif action_type in ("raise_vs_bet", "raise"):
            if very_strong:
                if impact == "negative" and multiway:
                    q = "ok"
                    reason = "Рейз на тёрне с очень сильной рукой на опасной карте борда в мультипоте может выглядеть чуть слишком агрессивным, но в целом остаётся велью-розыгрышем."
                else:
                    q = "good"
                    reason = "Рейз на тёрне с очень сильной рукой — стандартный велью-розыгрыш."
            elif strong or medium:
                if impact == "negative" and multiway:
                    q = "risky"
                    reason = "Рейз на тёрне с рукой средней/сильной силы в мультипоте на опасной карте борда выглядит рискованным."
                else:
                    q = "ok"
                    reason = "Рейз на тёрне с рукой средней/сильной силы может быть ок, но сильно зависит от диапазонов и текстуры борда."
            else:
                if not multiway and ip and impact != "negative":
                    q = "ok"
                    reason = "Блефовый рейз на тёрне в хедз-ап поте в позиции на не самой опасной карте борда — очень агрессивный, но иногда допустимый приём."
                else:
                    q = "risky"
                    reason = "Блефовый рейз на тёрне со слабой рукой в мультипоте или без позиции, особенно на опасной карте борда, выглядит рискованным."

        elif action_type in ("fold_vs_bet", "fold"):
            if strong or very_strong:
                if impact == "negative":
                    q = "ok"
                    reason = "Фолд достаточно сильной руки на тёрне на очень опасной карте борда может быть защитимым, но часто выглядит слишком тайтовым."
                else:
                    q = "bad"
                    reason = "Фолд достаточно сильной руки на тёрне чаще всего выглядит слишком тайтовым."
            elif weak:
                q = "good"
                reason = "Фолд слабой руки без перспективных дро против ставки на тёрне — нормальное аккуратное решение."
            else:
                q = "ok"
                reason = "Фолд руки средней силы на тёрне может быть ок, особенно против крупного сайзинга или тайтовых диапазонов на опасной карте борда."

        decision_quality = q
        if reason:
            quality_comment = reason

    # -------- Сайзинг и финальный комментарий --------
    amount = getattr(first, "amount", None)
    pot_before = getattr(first, "pot_before", None)
    pct_pot = getattr(first, "pct_pot", None)

    sizing = {
        "amount": amount,
        "pot_before": pot_before,
        "pct_pot": pct_pot,
    }

    pct_str = None
    if pct_pot is not None:
        try:
            pct_str = f"{pct_pot * 100:.1f}%"
        except Exception:
            pct_str = None

    size_part = ""
    if raw_action in ("bet", "raise") and amount is not None and pot_before is not None:
        size_part = f" Размер ставки на тёрне: {amount:.2f} в пот {pot_before:.2f}"
        if pct_str:
            size_part += f" (~{pct_str} пота)."

    multi_part = "в мультипоте" if context["multiway"] else "в хедз-ап банке"
    pos_part = "в позиции" if context["hero_ip"] else "без позиции"

    evolution_part = ""
    if evolution == "improved":
        evolution_part = " По сравнению с флопом твоя реализуемая equity на тёрне выглядит улучшившейся."
    elif evolution == "worsened":
        evolution_part = " По сравнению с флопом твоя реализуемая equity на тёрне выглядит ухудшившейся."
    elif evolution == "same":
        evolution_part = " По сравнению с флопом твоя реализуемая equity на тёрне примерно не изменилась."

    texture_part = ""
    if board_texture:
        t_type = board_texture.get("turn_card_type")
        impact = board_texture.get("impact_on_equity")
        if t_type is not None:
            texture_part += f" Карта тёрна классифицируется как '{t_type}'."
        if impact is not None:
            if impact == "negative":
                texture_part += " Влияние карты тёрна на твою руку скорее негативное."
            elif impact == "positive":
                texture_part += " Карта тёрна в целом помогает твоему диапазону/руке."
            elif impact == "neutral":
                texture_part += " Карта тёрна нейтральна для твоей руки/диапазона."

    quality_part = ""
    if decision_quality != "unknown":
        quality_part = f" Оценка решения движком: {decision_quality}. {quality_comment}"

    equity_part = ""
    if equity_estimate and equity_estimate.get("estimated_equity") is not None:
        equity_part = (
            f" Оценочная equity на тёрне против диапазона оппонента ≈ "
            f"{equity_estimate['estimated_equity']:.2f}."
        )

    comment = (
        f"Тип действия на тёрне: {action_type}. "
        f"Ты играешь {multi_part} {pos_part}.{size_part}"
        f"{evolution_part}{texture_part}{quality_part}{equity_part}"
    )
       # hero_turn_actions у тебя — список действий героя на тёрне
    hero_turn_action = hero_turn_actions[0] if hero_turn_actions else None
    action_kind_for_ev = hero_turn_action.action if hero_turn_action else None

    ev_estimate = compute_ev_estimate_v1(
        action_kind=action_kind_for_ev,
        sizing=sizing,
        equity_estimate=equity_estimate,
        facing_bet=facing_bet,
    )


    return {
        "action_type": action_type,
        "action_kind": raw_action,
        "sizing": sizing,
        "context": context,
        "hand": hand_block,
        "equity_estimate": equity_estimate,
        "decision_quality": decision_quality,
        "quality_comment": quality_comment,
        "comment": comment,
        "ev_estimate": ev_estimate,

    }
