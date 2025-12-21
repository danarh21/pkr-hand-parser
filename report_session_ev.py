from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


ROOT = Path(__file__).resolve().parent
HANDS_JSON = ROOT / "hands.json"


STREETS = [
    ("preflop", "hero_preflop_decision"),
    ("flop", "hero_flop_decision"),
    ("turn", "hero_turn_decision"),
    ("river", "hero_river_decision"),
]


def _safe_float(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None


def _get_ev_action(decision: Any) -> Optional[float]:
    if not isinstance(decision, dict):
        return None
    ev = decision.get("ev_estimate")
    if not isinstance(ev, dict):
        return None
    return _safe_float(ev.get("ev_action"))


def _hand_label(hand: Dict[str, Any], idx: int) -> str:
    hid = hand.get("hand_id") or f"Hand#{idx}"
    return str(hid)


def _street_action_type(decision: Any) -> str:
    if not isinstance(decision, dict):
        return "none"
    return str(decision.get("action_type") or "unknown")


def _sum_ev_by_street(hand: Dict[str, Any]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for street, key in STREETS:
        ev = _get_ev_action(hand.get(key))
        out[street] = ev if ev is not None else 0.0
    return out


def load_hands() -> List[Dict[str, Any]]:
    if not HANDS_JSON.exists():
        raise FileNotFoundError(f"hands.json not found at: {HANDS_JSON}")
    return json.loads(HANDS_JSON.read_text(encoding="utf-8"))


def main() -> None:
    hands = load_hands()

    total_hands = len(hands)

    street_totals: Dict[str, float] = {s: 0.0 for s, _ in STREETS}
    street_counts: Dict[str, int] = {s: 0 for s, _ in STREETS}

    # action_type breakdown by street
    action_type_counts: Dict[str, Dict[str, int]] = {s: {} for s, _ in STREETS}
    action_type_ev: Dict[str, Dict[str, float]] = {s: {} for s, _ in STREETS}

    per_hand_ev: List[Tuple[float, str]] = []  # (total_ev, hand_id)
    per_hand_street_ev: Dict[str, List[Tuple[float, str]]] = {s: [] for s, _ in STREETS}

    for idx, hand in enumerate(hands, start=1):
        hand_id = _hand_label(hand, idx)

        hand_total_ev = 0.0
        for street, key in STREETS:
            decision = hand.get(key)
            ev = _get_ev_action(decision)

            if ev is not None:
                street_totals[street] += ev
                street_counts[street] += 1
                hand_total_ev += ev

                at = _street_action_type(decision)
                action_type_counts[street][at] = action_type_counts[street].get(at, 0) + 1
                action_type_ev[street][at] = action_type_ev[street].get(at, 0.0) + ev

                per_hand_street_ev[street].append((ev, hand_id))

        per_hand_ev.append((hand_total_ev, hand_id))

    total_ev = sum(street_totals.values())
    avg_ev_per_hand = total_ev / total_hands if total_hands else 0.0

    print("========== SESSION EV OVERVIEW ==========")
    print(f"Hands in file: {total_hands}")
    print(f"Total EV (sum of ev_action across streets): {total_ev:.4f}")
    print(f"Average EV per hand: {avg_ev_per_hand:.6f}")
    print()

    print("=== EV BY STREET ===")
    for street, _ in STREETS:
        cnt = street_counts[street]
        tot = street_totals[street]
        avg = (tot / cnt) if cnt else 0.0
        print(f"- {street:7s}: total_ev={tot:.4f} | decisions={cnt} | avg_ev/decision={avg:.6f}")
    print()

    print("=== TOP HANDS BY EV (TOTAL) ===")
    per_hand_ev_sorted = sorted(per_hand_ev, key=lambda x: x[0])
    worst = per_hand_ev_sorted[:5]
    best = list(reversed(per_hand_ev_sorted[-5:]))

    print("Worst 5:")
    for ev, hid in worst:
        print(f"  - {hid}: {ev:.4f}")

    print("Best 5:")
    for ev, hid in best:
        print(f"  - {hid}: {ev:.4f}")
    print()

    print("=== TOP HANDS BY EV (PER STREET) ===")
    for street, _ in STREETS:
        items = per_hand_street_ev[street]
        if not items:
            print(f"- {street}: no decisions with ev_estimate")
            continue
        items_sorted = sorted(items, key=lambda x: x[0])
        worst_s = items_sorted[:3]
        best_s = list(reversed(items_sorted[-3:]))

        print(f"- {street.upper()}:")
        print("    Worst 3:")
        for ev, hid in worst_s:
            print(f"      * {hid}: {ev:.4f}")
        print("    Best 3:")
        for ev, hid in best_s:
            print(f"      * {hid}: {ev:.4f}")
    print()

    print("=== ACTION TYPES (COUNT + EV) ===")
    for street, _ in STREETS:
        print(f"- {street.upper()}:")
        counts = action_type_counts[street]
        evs = action_type_ev[street]
        if not counts:
            print("    (no data)")
            continue
        # sort by count desc
        rows = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
        for at, c in rows:
            tot_ev = evs.get(at, 0.0)
            avg = tot_ev / c if c else 0.0
            print(f"    {at:18s} | n={c:3d} | total_ev={tot_ev:.4f} | avg_ev={avg:.6f}")

    print()
    print("============= SESSION EV OVERVIEW DONE =============")


if __name__ == "__main__":
    main()
