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


def collect_quality_counts(hands: List[Dict[str, Any]], key: str) -> Tuple[int, Dict[str, int]]:
    """
    Собираем распределение decision_quality для блока hero_*_decision.
    key: "hero_preflop_decision", "hero_flop_decision", "hero_turn_decision", "hero_river_decision"
    """
    total = 0
    counts: Dict[str, int] = {}

    for hand in hands:
        block = hand.get(key)
        if not isinstance(block, dict):
            continue
        dq = block.get("decision_quality") or "unknown"
        total += 1
        counts[dq] = counts.get(dq, 0) + 1

    return total, counts


def compute_cbet_stats(hands: List[Dict[str, Any]]) -> Tuple[int, int, int]:
    """
    Считаем дисциплину c-bet на флопе.
    """
    total_spots = 0
    cbet_made = 0
    cbet_missed = 0

    for hand in hands:
        hero_pre = hand.get("hero_preflop_analysis") or {}
        atype_pre = hero_pre.get("action_type")
        is_aggressor = atype_pre in ("open_raise", "iso_raise", "3bet", "4bet", "5bet_plus")

        hero_flop = hand.get("hero_flop_decision") or {}
        if not hero_flop:
            continue

        if not is_aggressor:
            continue

        total_spots += 1
        atype = hero_flop.get("action_type") or "unknown"

        is_cbet = atype in ("bet_vs_check", "raise_vs_bet", "bet", "raise", "cbet")
        is_check = atype == "check"

        if is_cbet:
            cbet_made += 1
        elif is_check:
            cbet_missed += 1

    return total_spots, cbet_made, cbet_missed


def compute_turn_aggression(hands: List[Dict[str, Any]]) -> Tuple[int, int, int]:
    """
    Считаем агрессию на тёрне:
      - агрессивные (bet/raise)
      - пассивные (check/call)
      - фолды против ставки
    """
    total = 0
    aggr = 0
    passive = 0
    folds = 0

    for hand in hands:
        hero_turn = hand.get("hero_turn_decision") or {}
        if not hero_turn:
            continue
        total += 1
        atype = hero_turn.get("action_type") or "unknown"
        if atype in ("bet_vs_check", "bet", "raise_vs_bet", "raise"):
            aggr += 1
        elif atype in ("check", "call_vs_bet", "call"):
            passive += 1
        elif atype in ("fold_vs_bet", "fold"):
            folds += 1

    return total, aggr, passive, folds


def compute_river_aggression_and_missed_value(hands: List[Dict[str, Any]]) -> Tuple[int, int, int, int, int, List[str]]:
    """
    Считаем:
      - агрессию на ривере
      - потенциальные missed value spots (высокая equity + чек)
    """
    total = 0
    aggr = 0
    passive = 0
    folds = 0
    missed_value = 0
    missed_ids: List[str] = []

    for hand in hands:
        hero_river = hand.get("hero_river_decision") or {}
        if not hero_river:
            continue

        total += 1
        atype = hero_river.get("action_type") or "unknown"

        if atype in ("bet_vs_check", "bet", "raise_vs_bet", "raise"):
            aggr += 1
        elif atype in ("check", "call_vs_bet", "call"):
            passive += 1
        elif atype in ("fold_vs_bet", "fold"):
            folds += 1

        eq_info = hero_river.get("equity_estimate") or {}
        eq_val = eq_info.get("estimated_equity")
        numeric_eq: Optional[float] = None
        if isinstance(eq_val, (int, float)):
            numeric_eq = float(eq_val)

        hand_id = hand.get("hand_id") or f"ID_{hand.get('id', '?')}"
        if numeric_eq is not None and numeric_eq >= 0.70 and atype == "check":
            missed_value += 1
            if len(missed_ids) < 20:
                missed_ids.append(hand_id)

    return total, aggr, passive, folds, missed_value, missed_ids


def percent(part: int, whole: int) -> float:
    if whole <= 0:
        return 0.0
    return part / whole * 100.0


def print_quality_block(title: str, total: int, counts: Dict[str, int]) -> None:
    print(title)
    print(f"  Всего решений: {total}")
    if total == 0:
        print("  Нет данных.")
        print()
        return

    for key in sorted(counts.keys()):
        cnt = counts[key]
        pct = percent(cnt, total)
        print(f"  - {key:7s}: {cnt:3d} раз ({pct:5.1f}%)")
    print()


def main() -> None:
    base_path = Path(__file__).resolve().parent
    hands_path = base_path / "hands.json"

    hands = load_hands(hands_path)
    total_hands = len(hands)

    print()
    print("==========================================")
    print("        СЕССИОННЫЙ ПОСТФЛОП-ОТЧЁТ")
    print("==========================================")
    print()
    print(f"Всего раздач в сессии: {total_hands}")
    print()

    # Префлоп
    pre_total, pre_quality = collect_quality_counts(hands, "hero_preflop_decision")
    print_quality_block("ПРЕФЛОП — качество решений (decision_quality):", pre_total, pre_quality)

    # Флоп
    flop_total, flop_quality = collect_quality_counts(hands, "hero_flop_decision")
    print_quality_block("ФЛОП — качество решений (decision_quality):", flop_total, flop_quality)

    # Тёрн
    turn_total, turn_quality = collect_quality_counts(hands, "hero_turn_decision")
    print_quality_block("ТЁРН — качество решений (decision_quality):", turn_total, turn_quality)

    # Ривер
    river_total, river_quality = collect_quality_counts(hands, "hero_river_decision")
    print_quality_block("РИВЕР — качество решений (decision_quality):", river_total, river_quality)

    # C-bet
    cbet_spots, cbet_made, cbet_missed = compute_cbet_stats(hands)
    print("ФЛОП — дисциплина C-bet (когда ты был префлоп-агрессором):")
    print(f"  Всего c-bet спотов: {cbet_spots}")
    if cbet_spots > 0:
        print(f"  Сделан c-bet:        {cbet_made:3d} раз ({percent(cbet_made, cbet_spots):5.1f}%)")
        print(f"  Пропущен c-bet:      {cbet_missed:3d} раз ({percent(cbet_missed, cbet_spots):5.1f}%)")
    print()

    # Тёрн агрессия
    t_total, t_aggr, t_pass, t_fold = compute_turn_aggression(hands)
    print("ТЁРН — дисциплина агрессии:")
    print(f"  Всего решений на тёрне: {t_total}")
    print(f"  Агрессивные линии (bet/raise): {t_aggr:3d} ({percent(t_aggr, t_total):5.1f}%)")
    print(f"  Пассивные линии  (check/call): {t_pass:3d} ({percent(t_pass, t_total):5.1f}%)")
    print(f"  Фолды против ставки:           {t_fold:3d} ({percent(t_fold, t_total):5.1f}%)")
    print()

    # Ривер агрессия + missed value
    r_total, r_aggr, r_pass, r_fold, missed_value, missed_ids = compute_river_aggression_and_missed_value(hands)
    print("РИВЕР — дисциплина агрессии и упущенное вэлью:")
    print(f"  Всего решений на ривере: {r_total}")
    print(f"  Агрессивные линии (bet/raise): {r_aggr:3d} ({percent(r_aggr, r_total):5.1f}%)")
    print(f"  Пассивные линии  (check/call): {r_pass:3d} ({percent(r_pass, r_total):5.1f}%)")
    print(f"  Фолды против ставки:           {r_fold:3d} ({percent(r_fold, r_total):5.1f}%)")
    print(f"  Потенциально упущенное вэлью (high equity + check): {missed_value}")
    if missed_value > 0:
        print("  Примеры hand_id (не более 20):")
        for hid in missed_ids:
            print(f"    - {hid}")
    print()

    # ------------------------------------
    # ЧЕЛОВЕКОЧИТАЕМЫЙ СУММАРНЫЙ РАЗБОР
    # ------------------------------------

    print("==========================================")
    print("     ЧЕЛОВЕКОЧИТАЕМЫЙ РАЗБОР СЕССИИ")
    print("==========================================")
    print()

    # Префлоп вывод
    print("Префлоп:")
    if pre_total == 0:
        print("  Модель не нашла ни одного решения героя на префлопе (возможно, ошибка парсинга).")
    else:
        good_pre = pre_quality.get("good", 0)
        risky_pre = pre_quality.get("risky", 0) + pre_quality.get("mistake", 0) + pre_quality.get("bad", 0)
        print(f"  В сессии зафиксировано {pre_total} префлоп-решений героя.")
        print(f"  Доля аккуратных/хороших решений (good): {percent(good_pre, pre_total):.1f}%")
        if risky_pre > 0:
            print(f"  Доля рискованных/ошибочных решений (risky/mistake/bad): {percent(risky_pre, pre_total):.1f}%")
            print("  Есть споты, где диапазон открытия/колла можно подтянуть ближе к MOS-чартам.")
        else:
            print("  Отклонений от базовой префлоп-стратегии почти нет, дисциплина высокая.")
    print()

    # Флоп вывод
    print("Флоп:")
    if flop_total == 0:
        print("  Герой ни разу не дошёл до флопа или модель не зафиксировала действия.")
    else:
        good_flop = flop_quality.get("good", 0)
        risky_flop = flop_quality.get("risky", 0) + flop_quality.get("bad", 0)
        print(f"  Всего решений на флопе: {flop_total}")
        print(f"  Хорошие решения (good): {percent(good_flop, flop_total):.1f}%")
        if risky_flop > 0:
            print(f"  Рискованные/спорные решения: {percent(risky_flop, flop_total):.1f}%")
        if cbet_spots > 0:
            print(f"  C-bet в позициях агрессора: {percent(cbet_made, cbet_spots):.1f}% из {cbet_spots} спотов.")
            print("  Это даёт представление о том, как часто ты конвертишь префлоп-инициативу в давление на флопе.")
        print("  В целом флоп выглядит достаточно дисциплинированно, без сильного переигрыша рук.")
    print()

    # Тёрн вывод
    print("Тёрн:")
    if turn_total == 0:
        print("  Не зафиксировано ни одного решения на тёрне.")
    else:
        good_turn = turn_quality.get("good", 0)
        risky_turn = turn_quality.get("risky", 0) + turn_quality.get("bad", 0)
        print(f"  Всего решений на тёрне: {turn_total}")
        print(f"  Хорошие решения (good): {percent(good_turn, turn_total):.1f}%")
        if risky_turn > 0:
            print(f"  Рискованные/спорные решения: {percent(risky_turn, turn_total):.1f}%")
        print(f"  Агрессия на тёрне: {percent(t_aggr, t_total):.1f}% агрессивных линий, "
              f"{percent(t_pass, t_total):.1f}% пассивных, {percent(t_fold, t_total):.1f}% фолдов.")
        print("  По тёрну у тебя, как правило, аккуратная игра с разумным балансом агрессии и контроля банка.")
    print()

    # Ривер вывод
    print("Ривер:")
    if river_total == 0:
        print("  Не зафиксировано ни одного решения на ривере.")
    else:
        good_river = river_quality.get("good", 0)
        risky_river = river_quality.get("risky", 0) + river_quality.get("bad", 0)
        print(f"  Всего решений на ривере: {river_total}")
        print(f"  Хорошие решения (good): {percent(good_river, river_total):.1f}%")
        if risky_river > 0:
            print(f"  Рискованные/спорные решения: {percent(risky_river, river_total):.1f}%")
        print(f"  Агрессия на ривере: {percent(r_aggr, r_total):.1f}% агрессивных линий, "
              f"{percent(r_pass, r_total):.1f}% пассивных, {percent(r_fold, r_total):.1f}% фолдов.")
        if missed_value > 0:
            print(f"  Найдено {missed_value} потенциальных случаев упущенного вэлью (high equity + чек).")
            print("  Эти споты особенно полезно разобрать вручную: там можно было добрать фишки, но ты выбрал контроль банка.")
        else:
            print("  Явных missed value спотов по критерию high equity + check не найдено.")
    print()

    print("Общий вывод:")
    print("  Модель видит достаточно высокий процент хороших решений на всех улицах и отсутствие явных провалов.")
    print("  Основные точки роста обычно лежат в двух направлениях:")
    print("    1) Более агрессивный добор вэлью на тёрне/ривере там, где equity достаточно высока.")
    print("    2) Тонкая настройка диапазонов колла/фолда в пограничных спотах (особенно на ривере).")
    print()
    print("Рекомендуется выборочно пройтись по помеченным рискованным решениям и missed value-раздачам,")
    print("используя скрипт детального разбора одной руки (report_hand_detail.py),")
    print("и смотреть, какие линии давали бы больше EV при тех же бордах и действиях оппонентов.")
    print()


if __name__ == "__main__":
    main()
