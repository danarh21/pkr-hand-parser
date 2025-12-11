import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def load_hands(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Файл {path} не найден. Сначала запусти main.py, чтобы создать hands.json")

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError("Ожидался список раздач (list) в hands.json")

    return data


def find_hand_by_id(hands: List[Dict[str, Any]], hand_id: str) -> Optional[Dict[str, Any]]:
    for hand in hands:
        if hand.get("hand_id") == hand_id:
            return hand
    return None


def format_cards(cards: Optional[List[str]]) -> str:
    if not cards:
        return "-"
    return " ".join(cards)


def format_board(board: Optional[List[str]]) -> str:
    if not board:
        return "-"
    return " ".join(board)


def safe_float(v: Any) -> Optional[float]:
    if isinstance(v, (int, float)):
        return float(v)
    return None


# ==========================
#  ПРЕФЛОП
# ==========================

def print_preflop_section(hand: Dict[str, Any],
                          good_points: List[str],
                          improvement_points: List[str]) -> None:
    print("=== ПРЕФЛОП ===")
    hero_name = hand.get("hero_name")
    hero_pos = hand.get("hero_position")
    hero_cards = hand.get("hero_cards") or []
    hero_preflop_analysis = hand.get("hero_preflop_analysis") or {}
    hero_preflop_equity = hand.get("hero_preflop_equity") or {}
    hero_preflop_decision = hand.get("hero_preflop_decision") or {}

    print(f"Герой: {hero_name} | Позиция: {hero_pos}")
    print(f"Карты героя: {format_cards(hero_cards)}")

    if hero_preflop_equity:
        hand_key = hero_preflop_equity.get("hand_key")
        cat = hero_preflop_equity.get("category")
        est_eq = safe_float(hero_preflop_equity.get("estimated_equity_vs_unknown"))
        notes = hero_preflop_equity.get("notes")

        print(f"Префлоп-оценка руки по модели: {hand_key} (категория: {cat})")
        if est_eq is not None:
            print(f"Оценочная equity vs unknown: {est_eq:.2f}")
        if notes:
            print(f"Комментарий по диапазону (MOS): {notes}")

    if hero_preflop_analysis:
        atype = hero_preflop_analysis.get("action_type")
        was_first_in = hero_preflop_analysis.get("was_first_in")
        facing_raises = hero_preflop_analysis.get("facing_raises")
        facing_callers = hero_preflop_analysis.get("facing_callers")
        print()
        print("Контекст префлопа:")
        print(f"  Тип спота: {atype}, first-in: {was_first_in}, против рейзов: {facing_raises}, против коллов: {facing_callers}")

    if hero_preflop_decision:
        dq = hero_preflop_decision.get("decision_quality")
        comment = hero_preflop_decision.get("comment")
        math_block = hero_preflop_decision.get("math") or {}

        print()
        print("Решение на префлопе:")
        if dq:
            print(f"  Оценка качества модели: {dq}")
        pot_before = safe_float(math_block.get("pot_before"))
        invest = safe_float(math_block.get("investment"))
        req_eq = safe_float(math_block.get("required_equity"))
        est_eq = safe_float(math_block.get("estimated_equity"))
        ev_simple = safe_float(math_block.get("ev_simple"))
        if pot_before is not None and invest is not None:
            print(f"  Пот до решения: {pot_before:.2f}, вложение: {invest:.2f}")
        if req_eq is not None and est_eq is not None:
            print(f"  Требуемая equity по пот-оддсам: {req_eq:.2f}, оценочная equity руки: {est_eq:.2f}")
        if ev_simple is not None:
            print(f"  Примерная EV решения по модели: {ev_simple:.3f}")
        if comment:
            print(f"  Разбор модели: {comment}")

        # Коучинговые выводы по префлопу
        action_type = hero_preflop_decision.get("action_type")
        if dq == "good":
            good_points.append("Префлоп: выбранная линия в этой раздаче выглядит плюсовой и дисциплинированной по модели.")
        elif dq in ("ok", "neutral"):
            improvement_points.append("Префлоп: решение допустимое, но можно уточнить диапазон открытия/колла относительно MOS-чартов и позиций.")
        elif dq in ("risky", "mistake", "bad"):
            if action_type in ("open_raise", "iso_raise"):
                improvement_points.append(
                    "Префлоп: открытие выглядит слишком амбициозным. В подобных спотах лучше ужесточить диапазон, "
                    "особенно из ранних позиций или с руками средней/низкой категории."
                )
            elif action_type == "call_vs_raise":
                improvement_points.append(
                    "Префлоп: колл против рейза на границе диапазона. Часто здесь выгоднее либо 3-бетить сильные руки, "
                    "либо просто фолдить маргинальные, чтобы не заходить в сложные споты без позиции."
                )
            elif action_type in ("3bet", "4bet", "5bet_plus"):
                improvement_points.append(
                    "Префлоп: агрессивная линия (3-бет/4-бет) может быть переоценкой силы руки. "
                    "Имеет смысл свериться с твоими 3-бет/4-бет диапазонами и посмотреть, не лучше ли колл или фолд."
                )
            else:
                improvement_points.append(
                    "Префлоп: модель считает это решение рискованным. Стоит перепроверить этот спот в чарте и "
                    "отметить для себя, какие руки ты реально хочешь продолжать играть."
                )

    print()


# ==========================
#  ФЛОП
# ==========================

def print_flop_section(hand: Dict[str, Any],
                       good_points: List[str],
                       improvement_points: List[str]) -> None:
    print("=== ФЛОП ===")
    board = hand.get("board") or []
    flop_board = board[:3]
    print(f"Борд (флоп): {format_board(flop_board)}")

    hero_flop_cat = hand.get("hero_flop_hand_category")
    hero_flop_detail = hand.get("hero_flop_hand_detail") or {}
    hero_flop_decision = hand.get("hero_flop_decision") or {}

    if hero_flop_cat is None and not hero_flop_decision:
        print("Герой не сыграл флоп (фолд до флопа или нет действий на флопе).")
        print()
        return

    made = hero_flop_detail.get("made_hand")
    pair_kind = hero_flop_detail.get("pair_kind")

    print(f"Категория руки героя на флопе: {hero_flop_cat}")
    if made:
        print(f"  Сделанная рука: {made}")
    if pair_kind:
        print(f"  Тип пары: {pair_kind}")

    eq_info = hero_flop_decision.get("equity_estimate") or {}
    est_eq = safe_float(eq_info.get("estimated_equity"))
    if est_eq is not None:
        print(f"Оценочная equity на флопе (по модели): {est_eq:.2f}")

    context = hero_flop_decision.get("context") or {}
    players_to_flop = context.get("players_to_flop")
    multiway = context.get("multiway")
    hero_ip = context.get("hero_ip")
    preflop_role = context.get("preflop_role")
    hero_pos = context.get("hero_position")

    sizing = hero_flop_decision.get("sizing") or {}
    amount = safe_float(sizing.get("amount"))
    pot_before = safe_float(sizing.get("pot_before"))
    pct_pot = safe_float(sizing.get("pct_pot"))

    print()
    print("Контекст флопа:")
    print(f"  Игроков на флопе: {players_to_flop}, мультивей: {multiway}, герой в позиции: {hero_ip}, роль префлоп: {preflop_role}, позиция: {hero_pos}")
    if pot_before is not None:
        print(f"  Пот до действия героя: {pot_before:.2f}")
    if amount is not None and pct_pot is not None:
        print(f"  Размер ставки/рейза героя: {amount:.2f} (~{pct_pot*100:.1f}% пота)")

    dq = hero_flop_decision.get("decision_quality")
    comment = hero_flop_decision.get("comment")
    quality_comment = hero_flop_decision.get("quality_comment")
    action_type = hero_flop_decision.get("action_type")

    print()
    print("Решение на флопе:")
    if dq:
        print(f"  Оценка качества модели: {dq}")
    if quality_comment:
        print(f"  Краткий вердикт: {quality_comment}")
    if comment:
        print(f"  Разбор модели: {comment}")

    if dq == "good":
        good_points.append("Флоп: выбранная линия в этой раздаче логично соответствует силе руки и структуре борда.")
    elif dq in ("ok", "neutral"):
        improvement_points.append(
            "Флоп: решение допустимое, но можно продумать более агрессивный или более тайтовый план "
            "в зависимости от текстуры борда и количества оппонентов."
        )
    elif dq in ("risky", "bad"):
        if hero_flop_cat == "high_card" and action_type in ("call_vs_bet", "call"):
            improvement_points.append(
                "Флоп: колл с рукой без попадания (high card) часто приводит к сложным ситуациям на тёрне/ривере. "
                "В подобных спотах выгоднее либо сразу сдаваться, либо выбирать блеф-агрессию в подходящих бордах, "
                "но не затаскивать мусорные руки в глубокие банки."
            )
        elif hero_flop_cat in ("pair", "two_pair", "set") and action_type == "check":
            improvement_points.append(
                "Флоп: с готовой рукой (пара и сильнее) часто выгоднее ставить для вэлью и защиты, "
                "особенно на дровяных бордах и против нескольких оппонентов. Чек может приводить к недобору."
            )
        elif action_type in ("bet_vs_check", "raise_vs_bet", "bet", "raise"):
            improvement_points.append(
                "Флоп: агрессивная линия выглядит рискованной. Стоит перепроверить, достаточно ли у руки equity "
                "и fold equity против диапазона соперника, и не переигрывается ли маргинальная рука."
            )
        else:
            improvement_points.append(
                "Флоп: модель считает решение рискованным. Это хороший кандидат для ручного разбора с диапазонами "
                "оппонента: какие худшие руки ты выбиваешь и какие лучшие заставляешь платить."
            )

    print()


# ==========================
#  ТЁРН
# ==========================

def print_turn_section(hand: Dict[str, Any],
                       good_points: List[str],
                       improvement_points: List[str]) -> None:
    print("=== ТЁРН ===")
    board = hand.get("board") or []
    if len(board) < 4:
        print("Тёрн отсутствует (борд короче 4 карт).")
        print()
        return

    turn_board = board[:4]
    print(f"Борд (до тёрна): {format_board(turn_board)}")

    hero_turn_decision = hand.get("hero_turn_decision") or {}

    if not hero_turn_decision:
        print("Герой не сыграл тёрн (нет действий на тёрне).")
        print()
        return

    hand_block = hero_turn_decision.get("hand") or {}
    approx_cat = hand_block.get("approx_category_from_flop")
    approx_strength = safe_float(hand_block.get("approx_strength_score_from_flop"))
    evolution = hand_block.get("evolution")
    evolution_detail = hand_block.get("evolution_detail")
    board_texture = hand_block.get("board_texture") or {}

    print("Оценка силы руки к тёрну:")
    if approx_cat:
        print(f"  Категория (от флопа): {approx_cat}")
    if approx_strength is not None:
        print(f"  Примерная strength_score с флопа: {approx_strength:.2f}")
    if evolution:
        print(f"  Эволюция относительно флопа: {evolution} ({evolution_detail})")

    if board_texture:
        t_type = board_texture.get("turn_card_type")
        overall = board_texture.get("overall_texture")
        impact = board_texture.get("impact_on_equity")
        print("Текстура тёрна:")
        print(f"  Тип карты тёрна: {t_type}")
        print(f"  Общая текстура: {overall}")
        print(f"  Влияние на твою equity: {impact}")

    eq_info = hero_turn_decision.get("equity_estimate") or {}
    est_eq = safe_float(eq_info.get("estimated_equity"))
    if est_eq is not None:
        print(f"Оценочная equity на тёрне (по модели): {est_eq:.2f}")

    context = hero_turn_decision.get("context") or {}
    players_to_turn = context.get("players_to_turn")
    multiway = context.get("multiway")
    hero_ip = context.get("hero_ip")
    hero_pos = context.get("hero_position")
    preflop_role = context.get("preflop_role")

    sizing = hero_turn_decision.get("sizing") or {}
    amount = safe_float(sizing.get("amount"))
    pot_before = safe_float(sizing.get("pot_before"))
    pct_pot = safe_float(sizing.get("pct_pot"))

    print()
    print("Контекст тёрна:")
    print(f"  Игроков на тёрне: {players_to_turn}, мультивей: {multiway}, герой в позиции: {hero_ip}, позиция: {hero_pos}, роль префлоп: {preflop_role}")
    if pot_before is not None:
        print(f"  Пот до действия героя: {pot_before:.2f}")
    if amount is not None and pct_pot is not None:
        print(f"  Размер ставки/рейза героя: {amount:.2f} (~{pct_pot*100:.1f}% пота)")

    dq = hero_turn_decision.get("decision_quality")
    comment = hero_turn_decision.get("comment")
    quality_comment = hero_turn_decision.get("quality_comment")
    action_type = hero_turn_decision.get("action_type")

    print()
    print("Решение на тёрне:")
    if dq:
        print(f"  Оценка качества модели: {dq}")
    if quality_comment:
        print(f"  Краткий вердикт: {quality_comment}")
    if comment:
        print(f"  Разбор модели: {comment}")

    if dq == "good":
        good_points.append("Тёрн: линия выглядит логичной с учётом силы руки и структуры борда.")
    elif dq in ("ok", "neutral"):
        improvement_points.append(
            "Тёрн: решение допустимое, но можно точнее планировать, где продолжать агрессию, "
            "а где контролировать банк, исходя из диапазонов и текстуры доски."
        )
    elif dq in ("risky", "bad"):
        if action_type == "check":
            improvement_points.append(
                "Тёрн: пассивная линия с относительно сильной рукой может приводить к недобору. "
                "Рассмотри ставки небольшого/среднего размера для вэлью и защиты от дров."
            )
        elif action_type in ("call_vs_bet", "call"):
            improvement_points.append(
                "Тёрн: колл в пограничной ситуации может быть переоценкой руки. Стоит чаще фолдить, "
                "если сайзинг соперника большой, а твоя equity и реализуемость сомнительны."
            )
        elif action_type in ("bet_vs_check", "raise_vs_bet", "bet", "raise"):
            improvement_points.append(
                "Тёрн: агрессивная линия выглядит рискованной. Проверь, не раздуваешь ли банк с рукой, "
                "которой удобнее было бы контролировать банк и реализовывать equity без сильного роста пота."
            )
        else:
            improvement_points.append(
                "Тёрн: модель считает решение рискованным. Это хороший кандидат для ручного разбора в софте/солвере."
            )

    print()


# ==========================
#  РИВЕР
# ==========================

def print_river_section(hand: Dict[str, Any],
                        good_points: List[str],
                        improvement_points: List[str]) -> None:
    print("=== РИВЕР ===")
    board = hand.get("board") or []
    if len(board) < 5:
        print("Ривер отсутствует (борд короче 5 карт).")
        print()
        return

    river_board = board[:5]
    print(f"Борд (до ривера): {format_board(river_board)}")

    hero_river_decision = hand.get("hero_river_decision") or {}

    if not hero_river_decision:
        print("Герой не сыграл ривер (нет действий на ривере).")
        print()
        return

    eq_info = hero_river_decision.get("equity_estimate") or {}
    est_eq = safe_float(eq_info.get("estimated_equity"))
    if est_eq is not None:
        print(f"Оценочная equity на ривере (по модели): {est_eq:.2f}")

    context = hero_river_decision.get("context") or {}
    players_to_river = context.get("players_to_river")
    multiway = context.get("multiway")
    hero_ip = context.get("hero_ip")
    hero_pos = context.get("hero_position")
    preflop_role = context.get("preflop_role")

    sizing = hero_river_decision.get("sizing") or {}
    amount = safe_float(sizing.get("amount"))
    pot_before = safe_float(sizing.get("pot_before"))
    pct_pot = safe_float(sizing.get("pct_pot"))

    print()
    print("Контекст ривера:")
    print(f"  Игроков на ривере: {players_to_river}, мультивей: {multiway}, герой в позиции: {hero_ip}, позиция: {hero_pos}, роль префлоп: {preflop_role}")
    if pot_before is not None:
        print(f"  Пот до действия героя: {pot_before:.2f}")
    if amount is not None and pct_pot is not None:
        print(f"  Размер ставки/рейза героя: {amount:.2f} (~{pct_pot*100:.1f}% пота)")

    dq = hero_river_decision.get("decision_quality")
    comment = hero_river_decision.get("comment")
    quality_comment = hero_river_decision.get("quality_comment")
    action_type = hero_river_decision.get("action_type")

    print()
    print("Решение на ривере:")
    if dq:
        print(f"  Оценка качества модели: {dq}")
    if quality_comment:
        print(f"  Краткий вердикт: {quality_comment}")
    if comment:
        print(f"  Разбор модели: {comment}")

    if dq == "good":
        good_points.append("Ривер: выбранная линия адекватна силе руки и структуре банка.")
    elif dq in ("ok", "neutral"):
        improvement_points.append(
            "Ривер: решение в целом ок, но на ривере особенно важно точно выбирать между вэлью-бетом, чек-бихайнд и фолдом. "
            "Эти споты стоит разбирать детальнее, так как они сильно влияют на итоговый винрейт."
        )
    elif dq in ("risky", "bad"):
        if est_eq is not None and est_eq >= 0.70 and action_type == "check":
            improvement_points.append(
                "Ривер: у руки высокая оценочная equity, но выбран чек. Это кандидат на missed value — "
                "в подобных ситуациях чаще выгодно ставить тонкий вэлью-бет против диапазона колла соперника."
            )
        elif est_eq is not None and est_eq < 0.30 and action_type in ("call_vs_bet", "call"):
            improvement_points.append(
                "Ривер: низкая оценочная equity при колле выглядит сомнительно. В похожих спотах чаще лучше сфолдить, "
                "особенно против крупных бетов и тайтовых линий оппонента."
            )
        elif action_type in ("bet_vs_check", "raise_vs_bet", "bet", "raise"):
            improvement_points.append(
                "Ривер: агрессивная линия рискованна. На ривере банки уже большие, поэтому блефы и тонкие бетты "
                "стоит очень внимательно подбирать под диапазоны и частоты фолдов соперников."
            )
        else:
            improvement_points.append(
                "Ривер: модель считает это решение рискованным. Это хороший спот для глубокого разбора в солвере/симуляторе."
            )

    print()


# ==========================
#  ИСХОД РАЗДАЧИ
# ==========================

def print_outcome_section(hand: Dict[str, Any]) -> None:
    print("=== ИСХОД РАЗДАЧИ ===")
    hero_name = hand.get("hero_name")

    total_pot = safe_float(hand.get("total_pot"))
    rake = safe_float(hand.get("rake"))

    if total_pot is not None:
        print(f"Общий банк (до рейка): {total_pot:.2f}")
    if rake is not None:
        print(f"Рейк: {rake:.2f}")

    winners = hand.get("winners") or []
    showdown = hand.get("showdown") or []

    showdown_by_player: Dict[str, Dict[str, Any]] = {}
    for s in showdown:
        pname = s.get("player")
        if pname:
            showdown_by_player[pname] = s

    print()
    if winners:
        print("Победитель(и):")
        for w in winners:
            pname = w.get("player")
            amount = safe_float(w.get("amount"))
            sd_info = showdown_by_player.get(pname) or {}
            sd_desc = sd_info.get("description")
            if pname == hero_name:
                if amount is not None:
                    if sd_desc:
                        print(f"  - {pname} (Герой) выиграл {amount:.2f} с комбинацией: {sd_desc}")
                    else:
                        print(f"  - {pname} (Герой) выиграл {amount:.2f}")
                else:
                    print(f"  - {pname} (Герой) выиграл банк")
            else:
                if amount is not None:
                    if sd_desc:
                        print(f"  - {pname} выиграл {amount:.2f} с комбинацией: {sd_desc}")
                    else:
                        print(f"  - {pname} выиграл {amount:.2f}")
                else:
                    print(f"  - {pname} выиграл банк")
    else:
        print("Информация о победителе отсутствует (возможен фолд до шоудауна).")

    print()
    if showdown:
        print("Шоудаун:")
        for s in showdown:
            pname = s.get("player")
            cards = format_cards(s.get("cards") or [])
            result = s.get("result")
            desc = s.get("description")
            hero_mark = " (Герой)" if pname == hero_name else ""
            line = f"  - {pname}{hero_mark}: {cards}"
            if desc:
                line += f" | комбинация: {desc}"
            if result:
                line += f" | результат: {result}"
            print(line)
    else:
        print("Шоудаун отсутствует (раздача завершилась без открытия карт).")

    print()


# ==========================
#  ИТОГ РАЗДАЧИ
# ==========================

def print_summary(hand: Dict[str, Any],
                  good_points: List[str],
                  improvement_points: List[str]) -> None:
    print("=== ИТОГОВЫЙ РАЗБОР РАЗДАЧИ ===")
    if good_points:
        print("Что было сделано хорошо:")
        for i, text in enumerate(good_points, 1):
            print(f"  {i}. {text}")
        print()
    else:
        print("Отдельно ярких 'good' моментов модель не выделяет — игра скорее аккуратная/нейтральная.")
        print()

    if improvement_points:
        print("Где можно сыграть лучше и как повышать вэлью:")
        for i, text in enumerate(improvement_points, 1):
            print(f"  {i}. {text}")
        print()
    else:
        print("Модель не видит явных зон для улучшения в этой раздаче — по текущей эвристике она сыграна довольно близко к плану.")
        print()

    # --- Краткий вердикт: дисперсия или закономерность
    hero_name = hand.get("hero_name")
    winners = hand.get("winners") or []
    showdown = hand.get("showdown") or []

    hero_won = any(w.get("player") == hero_name for w in winners)
    hero_in_showdown = any(s.get("player") == hero_name for s in showdown)

    # Собираем decision_quality по улицам отдельно
    dq_pre = (hand.get("hero_preflop_decision") or {}).get("decision_quality")
    dq_flop = (hand.get("hero_flop_decision") or {}).get("decision_quality")
    dq_turn = (hand.get("hero_turn_decision") or {}).get("decision_quality")
    dq_river = (hand.get("hero_river_decision") or {}).get("decision_quality")

    qualities: List[str] = []
    for q in (dq_pre, dq_flop, dq_turn, dq_river):
        if isinstance(q, str):
            qualities.append(q)

    has_bad = any(q in ("mistake", "bad", "risky") for q in qualities)
    has_only_good_ok = bool(qualities) and all(q in ("good", "ok", "neutral") for q in qualities)

    # Отдельно смотрим, где именно были "плохие" решения
    has_pre_bad = dq_pre in ("mistake", "bad", "risky")
    has_post_bad = any(q in ("mistake", "bad", "risky") for q in (dq_flop, dq_turn, dq_river))

    print("Краткий итог по сочетанию качества игры и результата:")
    if hero_won and has_only_good_ok:
        print("  - Банк выигран, и модель не видит серьёзных ошибок по улицам. Это пример раздачи, где сыгранный план соответствует твоей стратегии и приносит ожидаемый результат.")
    elif hero_won and has_bad:
        # Специальный кейс: ошибка ТОЛЬКО на префлопе, постфлоп сыгран хорошо
        if has_pre_bad and not has_post_bad:
            print("  - Банк выигран. Основная неточность была на префлопе (выбор стартовой руки или спота), а постфлоп разыгран сильным и логичным образом. В долгую такие префлоп-отклонения могут стоить EV, поэтому стоит ужесточить диапазон входа, сохранив такой же качественный постфлоп.")
        else:
            print("  - Банк выигран, но в линии присутствуют спорные/рискованные решения. В этой конкретной раздаче результат положительный, но в долгую такие споты могут стоить EV и требуют доработки.")
    elif (not hero_won) and has_only_good_ok and hero_in_showdown:
        print("  - Банк проигран, но по оценке модели раздача сыграна дисциплинированно и в рамках стратегии. Такой результат ближе к дисперсии/кулеру, чем к системной ошибке.")
    elif (not hero_won) and has_bad and hero_in_showdown:
        print("  - Банк проигран, и в линии есть объективно рискованные или ошибочные решения. Это пример раздачи, где поражение больше похоже на закономерность и даёт материал для работы над ликами.")
    elif (not hero_won) and not hero_in_showdown:
        print("  - Раздача завершилась без шоудауна. Оценка качества игры строится только по decision_quality; чтобы понять, была ли это недоотзащита или нормальный фолд, стоит смотреть похожие споты в массе.")
    else:
        print("  - Модель не может однозначно классифицировать эту раздачу по сочетанию качества решений и результата, но её детали уже разложены выше по улицам.")

    print()
    print("Этот разбор основан на эвристической модели: decision_quality, оценках equity и контексте (позиция, мультивей, инициативы).")
    print("Для максимально точного ответа в деньгах нужен солвер/симуляции, но как обучающий коуч по раздаче это уже рабочий уровень.")
    print()



# ==========================
#  MAIN
# ==========================

def main() -> None:
    base_path = Path(__file__).resolve().parent
    hands_path = base_path / "hands.json"

    hands = load_hands(hands_path)

    print("Доступные hand_id в текущем файле hands.json:")
    for hand in hands:
        hid = hand.get("hand_id")
        idx = hand.get("id")
        print(f"  #{idx}: {hid}")
    print()

    hand_id_input = input("Введи hand_id раздачи, которую нужно разобрать (или оставь пустым для выхода): ").strip()
    if not hand_id_input:
        print("Отмена.")
        return

    hand = find_hand_by_id(hands, hand_id_input)
    if hand is None:
        print(f"Раздача с hand_id={hand_id_input} не найдена.")
        return

    good_points: List[str] = []
    improvement_points: List[str] = []

    print()
    print(f"РАЗБОР РАЗДАЧИ: {hand_id_input}")
    print(f"Стол: {hand.get('table_name')} | Дата/время: {hand.get('date')} {hand.get('time')}")
    print(f"Ставки: {hand.get('small_blind')}/{hand.get('big_blind')} {hand.get('currency')}")
    print()

    print_preflop_section(hand, good_points, improvement_points)
    print_flop_section(hand, good_points, improvement_points)
    print_turn_section(hand, good_points, improvement_points)
    print_river_section(hand, good_points, improvement_points)
    print_outcome_section(hand)
    print_summary(hand, good_points, improvement_points)


if __name__ == "__main__":
    main()
