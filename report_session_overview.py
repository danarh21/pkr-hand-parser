from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, List, Optional


def _load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _to_float(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        return float(x)
    except (TypeError, ValueError):
        return default


def _normalize_ev_estimate(ev_est: Any) -> Dict[str, Any]:
    """
    Новый контракт:
      ev_action: float
      ev_action_label: str
    Поддержка старого:
      ev: float, а ev_action мог быть строкой.
    """
    if not isinstance(ev_est, dict):
        return {"ev_action": 0.0, "ev_action_label": "missing_ev_estimate", "model": "v1_baseline"}

    if "ev_action" in ev_est and not isinstance(ev_est.get("ev_action"), str):
        ev_num = _to_float(ev_est.get("ev_action"), 0.0)
    elif "ev" in ev_est:
        ev_num = _to_float(ev_est.get("ev"), 0.0)
    else:
        ev_num = 0.0

    if isinstance(ev_est.get("ev_action_label"), str):
        label = ev_est.get("ev_action_label", "")
    elif isinstance(ev_est.get("ev_action"), str):
        label = ev_est.get("ev_action", "")
    else:
        label = ""

    model = ev_est.get("model", "v1_baseline")
    if not isinstance(model, str):
        model = "v1_baseline"

    out = dict(ev_est)
    out["ev_action"] = float(ev_num)
    out["ev_action_label"] = label
    out["model"] = model
    if "ev" in out:
        out.pop("ev", None)
    return out


def _iter_hand_reviews(data: Any) -> List[Dict[str, Any]]:
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        # уже hand_review
        if "hand_id" in data or "preflop" in data or "streets" in data:
            return [data]
        for key in ("hand_reviews", "hands", "items"):
            if key in data and isinstance(data[key], list):
                return [x for x in data[key] if isinstance(x, dict)]
    return []


def _get_street_obj(hand_review: Dict[str, Any], street: str) -> Dict[str, Any]:
    if street in hand_review and isinstance(hand_review[street], dict):
        return hand_review[street]

    streets = hand_review.get("streets")
    if isinstance(streets, dict) and isinstance(streets.get(street), dict):
        return streets[street]

    alt = f"{street}_result"
    if alt in hand_review and isinstance(hand_review[alt], dict):
        return hand_review[alt]

    return {}


def _get_hero_decision(street_obj: Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(street_obj.get("hero_decision"), dict):
        return street_obj["hero_decision"]
    if isinstance(street_obj.get("decision"), dict):
        return street_obj["decision"]
    for _, v in street_obj.items():
        if isinstance(v, dict) and ("ev_estimate" in v or "decision_quality" in v):
            return v
    return {}


def _signed(x: float) -> str:
    return f"{x:+.4f}"


def main() -> None:
    parser = argparse.ArgumentParser(description="PKR: Session Overview (EV-centric, Iteration 1).")
    parser.add_argument("json_path", help="JSON файл со списком hand_review (или объект с hands/hand_reviews).")
    args = parser.parse_args()

    try:
        data = _load_json(args.json_path)
    except FileNotFoundError:
        print(f"Файл не найден: {args.json_path}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Ошибка JSON: {e}", file=sys.stderr)
        sys.exit(1)

    hands = _iter_hand_reviews(data)
    if not hands:
        print("Не нашёл рук в JSON (ожидаю list[hand_review] или dict с ключом hands/hand_reviews).", file=sys.stderr)
        sys.exit(1)

    # агрегаты
    ev_sum = {"preflop": 0.0, "flop": 0.0, "turn": 0.0, "river": 0.0, "total": 0.0}
    decisions_count = 0

    dq_counts = {"good": 0, "marginal": 0, "mistake": 0, "blunder": 0, "unknown": 0}

    # Дополнительно: сколько раз по улицам EV был 0 (чтобы видеть “пустые” оценки)
    ev_zero_counts = {"preflop": 0, "flop": 0, "turn": 0, "river": 0}

    for hr in hands:
        hand_total = 0.0

        for street in ("preflop", "flop", "turn", "river"):
            st = _get_street_obj(hr, street)
            hd = _get_hero_decision(st)

            if isinstance(hd, dict) and hd:
                decisions_count += 1
                dq = str(hd.get("decision_quality") or "unknown").lower()
                if dq not in dq_counts:
                    dq = "unknown"
                dq_counts[dq] += 1

                ev_est = _normalize_ev_estimate(hd.get("ev_estimate"))
                evv = _to_float(ev_est.get("ev_action"), 0.0)
            else:
                evv = 0.0

            ev_sum[street] += float(evv)
            hand_total += float(evv)

            if abs(float(evv)) < 1e-12:
                ev_zero_counts[street] += 1

        ev_sum["total"] += float(hand_total)

    n_hands = len(hands)
    ev_avg = {k: (v / n_hands) for k, v in ev_sum.items()}

    print("=" * 72)
    print("SESSION OVERVIEW (Iteration 1)")
    print(f"Hands: {n_hands}")
    print(f"Street decisions counted: {decisions_count}")
    print("=" * 72)

    print()
    print("=== EV SUM ===")
    print(f"EV(preflop): {_signed(ev_sum['preflop'])}")
    print(f"EV(flop):    {_signed(ev_sum['flop'])}")
    print(f"EV(turn):    {_signed(ev_sum['turn'])}")
    print(f"EV(river):   {_signed(ev_sum['river'])}")
    print("-" * 26)
    print(f"EV(total):   {_signed(ev_sum['total'])}")

    print()
    print("=== EV AVG PER HAND ===")
    print(f"EV/preflop: {_signed(ev_avg['preflop'])}")
    print(f"EV/flop:    {_signed(ev_avg['flop'])}")
    print(f"EV/turn:    {_signed(ev_avg['turn'])}")
    print(f"EV/river:   {_signed(ev_avg['river'])}")
    print("-" * 26)
    print(f"EV/hand:    {_signed(ev_avg['total'])}")

    print()
    print("=== DECISION QUALITY (street-level counts) ===")
    for k in ("good", "marginal", "mistake", "blunder", "unknown"):
        print(f"{k.rjust(8)}: {dq_counts.get(k, 0)}")

    print()
    print("=== EV=0 COUNTS (by street, number of hands) ===")
    # тут счётчик по рукам, не по решениям: “в скольких руках на улице EV был 0”
    print(f"preflop: {ev_zero_counts['preflop']} / {n_hands}")
    print(f"flop:    {ev_zero_counts['flop']} / {n_hands}")
    print(f"turn:    {ev_zero_counts['turn']} / {n_hands}")
    print(f"river:   {ev_zero_counts['river']} / {n_hands}")

    print()
    print("OK")


if __name__ == "__main__":
    main()
