from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Any


ALLOWED_POS = {"EP", "MP", "HJ", "CO"}

HAND_RE = re.compile(r"^(?:[2-9TJQKA]{2}|[2-9TJQKA]{1}[2-9TJQKA]{1}[so])$")


def project_root() -> Path:
    return Path(__file__).resolve().parent


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Не найден файл: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise ValueError(f"Не удалось прочитать JSON: {path}. Ошибка: {e}")


def save_json(path: Path, data: Dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def norm_pos(p: str) -> str:
    p = p.strip().upper()
    if p not in ALLOWED_POS:
        raise ValueError(f"Неверная позиция '{p}'. Разрешено: {', '.join(sorted(ALLOWED_POS))}")
    return p


def norm_hand(h: str) -> str:
    h = h.strip()
    h = h.replace("10", "T").replace("t", "T").replace("j", "J").replace("q", "Q").replace("k", "K").replace("a", "A")
    h = h.replace("s", "s").replace("o", "o")
    if not HAND_RE.match(h):
        raise ValueError(
            f"Неверный формат руки '{h}'. Примеры: AKo, A9o, KTs, QJo, 76s, QQ."
        )
    # Для пар: "AA" и т.п. — ок.
    # Для непарных: нормализуем порядок рангов (A выше K и т.д.)
    if len(h) == 3:
        r1, r2, suited = h[0], h[1], h[2]
        order = "23456789TJQKA"
        if order.index(r1) < order.index(r2):
            h = f"{r2}{r1}{suited}"
    return h


def ensure_user_schema(data: Dict[str, Any]) -> None:
    if "rfi" not in data or not isinstance(data["rfi"], dict):
        data["rfi"] = {}
    for p in ALLOWED_POS:
        if p not in data["rfi"] or not isinstance(data["rfi"][p], list):
            data["rfi"][p] = []
    if "meta" not in data or not isinstance(data["meta"], dict):
        data["meta"] = {"name": "User MOS RFI", "version": 1, "format": "min_position", "positions": ["EP", "MP", "HJ", "CO"]}


def cmd_show(user_path: Path, pos: str) -> None:
    data = load_json(user_path)
    ensure_user_schema(data)
    p = norm_pos(pos)
    hands = sorted(set(norm_hand(x) for x in data["rfi"].get(p, [])))
    print(f"USER RFI [{p}] ({len(hands)} рук):")
    if hands:
        print("  " + " ".join(hands))
    else:
        print("  (пусто) — значит используется DEFAULT для этой позиции")


def cmd_add(user_path: Path, pos: str, hand: str) -> None:
    data = load_json(user_path)
    ensure_user_schema(data)
    p = norm_pos(pos)
    h = norm_hand(hand)

    current = [norm_hand(x) for x in data["rfi"].get(p, [])]
    s = set(current)
    if h in s:
        print(f"Уже есть: {p} {h}")
        return

    current.append(h)
    data["rfi"][p] = sorted(set(current))
    save_json(user_path, data)
    print(f"Добавлено: {p} {h}")


def cmd_remove(user_path: Path, pos: str, hand: str) -> None:
    data = load_json(user_path)
    ensure_user_schema(data)
    p = norm_pos(pos)
    h = norm_hand(hand)

    current = [norm_hand(x) for x in data["rfi"].get(p, [])]
    s = set(current)
    if h not in s:
        print(f"Нет такой руки в USER: {p} {h}")
        return

    s.remove(h)
    data["rfi"][p] = sorted(s)
    save_json(user_path, data)
    print(f"Удалено: {p} {h}")


def cmd_clear(user_path: Path, pos: str) -> None:
    data = load_json(user_path)
    ensure_user_schema(data)
    p = norm_pos(pos)
    data["rfi"][p] = []
    save_json(user_path, data)
    print(f"Очищено: {p}. Теперь для этой позиции будет использоваться DEFAULT.")


def usage() -> None:
    print(
        "Использование:\n"
        "  python edit_rfi_ranges.py show <POS>\n"
        "  python edit_rfi_ranges.py add <POS> <HAND>\n"
        "  python edit_rfi_ranges.py remove <POS> <HAND>\n"
        "  python edit_rfi_ranges.py clear <POS>\n\n"
        "Где POS: EP|MP|HJ|CO\n"
        "HAND: AKo, KTs, QJo, 76s, QQ и т.д.\n"
        "Важно: если USER-список позиции пустой — используется DEFAULT диапазон.\n"
    )


def main(argv: List[str]) -> int:
    root = project_root()
    user_path = root / "ranges" / "user_rfi.json"

    if len(argv) < 2:
        usage()
        return 2

    cmd = argv[1].strip().lower()

    try:
        if cmd == "show":
            if len(argv) != 3:
                usage()
                return 2
            cmd_show(user_path, argv[2])
            return 0

        if cmd == "add":
            if len(argv) != 4:
                usage()
                return 2
            cmd_add(user_path, argv[2], argv[3])
            return 0

        if cmd == "remove":
            if len(argv) != 4:
                usage()
                return 2
            cmd_remove(user_path, argv[2], argv[3])
            return 0

        if cmd == "clear":
            if len(argv) != 3:
                usage()
                return 2
            cmd_clear(user_path, argv[2])
            return 0

        usage()
        return 2

    except Exception as e:
        print(f"Ошибка: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
