import json
from pathlib import Path
from typing import Any, Dict, List


# ==========================
#   ЗАГРУЗКА РАЗДАЧ
# ==========================

def load_hands(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Файл {path} не найден. Сначала запусти main.py, чтобы создать hands.json")

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError("Ожидался список раздач в JSON (list). Проверь формат hands.json")

    return data


def is_hero_aggressor_preflop(hand: Dict[str, Any]) -> bool:
    """
    Проверяем, был ли герой префлоп-агрессором.
    """
    hero_preflop_analysis = hand.get("hero_preflop_analysis")
    if not isinstance(hero_preflop_analysis, dict):
        return False

    atype = hero_preflop_analysis.get("action_type")
    if atype in ("open_raise", "iso_raise", "3bet", "4bet", "5bet_plus"):
        return True
    return False


# ==========================
#   ОТЧЁТ ПО ФЛОПУ
# ==========================

def analyze_flop(hands: List[Dict[str, Any]]) -> Dict[str, Any]:

    """
    Собираем статистику по флопу:
      - общее количество рук с действием героя на флопе
      - распределение по decision_quality
      - распределение по action_type
      - дисциплина c-bet, когда герой был префлоп-агрессором
    """
    total_with_flop = 0

    quality_counts: Dict[str, int] = {}
    action_type_counts: Dict[str, int] = {}

    cbet_spots = 0
    cbet_made = 0
    cbet_missed = 0

    example_hands_by_quality: Dict[str, List[str]] = {}

    for hand in hands:
        hand_id = hand.get("hand_id") or f"ID_{hand.get('id', '?')}"

        hero_flop_decision = hand.get("hero_flop_decision")
        if not isinstance(hero_flop_decision, dict):
            # герой не дошёл до флопа или не совершал действия
            continue

        total_with_flop += 1

        # --- decision_quality ---
        dq = hero_flop_decision.get("decision_quality") or "unknown"
        quality_counts[dq] = quality_counts.get(dq, 0) + 1

        if dq not in example_hands_by_quality:
            example_hands_by_quality[dq] = []
        if len(example_hands_by_quality[dq]) < 3:
            # сохраняем до 3 примеров для каждого типа качества
            example_hands_by_quality[dq].append(hand_id)

        # --- action_type ---
        atype = hero_flop_decision.get("action_type") or "unknown"
        action_type_counts[atype] = action_type_counts.get(atype, 0) + 1

        # --- c-bet дисциплина ---
        # герой префлоп-агрессор + дошли до флопа → это c-bet спот
        if is_hero_aggressor_preflop(hand):
            cbet_spots += 1

            # c-bet считаем, если герой ставит/рейзит на флопе
            is_cbet = atype in ("bet_vs_check", "raise_vs_bet", "bet", "raise", "cbet")
            is_check = atype == "check"

            if is_cbet:
                cbet_made += 1
            elif is_check:
                cbet_missed += 1
            # остальные (call/fold_vs_bet) пока не относим никуда

    return {
        "total_with_flop": total_with_flop,
        "quality_counts": quality_counts,
        "action_type_counts": action_type_counts,
        "cbet_spots": cbet_spots,
        "cbet_made": cbet_made,
        "cbet_missed": cbet_missed,
        "example_hands_by_quality": example_hands_by_quality,
    }


def print_flop_report(stats: Dict[str, Any]) -> None:
    total = stats["total_with_flop"]
    quality_counts = stats["quality_counts"]
    action_type_counts = stats["action_type_counts"]
    cbet_spots = stats["cbet_spots"]
    cbet_made = stats["cbet_made"]
    cbet_missed = stats["cbet_missed"]
    example_hands_by_quality = stats["example_hands_by_quality"]

    print()
    print("========== ПОСТФЛОП-ОТЧЁТ: ФЛОП ==========")
    print()
    print(f"Всего раздач с действием героя на флопе: {total}")
    print()

    # --- распределение по quality ---
    print("Качество решений на флопе (decision_quality):")
    if total == 0:
        print("  Нет ни одной раздачи с действием на флопе.")
    else:
        for key in sorted(quality_counts.keys()):
            cnt = quality_counts[key]
            pct = cnt / total * 100 if total > 0 else 0.0
            print(f"  - {key:7s}: {cnt:3d} раз ({pct:5.1f}%)")
    print()

    # --- распределение по типам действий ---
    print("Типы действий на флопе (action_type):")
    if total == 0:
        print("  Нет данных.")
    else:
        for key in sorted(action_type_counts.keys()):
            cnt = action_type_counts[key]
            pct = cnt / total * 100 if total > 0 else 0.0
            print(f"  - {key:15s}: {cnt:3d} раз ({pct:5.1f}%)")
    print()

    # --- c-bet дисциплина ---
    print("C-bet дисциплина (когда ты был префлоп-агрессором):")
    print(f"  Всего c-bet спотов: {cbet_spots}")
    if cbet_spots > 0:
        pct_cbet = cbet_made / cbet_spots * 100 if cbet_spots > 0 else 0.0
        pct_miss = cbet_missed / cbet_spots * 100 if cbet_spots > 0 else 0.0
        print(f"  Сделан c-bet:        {cbet_made:3d} раз ({pct_cbet:5.1f}%)")
        print(f"  Пропущен c-bet:      {cbet_missed:3d} раз ({pct_miss:5.1f}%)")
    print()

    # --- примеры рук по качеству ---
    print("Примеры рук по оценке качества (не более 3 на тип):")
    if not example_hands_by_quality:
        print("  Нет примеров.")
    else:
        for key in sorted(example_hands_by_quality.keys()):
            examples = example_hands_by_quality[key]
            print(f"  - {key}: {', '.join(examples)}")
    print()
    print("============= ОТЧЁТ ПО ФЛОПУ ГОТОВ =============")
    print()


# ==========================
#   ОТЧЁТ ПО ТЁРНУ
# ==========================

def analyze_turn(hands: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Собираем статистику по тёрну:
      - общее количество рук с действием героя на тёрне
      - распределение по decision_quality
      - распределение по action_type
      - распределение по impact_on_equity (positive/neutral/negative/unknown)
      - дисциплина агрессии на тёрне (агрессивные/пассивные/фолды)
    """
    total_with_turn = 0

    quality_counts: Dict[str, int] = {}
    action_type_counts: Dict[str, int] = {}
    impact_counts: Dict[str, int] = {}

    aggressive_count = 0
    passive_count = 0
    fold_count = 0

    example_hands_by_quality: Dict[str, List[str]] = {}

    for hand in hands:
        hand_id = hand.get("hand_id") or f"ID_{hand.get('id', '?')}"

        hero_turn_decision = hand.get("hero_turn_decision")
        if not isinstance(hero_turn_decision, dict):
            continue

        total_with_turn += 1

        # --- decision_quality ---
        dq = hero_turn_decision.get("decision_quality") or "unknown"
        quality_counts[dq] = quality_counts.get(dq, 0) + 1

        if dq not in example_hands_by_quality:
            example_hands_by_quality[dq] = []
        if len(example_hands_by_quality[dq]) < 3:
            example_hands_by_quality[dq].append(hand_id)

        # --- action_type ---
        atype = hero_turn_decision.get("action_type") or "unknown"
        action_type_counts[atype] = action_type_counts.get(atype, 0) + 1

        # --- impact_on_equity (по текстуре борда) ---
        hand_block = hero_turn_decision.get("hand") or {}
        board_texture = hand_block.get("board_texture") or {}
        impact = board_texture.get("impact_on_equity")
        if impact is None:
            impact = "unknown"
        impact_counts[impact] = impact_counts.get(impact, 0) + 1

        # --- дисциплина агрессии ---
        if atype in ("bet_vs_check", "bet", "raise_vs_bet", "raise"):
            aggressive_count += 1
        elif atype in ("check", "call_vs_bet", "call"):
            passive_count += 1
        elif atype in ("fold_vs_bet", "fold"):
            fold_count += 1

    return {
        "total_with_turn": total_with_turn,
        "quality_counts": quality_counts,
        "action_type_counts": action_type_counts,
        "impact_counts": impact_counts,
        "aggressive_count": aggressive_count,
        "passive_count": passive_count,
        "fold_count": fold_count,
        "example_hands_by_quality": example_hands_by_quality,
    }


def print_turn_report(stats: Dict[str, Any]) -> None:
    total = stats["total_with_turn"]
    quality_counts = stats["quality_counts"]
    action_type_counts = stats["action_type_counts"]
    impact_counts = stats["impact_counts"]
    aggressive_count = stats["aggressive_count"]
    passive_count = stats["passive_count"]
    fold_count = stats["fold_count"]
    example_hands_by_quality = stats["example_hands_by_quality"]

    print()
    print("========== ПОСТФЛОП-ОТЧЁТ: ТЁРН ==========")
    print()
    print(f"Всего раздач с действием героя на тёрне: {total}")
    print()

    # --- качество решений ---
    print("Качество решений на тёрне (decision_quality):")
    if total == 0:
        print("  Нет ни одной раздачи с действием на тёрне.")
    else:
        for key in sorted(quality_counts.keys()):
            cnt = quality_counts[key]
            pct = cnt / total * 100 if total > 0 else 0.0
            print(f"  - {key:7s}: {cnt:3d} раз ({pct:5.1f}%)")
    print()

    # --- типы действий ---
    print("Типы действий на тёрне (action_type):")
    if total == 0:
        print("  Нет данных.")
    else:
        for key in sorted(action_type_counts.keys()):
            cnt = action_type_counts[key]
            pct = cnt / total * 100 if total > 0 else 0.0
            print(f"  - {key:15s}: {cnt:3d} раз ({pct:5.1f}%)")
    print()

    # --- влияние карты тёрна на equity ---
    print("Как часто карта тёрна ухудшает/улучшает твою equity (impact_on_equity):")
    if total == 0:
        print("  Нет данных.")
    else:
        for key in sorted(impact_counts.keys()):
            cnt = impact_counts[key]
            pct = cnt / total * 100 if total > 0 else 0.0
            print(f"  - {key:8s}: {cnt:3d} раз ({pct:5.1f}%)")
    print()

    # --- дисциплина агрессии ---
    print("Дисциплина агрессии на тёрне (по типу линий):")
    print(f"  Агрессивные линии (bet/raise): {aggressive_count:3d}")
    print(f"  Пассивные линии  (check/call): {passive_count:3d}")
    print(f"  Фолды против ставки:           {fold_count:3d}")
    if total > 0:
        agg_pct = aggressive_count / total * 100
        pas_pct = passive_count / total * 100
        fold_pct = fold_count / total * 100
        print(f"  Доли: агрессия {agg_pct:5.1f}%, пассив {pas_pct:5.1f}%, фолд {fold_pct:5.1f}%")
    print()

    # --- примеры рук ---
    print("Примеры рук по оценке качества (не более 3 на тип):")
    if not example_hands_by_quality:
        print("  Нет примеров.")
    else:
        for key in sorted(example_hands_by_quality.keys()):
            examples = example_hands_by_quality[key]
            print(f"  - {key}: {', '.join(examples)}")
    print()
    print("============= ОТЧЁТ ПО ТЁРНУ ГОТОВ =============")
    print()


# ==========================
#   ОТЧЁТ ПО РИВЕРУ
# ==========================

def analyze_river(hands: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Собираем статистику по риверу:
      - общее количество рук с действием героя на ривере
      - распределение по decision_quality
      - распределение по action_type
      - дисциплина агрессии (агрессивные/пассивные/фолды)
      - распределение по оценочной equity на ривере (low/medium/high/unknown)
      - потенциальные missed value spots (когда equity высокая, а герой чекнул)
    """
    total_with_river = 0

    quality_counts: Dict[str, int] = {}
    action_type_counts: Dict[str, int] = {}

    aggressive_count = 0
    passive_count = 0
    fold_count = 0

    equity_bucket_counts: Dict[str, int] = {}

    example_hands_by_quality: Dict[str, List[str]] = {}

    missed_value_count = 0
    missed_value_hands: List[str] = []

    for hand in hands:
        hand_id = hand.get("hand_id") or f"ID_{hand.get('id', '?')}"

        hero_river_decision = hand.get("hero_river_decision")
        if not isinstance(hero_river_decision, dict):
            continue

        total_with_river += 1

        # --- decision_quality ---
        dq = hero_river_decision.get("decision_quality") or "unknown"
        quality_counts[dq] = quality_counts.get(dq, 0) + 1

        if dq not in example_hands_by_quality:
            example_hands_by_quality[dq] = []
        if len(example_hands_by_quality[dq]) < 3:
            example_hands_by_quality[dq].append(hand_id)

        # --- action_type ---
        atype = hero_river_decision.get("action_type") or "unknown"
        action_type_counts[atype] = action_type_counts.get(atype, 0) + 1

        # --- дисциплина агрессии ---
        if atype in ("bet_vs_check", "bet", "raise_vs_bet", "raise"):
            aggressive_count += 1
        elif atype in ("check", "call_vs_bet", "call"):
            passive_count += 1
        elif atype in ("fold_vs_bet", "fold"):
            fold_count += 1

        # --- equity buckets ---
        eq_bucket = "unknown"
        eq_info = hero_river_decision.get("equity_estimate") or {}
        eq_val = eq_info.get("estimated_equity")

        numeric_eq: float | None = None
        if isinstance(eq_val, (int, float)):
            numeric_eq = float(eq_val)
            if numeric_eq < 0.3:
                eq_bucket = "low(<0.30)"
            elif numeric_eq < 0.6:
                eq_bucket = "medium(0.30-0.60)"
            else:
                eq_bucket = "high(>0.60)"

        equity_bucket_counts[eq_bucket] = equity_bucket_counts.get(eq_bucket, 0) + 1

        # --- missed value spot: высокая equity, но чек ---
        # v1-логика: если estimated_equity >= 0.70 и герой играет check → флаг как потенциально упущенное вэлью.
        if numeric_eq is not None and numeric_eq >= 0.70 and atype == "check":
            missed_value_count += 1
            if len(missed_value_hands) < 20:
                missed_value_hands.append(hand_id)

    return {
        "total_with_river": total_with_river,
        "quality_counts": quality_counts,
        "action_type_counts": action_type_counts,
        "aggressive_count": aggressive_count,
        "passive_count": passive_count,
        "fold_count": fold_count,
        "equity_bucket_counts": equity_bucket_counts,
        "example_hands_by_quality": example_hands_by_quality,
        "missed_value_count": missed_value_count,
        "missed_value_hands": missed_value_hands,
    }

def print_river_report(stats: Dict[str, Any]) -> None:
    total = stats["total_with_river"]
    quality_counts = stats["quality_counts"]
    action_type_counts = stats["action_type_counts"]
    aggressive_count = stats["aggressive_count"]
    passive_count = stats["passive_count"]
    fold_count = stats["fold_count"]
    equity_bucket_counts = stats["equity_bucket_counts"]
    example_hands_by_quality = stats["example_hands_by_quality"]
    missed_value_count = stats["missed_value_count"]
    missed_value_hands = stats["missed_value_hands"]

    print()
    print("========== ПОСТФЛОП-ОТЧЁТ: РИВЕР ==========")
    print()
    print(f"Всего раздач с действием героя на ривере: {total}")
    print()

    # --- качество решений ---
    print("Качество решений на ривере (decision_quality):")
    if total == 0:
        print("  Нет ни одной раздачи с действием на ривере.")
    else:
        for key in sorted(quality_counts.keys()):
            cnt = quality_counts[key]
            pct = cnt / total * 100 if total > 0 else 0.0
            print(f"  - {key:7s}: {cnt:3d} раз ({pct:5.1f}%)")
    print()

    # --- типы действий ---
    print("Типы действий на ривере (action_type):")
    if total == 0:
        print("  Нет данных.")
    else:
        for key in sorted(action_type_counts.keys()):
            cnt = action_type_counts[key]
            pct = cnt / total * 100 if total > 0 else 0.0
            print(f"  - {key:15s}: {cnt:3d} раз ({pct:5.1f}%)")
    print()

    # --- дисциплина агрессии ---
    print("Дисциплина агрессии на ривере (по типу линий):")
    print(f"  Агрессивные линии (bet/raise): {aggressive_count:3d}")
    print(f"  Пассивные линии  (check/call): {passive_count:3d}")
    print(f"  Фолды против ставки:           {fold_count:3d}")
    if total > 0:
        agg_pct = aggressive_count / total * 100
        pas_pct = passive_count / total * 100
        fold_pct = fold_count / total * 100
        print(f"  Доли: агрессия {agg_pct:5.1f}%, пассив {pas_pct:5.1f}%, фолд {fold_pct:5.1f}%")
    print()

    # --- распределение по equity ---
    print("Распределение оценочной equity на ривере (по bucket'ам):")
    if total == 0:
        print("  Нет данных.")
    else:
        for key in sorted(equity_bucket_counts.keys()):
            cnt = equity_bucket_counts[key]
            pct = cnt / total * 100 if total > 0 else 0.0
            print(f"  - {key:18s}: {cnt:3d} раз ({pct:5.1f}%)")
    print()

    # --- missed value spots ---
    print("Потенциально упущенное вэлью (missed value spots):")
    print(f"  Количество рук: {missed_value_count}")
    if missed_value_count > 0:
        print("  Примеры hand_id (не более 20):")
        for hid in missed_value_hands:
            print(f"    - {hid}")
    print()

    # --- примеры рук по качеству ---
    print("Примеры рук по оценке качества (не более 3 на тип):")
    if not example_hands_by_quality:
        print("  Нет примеров.")
    else:
        for key in sorted(example_hands_by_quality.keys()):
            examples = example_hands_by_quality[key]
            print(f"  - {key}: {', '.join(examples)}")
    print()
    print("============= ОТЧЁТ ПО РИВЕРУ ГОТОВ =============")
    print()

# ==========================
#   MAIN
# ==========================

def main() -> None:
    base_path = Path(__file__).resolve().parent
    hands_path = base_path / "hands.json"

    hands = load_hands(hands_path)

    # Флоп
    flop_stats = analyze_flop(hands)
    print_flop_report(flop_stats)

    # Тёрн
    turn_stats = analyze_turn(hands)
    print_turn_report(turn_stats)

    # Ривер
    river_stats = analyze_river(hands)
    print_river_report(river_stats)


if __name__ == "__main__":
    main()
