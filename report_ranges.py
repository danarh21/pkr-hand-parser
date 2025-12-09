import json
from pathlib import Path
from typing import List, Dict, Any, Optional

POSITIONS = ["UTG", "MP", "HJ", "CO", "BTN", "SB", "BB"]


def load_hands(json_path: str) -> List[Dict[str, Any]]:
    path = Path(json_path)
    if not path.exists():
        print(f"Файл {json_path} не найден.")
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            print("JSON имеет некорректный формат – ожидается список хендов (list).")
            return []
        return data
    except Exception as e:
        print(f"Ошибка чтения JSON: {e}")
        return []


def _safe_float(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        return float(x)
    except (TypeError, ValueError):
        return None


def classify_range_errors(hands: List[Dict[str, Any]]) -> Dict[str, Any]:
    # Базовая структура статистики
    stats: Dict[str, Any] = {
        "total_hands": 0,

        # Ошибки по типам
        "too_loose_open": 0,
        "too_early_position_open": 0,
        "too_tight_fold": 0,

        # EV-потери в bb
        "ev_loss_bb": {
            "too_loose_open": 0.0,
            "too_early_position_open": 0.0,
            "too_tight_fold": 0.0,  # пока не считаем EV для тайтовых фолдов
        },

        # Примеры ошибок
        "examples": {
            "too_loose_open": [],
            "too_early_position_open": [],
            "too_tight_fold": [],
        },

        # RFI-дисциплина
        "total_rfi_opportunities": 0,   # сколько раз у героя был шанс действовать первым (open/fold)
        "total_rfi_errors": 0,          # сколько из них были ошибками по RFI

        # Дисциплина по позициям
        "positions": {
            pos: {"opportunities": 0, "errors": 0}
            for pos in POSITIONS
        },
    }

    # Вспомогательная функция: учесть, что в этом хенде у героя был RFI-спот
    def register_rfi_opportunity(hero_position: Optional[str], is_error: bool):
        stats["total_rfi_opportunities"] += 1
        if is_error:
            stats["total_rfi_errors"] += 1

        pos = (hero_position or "").upper()
        if pos in stats["positions"]:
            stats["positions"][pos]["opportunities"] += 1
            if is_error:
                stats["positions"][pos]["errors"] += 1

    # Типы действий, которые считаем "RFI-контекстом" при игре первым
    RFI_ACTION_TYPES = {
        "open_raise",
        "open_limp",
        "iso_raise",
        "overlimp",
        "fold_preflop",
    }

    for hand in hands:
        stats["total_hands"] += 1

        decision = hand.get("hero_preflop_decision")
        if not decision:
            continue

        rd = decision.get("range_discipline")
        hpa = hand.get("hero_preflop_analysis") or {}
        hero_position = hpa.get("hero_position")
        was_first_in = hpa.get("was_first_in")
        action_type = decision.get("action_type")

        # Флаг: это раздача, где герой был первым в банке и решение относится к RFI-контексту
        is_rfi_spot = bool(
            was_first_in
            and action_type in RFI_ACTION_TYPES
        )

        error = rd.get("error_type") if rd else None

        # Если это RFI-спот, регистрируем его + отметим, была ли там ошибка
        if is_rfi_spot:
            is_error_here = error in (
                "too_loose_open",
                "too_early_position_open",
                "too_tight_fold",
            )
            register_rfi_opportunity(hero_position, is_error_here)

        # Далее — старая логика ошибок + EV
        if not rd or not error:
            continue

        math = decision.get("math", {})
        ev_simple = _safe_float(math.get("ev_simple"))
        bb = _safe_float(hand.get("big_blind"))

        def add_ev_loss(err_key: str):
            # Считаем только реально минусовые решения по нашей модели
            if ev_simple is None or bb is None or bb <= 0:
                return
            if ev_simple < 0:
                loss_bb = -ev_simple / bb
                stats["ev_loss_bb"][err_key] += loss_bb

        if error == "too_loose_open":
            stats["too_loose_open"] += 1
            add_ev_loss("too_loose_open")

            if len(stats["examples"]["too_loose_open"]) < 5:
                stats["examples"]["too_loose_open"].append({
                    "id": hand.get("id"),
                    "hand_key": hand.get("hero_preflop_equity", {}).get("hand_key"),
                    "hero_position": rd.get("hero_position"),
                    "comment": rd.get("range_comment"),
                })

        elif error == "too_early_position_open":
            stats["too_early_position_open"] += 1
            add_ev_loss("too_early_position_open")

            if len(stats["examples"]["too_early_position_open"]) < 5:
                stats["examples"]["too_early_position_open"].append({
                    "id": hand.get("id"),
                    "hand_key": hand.get("hero_preflop_equity", {}).get("hand_key"),
                    "hero_position": rd.get("hero_position"),
                    "mos_min_position": rd.get("mos_min_position"),
                    "comment": rd.get("range_comment"),
                })

        elif error == "too_tight_fold":
            stats["too_tight_fold"] += 1
            # EV для тайтовых фолдов пока не считаем — оставляем 0.0
            if len(stats["examples"]["too_tight_fold"]) < 5:
                stats["examples"]["too_tight_fold"].append({
                    "id": hand.get("id"),
                    "hand_key": hand.get("hero_preflop_equity", {}).get("hand_key"),
                    "hero_position": rd.get("hero_position"),
                    "mos_min_position": rd.get("mos_min_position"),
                    "comment": rd.get("range_comment"),
                })

    return stats


def print_report(stats: Dict[str, Any]) -> None:
    print("\n======================")
    print("     RFI-ОТЧЁТ")
    print("======================\n")

    print(f"Всего раздач: {stats['total_hands']}")
    print()

    # --- Ошибки по типам ---
    print("Ошибки по RFI (количество):")
    print(f"  🔴 Слишком лузовый open: {stats['too_loose_open']}")
    print(f"  🟠 Слишком ранний open:  {stats['too_early_position_open']}")
    print(f"  🔵 Слишком тайтовый фолд: {stats['too_tight_fold']}")
    print()

    # --- Дисциплина по RFI в целом ---
    opp = stats["total_rfi_opportunities"]
    err = stats["total_rfi_errors"]

    print("Дисциплина по RFI (когда ты ходишь первым):")
    if opp > 0:
        discipline = (opp - err) / opp * 100.0
        print(f"  Всего RFI-спотов: {opp}")
        print(f"  Ошибок по RFI:    {err}")
        print(f"  Общая дисциплина: {discipline:.1f}%")
    else:
        print("  RFI-споты не обнаружены (ни одного решения, где ты был первым в банке).")
    print()

    # --- Дисциплина по позициям ---
    print("Дисциплина по позициям (только RFI-споты):")
    for pos in POSITIONS:
        pstat = stats["positions"][pos]
        p_opp = pstat["opportunities"]
        p_err = pstat["errors"]
        if p_opp == 0:
            print(f"  {pos}:  нет данных")
        else:
            p_disc = (p_opp - p_err) / p_opp * 100.0
            print(
                f"  {pos}:  дисциплина {p_disc:.1f}%  "
                f"(спотов: {p_opp}, ошибок: {p_err})"
            )
    print()

    # --- EV-потери ---
    print("Оценочные потери EV (в больших блайнах, bb):")
    ev_loose = stats["ev_loss_bb"]["too_loose_open"]
    ev_early = stats["ev_loss_bb"]["too_early_position_open"]
    ev_tight = stats["ev_loss_bb"]["too_tight_fold"]

    print(f"  🔴 Лузовые open'ы:      -{ev_loose:.2f} bb")
    print(f"  🟠 Ранние open'ы:       -{ev_early:.2f} bb")

    if ev_tight == 0.0 and stats["too_tight_fold"] > 0:
        print("  🔵 Тайтовые фолды:      (EV пока не рассчитан, требуется отдельная модель)")
    else:
        print(f"  🔵 Тайтовые фолды:      -{ev_tight:.2f} bb")
    print()

    # --- Топ частых ошибок ---
    print("Топ типов ошибок по частоте:")
    errors_list = [
        ("too_early_position_open", "Слишком ранние open'ы", stats["too_early_position_open"]),
        ("too_loose_open", "Слишком лузовые open'ы", stats["too_loose_open"]),
        ("too_tight_fold", "Слишком тайтовые фолды", stats["too_tight_fold"]),
    ]
    errors_list = [e for e in errors_list if e[2] > 0]
    if not errors_list:
        print("  Явных ошибок по RFI пока не набралось — дисциплина выглядит очень аккуратной.")
    else:
        # сортируем по количеству по убыванию
        errors_list.sort(key=lambda x: x[2], reverse=True)
        for key, title, count in errors_list:
            print(f"  - {title}: {count}")
    print()

    # --- Примеры ---
    print("------ Примеры ошибок ------\n")

    def print_examples(err_type: str, title: str):
        examples = stats["examples"][err_type]
        if not examples:
            print(f"{title}: нет примеров\n")
            return
        print(f"{title}:")
        for ex in examples:
            print(f"  - Hand #{ex['id']}: {ex['hand_key']} | {ex['comment']}")
        print()

    print_examples("too_loose_open", "СЛИШКОМ ЛУЗОВЫЕ OPEN'Ы")
    print_examples("too_early_position_open", "СЛИШКОМ РАННИЕ OPEN'Ы")
    print_examples("too_tight_fold", "СЛИШКОМ ТАЙТОВЫЕ ФОЛДЫ")

    print("======================")
    print("   ОТЧЁТ ГОТОВ")
    print("======================\n")


def main() -> None:
    hands = load_hands("hands.json")
    if not hands:
        return

    stats = classify_range_errors(hands)
    print_report(stats)


if __name__ == "__main__":
    main()
