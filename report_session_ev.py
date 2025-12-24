from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


ROOT = Path(__file__).resolve().parent
HANDS_JSON = ROOT / "hands.json"

STREETS = ["preflop", "flop", "turn", "river"]


def _safe_float(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None


def _get_decision(hand: Dict[str, Any], street: str) -> Optional[Dict[str, Any]]:
    # legacy
    key = f"hero_{street}_decision"
    dec = hand.get(key)
    if isinstance(dec, dict):
        return dec

    # nested: hand["turn"]["hero_decision"] / ["decision"]
    st = hand.get(street)
    if isinstance(st, dict):
        dec2 = st.get("hero_decision") or st.get("decision")
        if isinstance(dec2, dict):
            return dec2

    # ui-ready: hand["streets"]["turn"]["hero_decision"]
    streets_obj = hand.get("streets")
    if isinstance(streets_obj, dict):
        st2 = streets_obj.get(street)
        if isinstance(st2, dict):
            dec3 = st2.get("hero_decision") or st2.get("decision")
            if isinstance(dec3, dict):
                return dec3

    return None


def _get_ev_action(decision: Any) -> Optional[float]:
    if not isinstance(decision, dict):
        return None
    ev = decision.get("ev_estimate")
    if not isinstance(ev, dict):
        return None

    v = ev.get("ev_action")
    if isinstance(v, str):
        v = None
    out = _safe_float(v)
    if out is not None:
        return out

    return _safe_float(ev.get("ev"))


def _get_missed_value_ev(decision: Any) -> float:
    """
    Missed value может лежать:
      1) decision["missed_value"]["missed_value_ev"]
      2) decision["ev_estimate"]["missed_value_ev"]
    """
    if not isinstance(decision, dict):
        return 0.0

    mv = decision.get("missed_value")
    if isinstance(mv, dict):
        v = _safe_float(mv.get("missed_value_ev"))
        if v is not None and v > 0:
            return v

    ev = decision.get("ev_estimate")
    if isinstance(ev, dict):
        v2 = _safe_float(ev.get("missed_value_ev"))
        if v2 is not None and v2 > 0:
            return v2

    return 0.0


def _street_action_type(decision: Any) -> str:
    if not isinstance(decision, dict):
        return "none"
    return str(decision.get("action_type") or "unknown")


def _hand_label(hand: Dict[str, Any], idx: int) -> str:
    return str(hand.get("hand_id") or f"Hand#{idx}")


def load_hands() -> List[Dict[str, Any]]:
    if not HANDS_JSON.exists():
        raise FileNotFoundError(f"hands.json not found at: {HANDS_JSON}")
    return json.loads(HANDS_JSON.read_text(encoding="utf-8"))


def main() -> None:
    hands = load_hands()
    total_hands = len(hands)

    street_totals: Dict[str, float] = {s: 0.0 for s in STREETS}
    street_counts: Dict[str, int] = {s: 0 for s in STREETS}

    action_type_counts: Dict[str, Dict[str, int]] = {s: {} for s in STREETS}
    action_type_ev: Dict[str, Dict[str, float]] = {s: {} for s in STREETS}

    per_hand_ev: List[Tuple[float, str]] = []
    per_hand_street_ev: Dict[str, List[Tuple[float, str]]] = {s: [] for s in STREETS}

    # Missed value aggregation
    missed_totals: Dict[str, float] = {s: 0.0 for s in STREETS}
    missed_counts: Dict[str, int] = {s: 0 for s in STREETS}
    per_hand_missed: List[Tuple[float, str]] = []  # (missed_ev_total, hand_id)
    per_hand_street_missed: Dict[str, List[Tuple[float, str]]] = {s: [] for s in STREETS}

    for idx, hand in enumerate(hands, start=1):
        hand_id = _hand_label(hand, idx)

        hand_total_ev = 0.0
        hand_total_missed = 0.0

        for street in STREETS:
            decision = _get_decision(hand, street)

            ev = _get_ev_action(decision)
            if ev is not None:
                street_totals[street] += ev
                street_counts[street] += 1
                hand_total_ev += ev

                at = _street_action_type(decision)
                action_type_counts[street][at] = action_type_counts[street].get(at, 0) + 1
                action_type_ev[street][at] = action_type_ev[street].get(at, 0.0) + ev

                per_hand_street_ev[street].append((ev, hand_id))

            mv_ev = _get_missed_value_ev(decision)
            if mv_ev > 0:
                missed_totals[street] += mv_ev
                missed_counts[street] += 1
                hand_total_missed += mv_ev
                per_hand_street_missed[street].append((mv_ev, hand_id))

        per_hand_ev.append((hand_total_ev, hand_id))
        per_hand_missed.append((hand_total_missed, hand_id))

    total_ev = sum(street_totals.values())
    avg_ev_per_hand = total_ev / total_hands if total_hands else 0.0

    total_missed = sum(missed_totals.values())
    avg_missed_per_hand = total_missed / total_hands if total_hands else 0.0

    print("========== SESSION EV OVERVIEW ==========")
    print(f"Hands in file: {total_hands}")
    print(f"Total EV (sum of ev_action across streets): {total_ev:.4f}")
    print(f"Average EV per hand: {avg_ev_per_hand:.6f}")
    print()

    print("=== EV BY STREET ===")
    for street in STREETS:
        cnt = street_counts[street]
        tot = street_totals[street]
        avg = (tot / cnt) if cnt else 0.0
        print(f"- {street:7s}: total_ev={tot:.4f} | decisions={cnt} | avg_ev/decision={avg:.6f}")
    print()

    print("=== MISSED VALUE EV (Iteration 2) ===")
    print(f"Total Missed EV: {total_missed:.4f}")
    print(f"Average Missed EV per hand: {avg_missed_per_hand:.6f}")
    for street in STREETS:
        cnt = missed_counts[street]
        tot = missed_totals[street]
        avg = (tot / cnt) if cnt else 0.0
        print(f"- {street:7s}: missed_total={tot:.4f} | spots={cnt} | avg_missed/spot={avg:.6f}")
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

    print("=== TOP HANDS BY MISSED VALUE EV (TOTAL) ===")
    per_hand_missed_sorted = sorted(per_hand_missed, key=lambda x: x[0])
    worst_missed = list(reversed(per_hand_missed_sorted[-5:]))  # biggest missed
    print("Biggest missed 5:")
    for mv, hid in worst_missed:
        print(f"  - {hid}: {mv:.4f}")
    print()

    print("=== TOP HANDS BY EV (PER STREET) ===")
    for street in STREETS:
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

    print("=== TOP MISSED VALUE EV (PER STREET) ===")
    for street in STREETS:
        items = per_hand_street_missed[street]
        if not items:
            print(f"- {street}: no missed value spots")
            continue
        items_sorted = sorted(items, key=lambda x: x[0])
        best_s = list(reversed(items_sorted[-3:]))

        print(f"- {street.upper()}:")
        print("    Biggest missed 3:")
        for mv, hid in best_s:
            print(f"      * {hid}: {mv:.4f}")
    print()

    print("=== ACTION TYPES (COUNT + EV) ===")
    for street in STREETS:
        print(f"- {street.upper()}:")
        counts = action_type_counts[street]
        evs = action_type_ev[street]
        if not counts:
            print("    (no data)")
            continue
        rows = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
        for at, c in rows:
            tot_ev = evs.get(at, 0.0)
            avg = tot_ev / c if c else 0.0
            print(f"    {at:18s} | n={c:3d} | total_ev={tot_ev:.4f} | avg_ev={avg:.6f}")

    print()
    print("============= SESSION EV OVERVIEW DONE =============")


if __name__ == "__main__":
    main()
