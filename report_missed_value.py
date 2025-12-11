import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def load_hands(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Файл {path} не найден. Сначала запусти main.py, чтобы создать hands.json")

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError("Ожидался список раздач (list) в hands.json")

    return data


def safe_float(v: Any) -> Optional[float]:
    if isinstance(v, (int, float)):
        return float(v)
    return None


def format_cards(cards: Optional[List[str]]) -> str:
    if not cards:
        return "-"
    return " ".join(cards)


def format_board(board: Optional[List[str]]) -> str:
    if not board:
        return "-"
    return " ".join(board)


def find_missed_value_spots(hands: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Возвращает два списка:
      1) missed_value_checks  — сильная рука, IP, ривер, но герой чекнул
      2) missed_value_passive_calls — сильная рука, IP, ривер, герой только колл против небольшой ставки
    """
    missed_value_checks: List[Dict[str, Any]] = []
    missed_value_passive_calls: List[Dict[str, Any]] = []

    for hand in hands:
        hero_name = hand.get("hero_name")
        hero_cards = hand.get("hero_cards") or []
        board = hand.get("board") or []
        river_dec = hand.get("hero_river_decision") or {}

        if not river_dec:
            continue

        # equity на ривере
        eq_info = river_dec.get("equity_estimate") or {}
        est_eq = safe_float(eq_info.get("estimated_equity"))
        if est_eq is None:
            continue

        # контекст
        context = river_dec.get("context") or {}
        hero_ip = context.get("hero_ip")
        players_to_river = context.get("players_to_river")
        multiway = context.get("multiway")
        hero_pos = context.get("hero_position")
        preflop_role = context.get("preflop_role")

        # сайзинг
        sizing = river_dec.get("sizing") or {}
        amount = safe_float(sizing.get("amount"))
        pot_before = safe_float(sizing.get("pot_before"))
        pct_pot = safe_float(sizing.get("pct_pot"))

        action_type = river_dec.get("action_type")
        action_kind = river_dec.get("action_kind")

        # Спот 1: IP, сильная equity, но чек
        if (
            hero_ip is True
            and est_eq >= 0.65
            and action_type == "check"
        ):
            missed_value_checks.append(
                {
                    "hand_id": hand.get("hand_id"),
                    "id": hand.get("id"),
                    "hero_name": hero_name,
                    "hero_cards": hero_cards,
                    "board": board,
                    "equity": est_eq,
                    "players_to_river": players_to_river,
                    "multiway": multiway,
                    "hero_ip": hero_ip,
                    "hero_pos": hero_pos,
                    "preflop_role": preflop_role,
                    "action_type": action_type,
                    "action_kind": action_kind,
                    "amount": amount,
                    "pot_before": pot_before,
                    "pct_pot": pct_pot,
                }
            )

        # Спот 2: IP, сильная equity, небольшой бет оппа, герой только колл
        # Здесь мы видим только колл героя (amount) и pot_before, считается, что бет оппа примерно равен этому amount.
        if (
            hero_ip is True
            and est_eq >= 0.70
            and action_type == "call_vs_bet"
        ):
            if pot_before is not None and amount is not None and pot_before > 0:
                frac = amount / pot_before
            else:
                frac = None

            # небольшой бет оппа — условно <= 1/3 пота
            if frac is not None and frac <= 0.33:
                missed_value_passive_calls.append(
                    {
                        "hand_id": hand.get("hand_id"),
                        "id": hand.get("id"),
                        "hero_name": hero_name,
                        "hero_cards": hero_cards,
                        "board": board,
                        "equity": est_eq,
                        "players_to_river": players_to_river,
                        "multiway": multiway,
                        "hero_ip": hero_ip,
                        "hero_pos": hero_pos,
                        "preflop_role": preflop_role,
                        "action_type": action_type,
                        "action_kind": action_kind,
                        "amount": amount,
                        "pot_before": pot_before,
                        "pct_pot": pct_pot,
                        "bet_frac": frac,
                    }
                )

    return missed_value_checks, missed_value_passive_calls


def print_missed_value_report(
    missed_checks: List[Dict[str, Any]],
    missed_calls: List[Dict[str, Any]],
) -> None:
    total_spots = len(missed_checks) + len(missed_calls)

    print("========== ОТЧЁТ ПО MISSED VALUE SPOTS (РИВЕР) ==========")
    print(f"Всего потенциальных missed value спотов на ривере: {total_spots}")
    print(f"  - Чек с сильной рукой (в позиции): {len(missed_checks)}")
    print(f"  - Пассивный колл против небольшой ставки (в позиции): {len(missed_calls)}")
    print()

    if total_spots == 0:
        print("Модель не нашла явных missed value спотов на ривере по текущим эвристикам.")
        print("Это не значит, что их нет совсем, но на базовом уровне твои решения по риверу выглядят дисциплинированно.")
        print()
        return

    # сортируем по размеру пота, чтобы сначала показать наиболее дорогие споты
    missed_checks_sorted = sorted(
        missed_checks,
        key=lambda x: (x.get("pot_before") or 0.0),
        reverse=True,
    )
    missed_calls_sorted = sorted(
        missed_calls,
        key=lambda x: (x.get("pot_before") or 0.0),
        reverse=True,
    )

    # Лимит на количество выводимых примеров
    max_examples_per_type = 10

    print("------ ЧЕК С СИЛЬНОЙ РУКОЙ НА РИВЕРЕ (IP) ------")
    if not missed_checks_sorted:
        print("  Не найдено спотов, где ты в позиции чекнул на ривере с высокой оценочной equity.")
    else:
        for spot in missed_checks_sorted[:max_examples_per_type]:
            hand_id = spot.get("hand_id")
            hid = spot.get("id")
            board = format_board(spot.get("board"))
            cards = format_cards(spot.get("hero_cards"))
            eq = spot.get("equity") or 0.0
            pot_before = spot.get("pot_before") or 0.0
            players = spot.get("players_to_river")
            multiway = spot.get("multiway")
            hero_pos = spot.get("hero_pos")
            preflop_role = spot.get("preflop_role")

            print(f"  - Hand #{hid} ({hand_id}):")
            print(f"      Борд: {board}")
            print(f"      Карты героя: {cards}")
            print(f"      Оценочная equity на ривере: {eq:.2f}")
            print(f"      Пот перед решением на ривере: {pot_before:.2f}")
            print(f"      Игроков на ривере: {players}, мультивей: {multiway}")
            print(f"      Позиция героя: {hero_pos}, роль префлоп: {preflop_role}")
            print("      Действие: check в позиции с сильной оценкой equity.")
            print("      Комментарий: Это кандидат на missed value — часто здесь можно поставить тонкий вэлью-бет и добрать с худших рук.")
            print()

    print("------ ПАССИВНЫЙ КОЛЛ ПРОТИВ НЕБОЛЬШОЙ СТАВКИ (IP) ------")
    if not missed_calls_sorted:
        print("  Не найдено спотов, где ты в позиции только заколлировал небольшую ставку на ривере с сильной рукой.")
    else:
        for spot in missed_calls_sorted[:max_examples_per_type]:
            hand_id = spot.get("hand_id")
            hid = spot.get("id")
            board = format_board(spot.get("board"))
            cards = format_cards(spot.get("hero_cards"))
            eq = spot.get("equity") or 0.0
            pot_before = spot.get("pot_before") or 0.0
            amount = spot.get("amount") or 0.0
            bet_frac = spot.get("bet_frac") or 0.0
            players = spot.get("players_to_river")
            multiway = spot.get("multiway")
            hero_pos = spot.get("hero_pos")
            preflop_role = spot.get("preflop_role")

            print(f"  - Hand #{hid} ({hand_id}):")
            print(f"      Борд: {board}")
            print(f"      Карты героя: {cards}")
            print(f"      Оценочная equity на ривере: {eq:.2f}")
            print(f"      Пот перед ставкой оппонента: {pot_before:.2f}")
            print(f"      Размер ставки оппонента (примерно): {amount:.2f} (~{bet_frac*100:.1f}% пота)")
            print(f"      Игроков на ривере: {players}, мультивей: {multiway}")
            print(f"      Позиция героя: {hero_pos}, роль префлоп: {preflop_role}")
            print("      Действие: только колл против небольшой ставки на ривере с сильной оценкой equity.")
            print("      Комментарий: Это кандидат на missed value — часто здесь можно играть через рейз для добора с более слабых рук.")
            print()

    print("============= ОТЧЁТ ПО MISSED VALUE ГОТОВ =============")
    print()


def main() -> None:
    base_path = Path(__file__).resolve().parent
    hands_path = base_path / "hands.json"

    hands = load_hands(hands_path)
    missed_checks, missed_calls = find_missed_value_spots(hands)
    print_missed_value_report(missed_checks, missed_calls)


if __name__ == "__main__":
    main()
