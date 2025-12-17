import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# =====================
#  Общие утилиты
# =====================

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


# =====================
#  Анализ префлопа / RFI
# =====================

def analyze_preflop_rfi(hands: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Сводка по префлопу:
      - сколько было RFI-спотов (герой ходит первым)
      - сколько из них с ошибками по диапазону
      - дисциплина по позициям
    """
    rfi_spots = 0
    rfi_errors = 0

    # дисциплина по позициям: {pos: {"spots": int, "errors": int}}
    pos_stats: Dict[str, Dict[str, int]] = {}

    # типы ошибок по диапазону (если есть error_type)
    error_types: Dict[str, int] = {}

    for hand in hands:
        pre_analysis = hand.get("hero_preflop_analysis") or {}
        pre_decision = hand.get("hero_preflop_decision") or {}
        range_disc = pre_decision.get("range_discipline") or {}

        hero_pos = pre_analysis.get("hero_position") or hand.get("hero_position")

        was_first_in = pre_analysis.get("was_first_in")

        # RFI-спот: ты первый в раздаче (open-raise / iso-raise, без предыдущих рейзов/коллов)
        if was_first_in:
            rfi_spots += 1
            if hero_pos:
                pos_stats.setdefault(hero_pos, {"spots": 0, "errors": 0})
                pos_stats[hero_pos]["spots"] += 1

            error_type = range_disc.get("error_type")
            if error_type:
                rfi_errors += 1
                if hero_pos:
                    pos_stats[hero_pos]["errors"] += 1
                error_types[error_type] = error_types.get(error_type, 0) + 1

    return {
        "rfi_spots": rfi_spots,
        "rfi_errors": rfi_errors,
        "pos_stats": pos_stats,
        "error_types": error_types,
    }


# =====================
#  Анализ постфлопа
# =====================

def _collect_decision_quality(decision: Dict[str, Any], counter: Dict[str, int]) -> None:
    dq = decision.get("decision_quality")
    if isinstance(dq, str):
        counter[dq] = counter.get(dq, 0) + 1


def _collect_action_type(decision: Dict[str, Any], counter: Dict[str, int]) -> None:
    atype = decision.get("action_type")
    if isinstance(atype, str):
        counter[atype] = counter.get(atype, 0) + 1


def analyze_postflop(hands: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Сводка по флоп/тёрн/риверу:
      - сколько раз был action героя
      - распределение decision_quality и action_type
    """
    result: Dict[str, Any] = {}

    streets = [
        ("flop", "hero_flop_decision"),
        ("turn", "hero_turn_decision"),
        ("river", "hero_river_decision"),
    ]

    for street_name, key in streets:
        total_spots = 0
        quality_counter: Dict[str, int] = {}
        action_counter: Dict[str, int] = {}

        for hand in hands:
            dec = hand.get(key) or {}
            if not dec:
                continue

            total_spots += 1
            _collect_decision_quality(dec, quality_counter)
            _collect_action_type(dec, action_counter)

        result[street_name] = {
            "total_spots": total_spots,
            "quality_counter": quality_counter,
            "action_counter": action_counter,
        }

    return result


# =====================
#  Missed value на ривере
#  (reuse логики из report_missed_value)
# =====================

def find_missed_value_spots(hands: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Возвращает два списка:
      1) missed_value_checks  — сильная рука, IP, ривер, но герой чекнул
      2) missed_value_passive_calls — сильная рука, IP, ривер, герой только колл против небольшой ставки
    """
    missed_value_checks: List[Dict[str, Any]] = []
    missed_value_passive_calls: List[Dict[str, Any]] = []

    for hand in hands:
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
        if (
            hero_ip is True
            and est_eq >= 0.70
            and action_type == "call_vs_bet"
        ):
            if pot_before is not None and amount is not None and pot_before > 0:
                frac = amount / pot_before
            else:
                frac = None

            if frac is not None and frac <= 0.33:
                missed_value_passive_calls.append(
                    {
                        "hand_id": hand.get("hand_id"),
                        "id": hand.get("id"),
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


# =====================
#  Ключевые руки для разбора
# =====================

def collect_key_hands(hands: List[Dict[str, Any]], max_examples: int = 10) -> List[Dict[str, Any]]:
    """
    Собираем раздачи, где есть risky/mistake/bad решения хотя бы на одной улице.
    """
    key_hands: List[Dict[str, Any]] = []

    for hand in hands:
        hand_id = hand.get("hand_id")
        idx = hand.get("id")
        hero_cards = hand.get("hero_cards") or []
        board = hand.get("board") or []

        issues: List[str] = []

        for street_name, key in [
            ("preflop", "hero_preflop_decision"),
            ("flop", "hero_flop_decision"),
            ("turn", "hero_turn_decision"),
            ("river", "hero_river_decision"),
        ]:
            dec = hand.get(key) or {}
            dq = dec.get("decision_quality")
            atype = dec.get("action_type")
            if dq in ("risky", "mistake", "bad"):
                issues.append(f"{street_name}: {dq} ({atype})")

        if issues:
            key_hands.append(
                {
                    "hand_id": hand_id,
                    "id": idx,
                    "hero_cards": hero_cards,
                    "board": board,
                    "issues": issues,
                }
            )

    # можно было бы сортировать по важности, но пока просто первые N
    return key_hands[:max_examples]


# =====================
#  Печать Session Overview
# =====================

def _print_percent(part: int, total: int) -> str:
    if total <= 0:
        return "0.0%"
    return f"{(part * 100.0) / total:.1f}%"

def build_coach_summary(
    preflop_stats: Dict[str, Any],
    postflop_stats: Dict[str, Any],
    missed_checks: List[Dict[str, Any]],
    missed_calls: List[Dict[str, Any]],
    key_hands: List[Dict[str, Any]],
    total_hands: int,
) -> Dict[str, Any]:
    """
    Возвращает структурированный "человекочитаемый" итог по сессии.
    UI потом сможет это рендерить как отдельный блок.
    """
    rfi_spots = int(preflop_stats.get("rfi_spots", 0) or 0)
    rfi_errors = int(preflop_stats.get("rfi_errors", 0) or 0)
    pos_stats = preflop_stats.get("pos_stats") or {}

    def pct(a: int, b: int) -> float:
        if b <= 0:
            return 0.0
        return 100.0 * float(a) / float(b)

    # --- качество по улицам ---
    def street_good_pct(street: str) -> float:
        s = postflop_stats.get(street) or {}
        total = int(s.get("total_spots", 0) or 0)
        qcnt = s.get("quality_counter") or {}
        good = int(qcnt.get("good", 0) or 0)
        return pct(good, total)

    flop_good = street_good_pct("flop")
    turn_good = street_good_pct("turn")
    river_good = street_good_pct("river")

    # --- missed value ---
    mv_total = len(missed_checks) + len(missed_calls)

    # --- выявляем проблемные позиции по RFI дисциплине ---
    weak_positions: List[str] = []
    for pos, vals in pos_stats.items():
        spots = int(vals.get("spots", 0) or 0)
        errs = int(vals.get("errors", 0) or 0)
        if spots > 0:
            disc = 100.0 * float(spots - errs) / float(spots)
            # считаем "слабым местом" только если есть минимум 3 спота и дисциплина < 90%
            if spots >= 3 and disc < 90.0:
                weak_positions.append(f"{pos} ({disc:.1f}%, {errs}/{spots})")

    # --- общий "тон" сессии ---
    # Простая классификация: стабильная/смешанная/хаотичная
    avg_good = (flop_good + turn_good + river_good) / 3.0 if (flop_good + turn_good + river_good) > 0 else 0.0
    if avg_good >= 80.0:
        session_grade = "стабильная"
    elif avg_good >= 60.0:
        session_grade = "смешанная"
    else:
        session_grade = "хаотичная"

    # --- сильные стороны ---
    strengths: List[str] = []
    if flop_good >= 85.0:
        strengths.append(f"Флоп: высокая доля качественных решений (good ≈ {flop_good:.1f}%).")
    if turn_good >= 80.0:
        strengths.append(f"Тёрн: дисциплина линий держится (good ≈ {turn_good:.1f}%).")
    if rfi_spots > 0 and pct(rfi_errors, rfi_spots) <= 10.0:
        strengths.append(f"Префлоп: RFI-дисциплина в целом хорошая (ошибки ≈ {pct(rfi_errors, rfi_spots):.1f}%).")

    if not strengths:
        strengths.append("Сильные стороны не выделены жёсткими порогами — нужна чуть большая выборка рук для уверенных выводов.")

    # --- где теряется EV (по текущим сигналам) ---
    leaks: List[str] = []
    if rfi_errors > 0:
        leaks.append(f"Префлоп: есть отклонения от RFI-диапазонов (ошибок: {rfi_errors} из {rfi_spots}).")
    if weak_positions:
        leaks.append("Префлоп: слабые позиции по дисциплине RFI: " + ", ".join(weak_positions) + ".")
    if mv_total > 0:
        leaks.append(f"Ривер: найдены missed value споты (шт: {mv_total}).")

    if not leaks:
        leaks.append("Явных системных утечек по выбранным эвристикам не найдено (это хорошо, но выборка может быть небольшой).")

    # --- конкретные рекомендации ---
    recs: List[str] = []
    if weak_positions:
        recs.append("Ужесточи открытия/изолейты в проблемных позициях (часто это UTG/SB): в пограничных руках выбирай фолд.")
    if mv_total > 0:
        recs.append("Добавь на ривере тонкий вэлью-бет в позиции, когда оценочная equity высокая и линия оппонента пассивная.")
    if not recs:
        recs.append("Продолжай играть в том же стиле, но на следующей сессии увеличим чувствительность поиска missed value и проверим, где можно добирать чаще.")

    # --- итог одной строкой ---
    one_liner = f"Итог: сессия {session_grade}. Главный резерв EV — " + ("ривер (добор)" if mv_total > 0 else "точечная дисциплина префлопа/позиций") + "."

    # ключевые руки (короткий список)
    key_hand_ids: List[str] = []
    for h in key_hands[:5]:
        hid = h.get("hand_id")
        if isinstance(hid, str) and hid:
            key_hand_ids.append(hid)

    return {
        "session_grade": session_grade,
        "avg_good_pct": round(avg_good, 1),
        "strengths": strengths,
        "leaks": leaks,
        "recommendations": recs,
        "one_liner": one_liner,
        "key_hands": key_hand_ids,
        "meta": {
            "total_hands": total_hands,
            "rfi_spots": rfi_spots,
            "rfi_errors": rfi_errors,
            "missed_value_total": mv_total,
            "good_pct": {"flop": round(flop_good, 1), "turn": round(turn_good, 1), "river": round(river_good, 1)},
        },
    }

def print_session_overview(
    preflop_stats: Dict[str, Any],
    postflop_stats: Dict[str, Any],
    missed_checks: List[Dict[str, Any]],
    missed_calls: List[Dict[str, Any]],
    key_hands: List[Dict[str, Any]],
    total_hands: int,
) -> None:
    print("========== ОБЩИЙ ОТЧЁТ ПО СЕССИИ ==========")
    print(f"Всего раздач в сессии (в файле hands.json): {total_hands}")
    print()

    # --- Префлоп / RFI ---
    print("=== ПРЕФЛОП / RFI-ДИСЦИПЛИНА ===")
    rfi_spots = preflop_stats["rfi_spots"]
    rfi_errors = preflop_stats["rfi_errors"]
    pos_stats = preflop_stats["pos_stats"]
    error_types = preflop_stats["error_types"]

    print(f"Всего RFI-спотов (когда ты ходишь первым): {rfi_spots}")
    print(f"Ошибок по диапазону (по модели range_discipline): {rfi_errors} ({_print_percent(rfi_errors, rfi_spots)})")
    print()

    print("Дисциплина по позициям (только RFI-споты):")
    if not pos_stats:
        print("  Нет данных по RFI-спотам (возможно, во всех раздачах ты не был первым)")
    else:
        for pos, vals in pos_stats.items():
            spots = vals["spots"]
            errs = vals["errors"]
            disc = 100.0 * (spots - errs) / spots if spots > 0 else 0.0
            print(f"  {pos}: дисциплина {disc:.1f}%  (спотов: {spots}, ошибок: {errs})")
    print()

    if error_types:
        print("Типы ошибок по диапазону (по полю error_type):")
        for etype, cnt in error_types.items():
            print(f"  - {etype}: {cnt}")
    else:
        print("Модель не выделила явных типов ошибок по диапазону (error_type пуст).")
    print()

    # --- Постфлоп ---
    print("=== ПОСТФЛОП (ФЛОП / ТЁРН / РИВЕР) ===")

    for street in ("flop", "turn", "river"):
        data = postflop_stats.get(street) or {}
        total_spots_s = data.get("total_spots", 0)
        qcnt = data.get("quality_counter", {})
        acnt = data.get("action_counter", {})

        print(f"--- {street.upper()} ---")
        print(f"Всего раздач с действием героя на {street}: {total_spots_s}")

        if total_spots_s > 0:
            print("Качество решений (decision_quality):")
            for q in ("good", "ok", "risky", "mistake", "bad"):
                if q in qcnt:
                    print(f"  - {q:7}: {qcnt[q]:3} раз ({_print_percent(qcnt[q], total_spots_s)})")
            # прочие, если есть
            for q, cnt in qcnt.items():
                if q not in ("good", "ok", "risky", "mistake", "bad"):
                    print(f"  - {q:7}: {cnt:3} раз ({_print_percent(cnt, total_spots_s)})")

            print("Типы действий (action_type):")
            for atype, cnt in acnt.items():
                print(f"  - {atype:15}: {cnt:3} раз ({_print_percent(cnt, total_spots_s)})")
        else:
            print("  Герой ни разу не принимал решений на этой улице в текущей выборке.")
        print()

    # --- Missed Value ---
    total_mv = len(missed_checks) + len(missed_calls)
    print("=== MISSED VALUE НА РИВЕРЕ (по эвристике) ===")
    print(f"Всего потенциальных missed value спотов на ривере: {total_mv}")
    print(f"  - Чек в позиции с сильной рукой: {len(missed_checks)}")
    print(f"  - Пассивный колл против небольшой ставки в позиции: {len(missed_calls)}")
    print()

    if total_mv == 0:
        print("По текущим настройкам модель не нашла явных missed value спотов на ривере.")
        print("Это не означает идеальную игру, но крупные упущения вэлью по базовым критериям не зафиксированы.")
    else:
        print("Примеры missed value спотов (не более 5 каждого типа):")
        print("-- Чек с сильной рукой в позиции --")
        for spot in missed_checks[:5]:
            print(f"  Hand #{spot.get('id')} ({spot.get('hand_id')}), equity={spot.get('equity'):.2f}, борд={' '.join(spot.get('board') or [])}")
        print("-- Пассивный колл против небольшой ставки --")
        for spot in missed_calls[:5]:
            print(f"  Hand #{spot.get('id')} ({spot.get('hand_id')}), equity={spot.get('equity'):.2f}, борд={' '.join(spot.get('board') or [])}")
    print()

    # --- Ключевые руки ---
    print("=== КЛЮЧЕВЫЕ РУКИ ДЛЯ РАЗБОРА (сомнительные решения) ===")
    if not key_hands:
        print("Модель не нашла раздач с явно рискованными/ошибочными решениями по тегам decision_quality.")
    else:
        for hand_info in key_hands:
            hand_id = hand_info.get("hand_id")
            idx = hand_info.get("id")
            cards = hand_info.get("hero_cards") or []
            board = hand_info.get("board") or []
            issues = hand_info.get("issues") or []
            print(f"  - Hand #{idx} ({hand_id}) | карты героя: {' '.join(cards)}, борд: {' '.join(board)}")
            for iss in issues:
                print(f"      * {iss}")
    print()
    # --- Итоговый коуч-блок ---
    summary = build_coach_summary(
        preflop_stats=preflop_stats,
        postflop_stats=postflop_stats,
        missed_checks=missed_checks,
        missed_calls=missed_calls,
        key_hands=key_hands,
        total_hands=total_hands,
    )

    print("=== ИТОГОВЫЙ ВЕРДИКТ ПО СЕССИИ (коуч-вывод) ===")
    print(summary["one_liner"])
    print()
    print("Что было хорошо:")
    for i, s in enumerate(summary["strengths"], 1):
        print(f"  {i}. {s}")
    print()
    print("Где вероятно теряется EV:")
    for i, s in enumerate(summary["leaks"], 1):
        print(f"  {i}. {s}")
    print()
    print("Что делать в следующей сессии:")
    for i, s in enumerate(summary["recommendations"], 1):
        print(f"  {i}. {s}")
    if summary.get("key_hands"):
        print()
        print("Ключевые раздачи для просмотра:")
        for hid in summary["key_hands"]:
            print(f"  - {hid}")
    print()

    print("============= SESSION OVERVIEW ГОТОВ =============")
    print()


# =====================
#  MAIN
# =====================

def main() -> None:
    base_path = Path(__file__).resolve().parent
    hands_path = base_path / "hands.json"

    hands = load_hands(hands_path)

    preflop_stats = analyze_preflop_rfi(hands)
    postflop_stats = analyze_postflop(hands)
    missed_checks, missed_calls = find_missed_value_spots(hands)
    key_hands = collect_key_hands(hands, max_examples=10)

    print_session_overview(
        preflop_stats=preflop_stats,
        postflop_stats=postflop_stats,
        missed_checks=missed_checks,
        missed_calls=missed_calls,
        key_hands=key_hands,
        total_hands=len(hands),
    )


if __name__ == "__main__":
    main()
