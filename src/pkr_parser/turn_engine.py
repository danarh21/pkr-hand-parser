from __future__ import annotations

from typing import Optional, Dict, Any, List

from .ev_tools import compute_ev_estimate_v1, generate_assumptions, generate_context


RANK_ORDER = {
    "2": 2,
    "3": 3,
    "4": 4,
    "5": 5,
    "6": 6,
    "7": 7,
    "8": 8,
    "9": 9,
    "T": 10,
    "J": 11,
    "Q": 12,
    "K": 13,
    "A": 14,
}

# 🔥 Сильные категории для Missed Value (MVP)
STRONG_CATS = {
    "two_pair",
    "set",
    "straight",
    "flush",
    "full_house",
    "quads",
}


def _get(a: Any, key: str, default: Any = None) -> Any:
    if isinstance(a, dict):
        return a.get(key, default)
    return getattr(a, key, default)


def _safe_float(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None


def _clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))


def _get_preflop_role(hero_preflop_analysis: Optional[Any], hero_position: Optional[str]) -> str:
    if hero_preflop_analysis is None:
        return "checked_bb" if hero_position == "BB" else "unknown"

    if isinstance(hero_preflop_analysis, dict):
        act = hero_preflop_analysis.get("action_type") or hero_preflop_analysis.get("action_kind")
    else:
        act = getattr(hero_preflop_analysis, "action_type", None) or getattr(
            hero_preflop_analysis, "action_kind", None
        )

    if act in ("open_raise", "3bet", "4bet", "iso_raise"):
        return "aggressor"
    if act in ("call_vs_raise", "cold_call", "call"):
        return "caller"
    if act in ("fold_preflop", "fold"):
        return "folder"
    return "unknown"


def _detect_turn_card(board: Optional[List[str]]) -> Optional[str]:
    return board[3] if board and len(board) >= 4 else None


def _players_to_turn(actions: List[Any]) -> int:
    names = set()
    for a in actions:
        if _get(a, "street") == "turn":
            pn = _get(a, "player_name") or _get(a, "player") or _get(a, "name")
            if pn:
                names.add(str(pn))
    return max(2, len(names)) if names else 2


def _is_multiway(players_to_turn: int) -> bool:
    return players_to_turn >= 3


def _is_hero_in_position(hero_position: Optional[str]) -> bool:
    return (hero_position or "").upper() in ("BTN", "CO", "HJ")


def _infer_hero_ip_from_actions_on_street(turn_actions: List[Any], hero_name: str) -> Optional[bool]:
    first_hero = None
    first_villain = None

    for i, a in enumerate(turn_actions):
        p = _get(a, "player_name") or _get(a, "player") or _get(a, "name")
        if p == hero_name and first_hero is None:
            first_hero = i
        if p != hero_name and p is not None and first_villain is None:
            first_villain = i

    if first_hero is None or first_villain is None:
        return None
    return first_hero > first_villain


def _parse_bet_amount(action_obj: Any) -> Optional[float]:
    for attr in ("amount", "bet", "size", "value"):
        v = _get(action_obj, attr)
        try:
            if v is not None:
                return float(v)
        except Exception:
            pass
    return None


def _estimate_pot_before_turn(actions: List[Any]) -> Optional[float]:
    for a in actions:
        if _get(a, "street") == "turn":
            v = _get(a, "pot_before") or _get(a, "pot")
            try:
                if v is not None:
                    return float(v)
            except Exception:
                return None
    return None


def _build_sizing(raw_action: str, bet_amount: Optional[float], pot_before: Optional[float]) -> Dict[str, Any]:
    if bet_amount is None or pot_before is None or pot_before <= 0:
        return {"amount": bet_amount, "pot_before": pot_before, "pct_pot": None}
    return {
        "amount": bet_amount,
        "pot_before": pot_before,
        "pct_pot": bet_amount / pot_before,
    }


def _simple_equity_estimate(hero_flop_decision: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    base = 0.50
    if isinstance(hero_flop_decision, dict):
        eq = hero_flop_decision.get("equity_estimate")
        if isinstance(eq, dict) and eq.get("estimated_equity") is not None:
            try:
                base = float(eq["estimated_equity"])
            except Exception:
                pass
    base = 0.50 + (base - 0.50) * 0.85
    base = _clamp(base, 0.05, 0.95)
    return {"estimated_equity": base, "model": "mvp_turn_heuristic"}


def get_turn_action_type(hero_turn_action: Any, faced_bet: bool) -> str:
    act = str(_get(hero_turn_action, "action") or "").lower()
    if act == "check":
        return "check"
    if act == "call":
        return "call_vs_bet" if faced_bet else "call"
    if act == "fold":
        return "fold_vs_bet" if faced_bet else "fold"
    if act == "bet":
        return "bet_vs_check" if not faced_bet else "bet"
    if act in ("raise", "3bet", "4bet"):
        return "raise_vs_bet" if faced_bet else "raise"
    return "unknown"


def get_turn_ev_action(action_type: str, hero_ip: bool, multiway: bool) -> str:
    return f"turn_{action_type}_{'ip' if hero_ip else 'oop'}_{'mw' if multiway else 'hu'}"


def _decision_quality_from_ev(ev_value: float) -> str:
    if ev_value >= 0.05:
        return "good"
    if ev_value > -0.05:
        return "ok"
    if ev_value > -0.30:
        return "bad"
    return "blunder"


def _compute_missed_value_turn_by_category(
    *,
    action_type: str,
    hero_ip: bool,
    multiway: bool,
    flop_category: Optional[str],
    pot_before: Optional[float],
) -> Optional[Dict[str, Any]]:
    if action_type != "check":
        return None
    if not hero_ip or multiway:
        return None
    if flop_category not in STRONG_CATS:
        return None
    if pot_before is None or pot_before <= 0:
        return None

    missed_ev = 0.35 * pot_before

    return {
        "street": "turn",
        "tag": "missed_value_strong_hand_ip",
        "reason": f"Hero checked IP with strong hand ({flop_category}).",
        "pot_before": float(pot_before),
        "missed_value_ev": float(missed_ev),
        "model": "mvp_turn_missed_value_v2",
    }


def evaluate_hero_turn_decision(
    actions: List[Any],
    hero_name: Optional[str],
    hero_position: Optional[str],
    hero_preflop_analysis: Optional[Any],
    hero_flop_decision: Optional[Dict[str, Any]],
    board: Optional[List[str]],
    hero_flop_hand_category: Optional[str] = None,
) -> Optional[Dict[str, Any]]:

    if not hero_name:
        return None

    turn_actions = [a for a in actions if _get(a, "street") == "turn"]
    if not turn_actions:
        return None

    hero_turn_actions = [
        a for a in turn_actions
        if (_get(a, "player_name") == hero_name or _get(a, "player") == hero_name or _get(a, "name") == hero_name)
    ]
    if not hero_turn_actions:
        return None

    first = hero_turn_actions[0]
    raw_action = str(_get(first, "action") or "").lower()

    faced_bet = any(
        str(_get(a, "action") or "").lower() in ("bet", "raise")
        for a in turn_actions
        if a is not first
    )

    action_type = get_turn_action_type(first, faced_bet)

    pot_before = _estimate_pot_before_turn(actions)
    sizing = _build_sizing(raw_action, _parse_bet_amount(first), pot_before)

    players_to_turn = _players_to_turn(actions)
    multiway = _is_multiway(players_to_turn)

    hero_ip = _infer_hero_ip_from_actions_on_street(turn_actions, hero_name)
    if hero_ip is None:
        hero_ip = _is_hero_in_position(hero_position)

    context = {
        "players_to_turn": players_to_turn,
        "multiway": multiway,
        "hero_ip": hero_ip,
        "hero_position": hero_position,
        "preflop_role": _get_preflop_role(hero_preflop_analysis, hero_position),
    }

    equity_estimate = _simple_equity_estimate(hero_flop_decision)
    eq = _safe_float(equity_estimate.get("estimated_equity"))

    ev_action = get_turn_ev_action(action_type, hero_ip, multiway)

    ev_context = generate_context(
        multiway=multiway,
        hero_ip=hero_ip,
        hero_position=str(hero_position or "unknown"),
        villain_position="unknown",
        effective_stack=0.0,
        board_texture="unknown",
    )

    ev_estimate = compute_ev_estimate_v1(
        street="turn",
        action_kind=raw_action,
        pot_before=sizing.get("pot_before"),
        investment=sizing.get("amount"),
        estimated_equity=eq,
        fold_equity=0.0,
        final_pot_if_called=None,
        ev_action=ev_action,
        ev_action_label=ev_action,
        assumptions=generate_assumptions("turn", raw_action, ev_context),
        confidence=0.6,
        context=ev_context,
        alternatives={},
    )

    ev_value = _safe_float(ev_estimate.get("ev_action")) or 0.0

    missed_value = _compute_missed_value_turn_by_category(
        action_type=action_type,
        hero_ip=hero_ip,
        multiway=multiway,
        flop_category=hero_flop_hand_category,
        pot_before=pot_before,
    )

    if isinstance(missed_value, dict):
        ev_estimate["missed_value_ev"] = missed_value["missed_value_ev"]
        ev_estimate["missed_value_tag"] = missed_value["tag"]

    return {
        "action_type": action_type,
        "action_kind": raw_action,
        "sizing": sizing,
        "context": context,
        "hand": {"board_turn": _detect_turn_card(board), "board": board},
        "equity_estimate": equity_estimate,
        "ev_estimate": ev_estimate,
        "missed_value": missed_value,
        "decision_quality": _decision_quality_from_ev(ev_value),
        "quality_comment": f"EV={ev_value:+.4f}",
        "comment": f"Turn {action_type}, IP={hero_ip}, MW={multiway}",
    }
