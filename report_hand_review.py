import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


def _money(x: Any) -> str:
    if x is None:
        return "-"
    try:
        return f"{float(x):.2f}"
    except Exception:
        return str(x)


def _pct(x: Any) -> str:
    if x is None:
        return "-"
    try:
        return f"{float(x) * 100:.1f}%"
    except Exception:
        return str(x)


def _equity(x: Any) -> str:
    if x is None:
        return "-"
    try:
        return f"{float(x):.2f}"
    except Exception:
        return str(x)


def _ev(x: Any) -> str:
    if x is None:
        return "-"
    try:
        return f"{float(x):.4f}"
    except Exception:
        return str(x)


def _find_hand(hands: List[Dict[str, Any]], hand_id: str) -> Optional[Dict[str, Any]]:
    for h in hands:
        if h.get("hand_id") == hand_id:
            return h
    return None


def _street_ev(decision: Optional[Dict[str, Any]]) -> float:
    if not decision:
        return 0.0
    ev = (decision.get("ev_estimate") or {}).get("ev_action")
    try:
        return float(ev)
    except Exception:
        return 0.0


def _print_header(hand: Dict[str, Any]) -> None:
    print(f"РАЗБОР РАЗДАЧИ: {hand.get('hand_id')}")
    print(f"Стол: {hand.get('table_name')} | Дата/время: {hand.get('date')} {hand.get('time')}")
    print(f"Ставки: {hand.get('small_blind')}/{hand.get('big_blind')} {hand.get('currency')}")
    print("")


def _print_preflop(hand: Dict[str, Any]) -> float:
    hero = hand.get("hero_name")
    pos = hand.get("hero_position")
    cards = hand.get("hero_cards") or []
    eq = hand.get("hero_preflop_equity") or {}
    dec = hand.get("hero_preflop_decision") or {}

    print("=== ПРЕФЛОП ===")
    print(f"Герой: {hero} | Позиция: {pos}")
    print(f"Карты героя: {' '.join(cards) if cards else '-'}")

    print(f"Префлоп-оценка руки по модели: {eq.get('hand_key')} (категория: {eq.get('category')})")
    print(f"Оценочная equity vs unknown: {_equity(eq.get('estimated_equity_vs_unknown'))}")
    notes = eq.get("notes")
    if notes:
        print(f"Комментарий (MOS/диапазоны): {notes}")

    # EV префлопа
    ev_pf = _street_ev(dec)
    dq = dec.get("decision_quality", "unknown")
    print("")
    print("Решение на префлопе:")
    print(f"  action_type={dec.get('action_type')} | action_kind={dec.get('action_kind')} | decision_quality={dq}")
    math = dec.get("math") or {}
    if math:
        print(f"  pot_before={_money(math.get('pot_before'))} | investment={_money(math.get('investment'))} | req_equity={_equity(math.get('required_equity'))}")
        if math.get("estimated_equity") is not None:
            print(f"  est_equity={_equity(math.get('estimated_equity'))}")
        if math.get("ev_simple") is not None:
            print(f"  ev_simple={_ev(math.get('ev_simple'))}")
    if dec.get("comment"):
        comment = dec.get('comment')
        if comment:
            safe_comment = str(comment).encode('ascii', errors='ignore').decode('ascii')
            print(f"  comment: {safe_comment}")
    if (dec.get("ev_estimate") or {}).get("explanation"):
        print(f"  EV(action)={_ev((dec.get('ev_estimate') or {}).get('ev_action'))}")
        print(f"  EV_expl: {(dec.get('ev_estimate') or {}).get('explanation')}")

    print("")
    return ev_pf


def _print_postflop_street(
    title: str,
    board_cards: List[str],
    decision: Optional[Dict[str, Any]],
    pot_key: str,
) -> float:
    print(f"=== {title} ===")
    print(f"Борд: {' '.join(board_cards) if board_cards else '-'}")

    if not decision:
        print("Герой не сыграл эту улицу (нет действий).")
        print("")
        return 0.0

    action_type = decision.get("action_type")
    action_kind = decision.get("action_kind")
    dq = decision.get("decision_quality", "unknown")

    ctx = decision.get("context") or {}
    sizing = decision.get("sizing") or {}
    eq_info = decision.get("equity_estimate") or {}
    ev_info = decision.get("ev_estimate") or {}

    print(f"Действие героя: action_type={action_type} | action_kind={action_kind} | decision_quality={dq}")

    players_key = None
    if title == "ФЛОП":
        players_key = "players_to_flop"
    elif title == "ТЁРН":
        players_key = "players_to_turn"
    elif title == "РИВЕР":
        players_key = "players_to_river"

    if players_key and players_key in ctx:
        print(
            f"Контекст: players={ctx.get(players_key)} | multiway={ctx.get('multiway')} | hero_ip={ctx.get('hero_ip')} | pos={ctx.get('hero_position')} | preflop_role={ctx.get('preflop_role')}"
        )

    pot_before = sizing.get("pot_before")
    amount = sizing.get("amount")
    pct_pot = sizing.get("pct_pot")

    # Пот из hand-объекта, если есть
    pot_street = None
    # ключи в hands.json: pot_flop/pot_turn/pot_river уже есть
    # pot_key передаём явно
    # это удобнее показывать, чем только pot_before в sizing
    # (pot_before в sizing может быть None для check)
    pot_street = ctx.get(pot_key)

    if pot_street is not None:
        print(f"Пот на улице (по hand): {_money(pot_street)}")

    if pot_before is not None or amount is not None:
        print(f"Sizing: amount={_money(amount)} | pot_before={_money(pot_before)} | pct_pot={_pct(pct_pot)}")

    if eq_info.get("estimated_equity") is not None:
        print(f"Equity_est: {_equity(eq_info.get('estimated_equity'))} | model={eq_info.get('model')}")
        if eq_info.get("explanation"):
            explanation = eq_info.get('explanation')
            safe_explanation = str(explanation).encode('ascii', errors='ignore').decode('ascii')
            print(f"Equity_expl: {safe_explanation}")

    ev_action = ev_info.get("ev_action")
    if ev_action is not None:
        print(f"EV(action): {_ev(ev_action)} | model={ev_info.get('model')}")
        if ev_info.get("explanation"):
            explanation = ev_info.get('explanation')
            safe_explanation = str(explanation).encode('ascii', errors='ignore').decode('ascii')
            print(f"EV_expl: {safe_explanation}")

    if decision.get("comment"):
        comment = decision.get('comment')
        if comment:
            safe_comment = str(comment).encode('ascii', errors='ignore').decode('ascii')
            print(f"Comment: {safe_comment}")

    print("")
    return _street_ev(decision)


def _print_outcome(hand: Dict[str, Any]) -> None:
    print("=== ИСХОД РАЗДАЧИ ===")
    total_pot = hand.get("total_pot")
    rake = hand.get("rake")
    print(f"Общий банк (total_pot): {_money(total_pot)}")
    print(f"Рейк: {_money(rake)}")
    print("")

    winners = hand.get("winners") or []
    if winners:
        print("Победитель(и):")
        for w in winners:
            print(f"  - {w.get('player')} выиграл {_money(w.get('amount'))}")
    else:
        print("Победители не указаны.")
    print("")

    showdown = hand.get("showdown") or []
    if showdown:
        print("Шоудаун:")
        for s in showdown:
            cards = s.get("cards") or []
            desc = s.get("description")
            res = s.get("result")
            won_amt = s.get("won_amount")
            print(f"  - {s.get('player')}: {' '.join(cards) if cards else '-'} | {desc} | result={res} | won_amount={_money(won_amt)}")
    else:
        print("Шоудаун отсутствует (раздача завершилась без открытия карт).")

    print("")


def _print_total_ev(ev_pf: float, ev_flop: float, ev_turn: float, ev_river: float) -> None:
    total = ev_pf + ev_flop + ev_turn + ev_river
    print("=== EV-СВОДКА ПО РАЗДАЧЕ ===")
    print(f"EV(preflop)={ev_pf:.4f} | EV(flop)={ev_flop:.4f} | EV(turn)={ev_turn:.4f} | EV(river)={ev_river:.4f}")
    print(f"EV(total)={total:.4f}")
    print("")


def _print_coach_summary(hand: Dict[str, Any], ev_pf: float, ev_flop: float, ev_turn: float, ev_river: float) -> None:
    print("=== ИТОГОВЫЙ КОУЧ-ВЫВОД (v1) ===")

    issues = []
    if ev_pf < -0.0001:
        issues.append("Префлоп: возможная потеря EV (по модели).")
    if ev_flop < -0.0001:
        issues.append("Флоп: возможная потеря EV (по модели).")
    if ev_turn < -0.0001:
        issues.append("Тёрн: возможная потеря EV (по модели).")
    if ev_river < -0.0001:
        issues.append("Ривер: missed value / потеря EV (по модели).")

    if not issues:
        print("Явных потерь EV по v1-эвристике не найдено (это не гарантирует оптимальную игру, но базово линия ок).")
    else:
        print("Где модель видит потери EV:")
        for i, s in enumerate(issues, 1):
            print(f"  {i}. {s}")

    # специальный вывод под missed value
    rd = hand.get("hero_river_decision") or {}
    ev_info = (rd.get("ev_estimate") or {})
    if ev_info.get("model") == "river_missed_value_v1":
        print("")
        print("Missed value spot (ривер):")
        explanation = ev_info.get('explanation')
        safe_explanation = str(explanation).encode('ascii', errors='ignore').decode('ascii')
        print(f"  - {safe_explanation}")

    print("")


def main() -> None:
    if len(sys.argv) < 2:
        print("Использование:")
        print("  python report_hand_review.py <HAND_ID> [hands.json]")
        sys.exit(1)

    hand_id = sys.argv[1]
    hands_path = Path(sys.argv[2]) if len(sys.argv) >= 3 else Path("hands.json")

    if not hands_path.exists():
        print(f"Файл не найден: {hands_path}")
        sys.exit(1)

    hands = json.loads(hands_path.read_text(encoding="utf-8"))
    if not isinstance(hands, list):
        print("hands.json должен быть списком раздач (list).")
        sys.exit(1)

    hand = _find_hand(hands, hand_id)
    if not hand:
        print(f"Раздача не найдена: {hand_id}")
        sys.exit(1)

    _print_header(hand)

    ev_pf = _print_preflop(hand)

    board = hand.get("board") or []
    flop_board = board[:3] if len(board) >= 3 else board
    turn_board = board[:4] if len(board) >= 4 else board
    river_board = board[:5] if len(board) >= 5 else board

    ev_flop = _print_postflop_street(
        "ФЛОП",
        flop_board,
        hand.get("hero_flop_decision"),
        pot_key="pot_flop",
    )
    ev_turn = _print_postflop_street(
        "ТЁРН",
        turn_board,
        hand.get("hero_turn_decision"),
        pot_key="pot_turn",
    )
    ev_river = _print_postflop_street(
        "РИВЕР",
        river_board,
        hand.get("hero_river_decision"),
        pot_key="pot_river",
    )

    _print_outcome(hand)
    _print_total_ev(ev_pf, ev_flop, ev_turn, ev_river)
    _print_coach_summary(hand, ev_pf, ev_flop, ev_turn, ev_river)


if __name__ == "__main__":
    main()
