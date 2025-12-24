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


def _load_hands(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        print(f"hands.json not found at: {path}", file=sys.stderr)
        sys.exit(1)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"Failed to parse {path}: {e}", file=sys.stderr)
        sys.exit(1)


def _find_hand(hands: List[Dict[str, Any]], hand_id: str) -> Optional[Dict[str, Any]]:
    for h in hands:
        if h.get("hand_id") == hand_id:
            return h
    return None


def _get_ev_value(ev_info: Any) -> float:
    """
    Достаёт численное EV выбранного действия из ev_estimate.

    Совместимость:
    - новый контракт: ev_action (float)
    - legacy: ev (float)
    - legacy-лейбл: ev_action_str (строка) — игнорируем для числа
    """
    if not isinstance(ev_info, dict):
        return 0.0

    v = ev_info.get("ev_action")

    # если вдруг там строка, попробуем привести (иногда могли сохранить число строкой)
    if isinstance(v, str):
        try:
            return float(v)
        except Exception:
            v = None

    if v is not None:
        try:
            return float(v)
        except Exception:
            pass

    # fallback старого формата
    v2 = ev_info.get("ev")
    if v2 is not None:
        try:
            return float(v2)
        except Exception:
            return 0.0

    return 0.0


def _street_ev(decision: Optional[Dict[str, Any]]) -> float:
    if not decision:
        return 0.0
    ev_info = decision.get("ev_estimate") or {}
    return _get_ev_value(ev_info)


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
    print(f"  pot_before={_money(dec.get('pot_before'))} | investment={_money(dec.get('investment'))} | req_equity={_equity((dec.get('math') or {}).get('required_equity'))}")
    print(f"  est_equity={_equity(dec.get('estimated_equity'))}")
    if (dec.get("ev_estimate") or {}).get("explanation"):
        print(f"  EV(action)={_ev(_get_ev_value(dec.get('ev_estimate') or {}))}")
        print(f"  EV_expl: {(dec.get('ev_estimate') or {}).get('explanation')}")
    if dec.get("comment"):
        print(f"  Комментарий: {dec.get('comment')}")

    print("")
    return ev_pf


def _print_street_generic(street_name: str, decision: Dict[str, Any]) -> float:
    print(f"=== {street_name.upper()} ===")

    if not decision:
        print("Нет решения героя на этой улице.")
        print("")
        return 0.0

    dq = decision.get("decision_quality", "unknown")
    print(f"Решение: action_kind={decision.get('action_kind')} | action_type={decision.get('action_type')} | decision_quality={dq}")
    print(f"pot_before={_money(decision.get('pot_before'))} | investment={_money(decision.get('investment'))} | est_equity={_equity(decision.get('estimated_equity'))}")

    ev_info = decision.get("ev_estimate") or {}
    ev_action = _get_ev_value(ev_info)
    if ev_action is not None:
        print(f"EV(action): {_ev(ev_action)} | model={ev_info.get('model')}")
        if ev_info.get("assumptions"):
            print(f"Assumptions: {ev_info.get('assumptions')}")
        if ev_info.get("explanation"):
            print(f"Explanation: {ev_info.get('explanation')}")

    if decision.get("comment"):
        print(f"Комментарий: {decision.get('comment')}")

    print("")
    return float(ev_action) if ev_action is not None else 0.0


def _print_outcome(hand: Dict[str, Any]) -> None:
    outcome = hand.get("outcome") or {}
    print("=== ИТОГ ===")
    if not outcome:
        print("Нет данных по итогам раздачи.")
        print("")
        return

    print(f"Результат: {outcome.get('result')}")
    print(f"Выигрыш героя: {_money(outcome.get('hero_net'))} {hand.get('currency')}")
    if outcome.get("showdown"):
        print(f"Шоудаун: {outcome.get('showdown')}")
    print("")


def _print_total_ev(ev_pf: float, ev_flop: float, ev_turn: float, ev_river: float) -> None:
    total = (ev_pf or 0.0) + (ev_flop or 0.0) + (ev_turn or 0.0) + (ev_river or 0.0)
    print("=== EV SUMMARY (decomposition) ===")
    print(f"EV(preflop): {_ev(ev_pf)}")
    print(f"EV(flop):    {_ev(ev_flop)}")
    print(f"EV(turn):    {_ev(ev_turn)}")
    print(f"EV(river):   {_ev(ev_river)}")
    print("-" * 30)
    print(f"EV(total):   {_ev(total)}")
    print("")


def _print_coach_summary(hand: Dict[str, Any], ev_pf: float, ev_flop: float, ev_turn: float, ev_river: float) -> None:
    """
    Оставляем как было: если у тебя в JSON уже есть coach_summary — печатаем его.
    Если нет — делаем простой вывод по EV.
    """
    coach = hand.get("coach_summary")
    print("=== COACH SUMMARY ===")
    if coach:
        if isinstance(coach, str):
            print(coach)
        elif isinstance(coach, dict):
            for k, v in coach.items():
                print(f"{k}: {v}")
        else:
            print(str(coach))
        print("")
        return

    # fallback (без потери функционала, просто дефолт если поля нет)
    total = (ev_pf or 0.0) + (ev_flop or 0.0) + (ev_turn or 0.0) + (ev_river or 0.0)
    if total >= 0.05:
        print("Суммарно линия выглядит плюсовой по EV. Продолжай сохранять дисциплину и ищи spots для thin value.")
    elif -0.05 < total < 0.05:
        print("Суммарно EV около нуля: тонкий спот. Проверь сайзинги и частоты агрессии/пассивности.")
    else:
        print("Суммарно EV отрицательный: вероятно, где-то переоценка equity или лишняя агрессия/пассивность.")
    print("")


def main() -> None:
    root = Path(__file__).resolve().parent
    hands_path = root / "hands.json"
    hands = _load_hands(hands_path)

    if len(sys.argv) < 2:
        print("Usage: python report_hand_review.py <hand_id>", file=sys.stderr)
        sys.exit(1)

    hand_id = sys.argv[1]
    hand = _find_hand(hands, hand_id)
    if not hand:
        print(f"Hand not found: {hand_id}", file=sys.stderr)
        sys.exit(1)

    _print_header(hand)

    ev_pf = _print_preflop(hand)

    # flop/turn/river — оставляем структуру как в твоём JSON
    flop_dec = hand.get("hero_flop_decision") or {}
    turn_dec = hand.get("hero_turn_decision") or {}
    river_dec = hand.get("hero_river_decision") or {}

    ev_flop = _print_street_generic("Флоп", flop_dec)
    ev_turn = _print_street_generic("Тёрн", turn_dec)
    ev_river = _print_street_generic("Ривер", river_dec)

    _print_outcome(hand)
    _print_total_ev(ev_pf, ev_flop, ev_turn, ev_river)
    _print_coach_summary(hand, ev_pf, ev_flop, ev_turn, ev_river)

    # Сохраняем результат в JSON файл (как было)
    output_filename = f"hand_review_{hand_id}.json"
    with open(output_filename, "w", encoding="utf-8") as f:
        json.dump(hand, f, ensure_ascii=False, indent=2)
    print(f"\nРезультат сохранен в файл: {output_filename}")


if __name__ == "__main__":
    main()
