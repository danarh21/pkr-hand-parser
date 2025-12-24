from __future__ import annotations

from typing import Optional, Dict, Any, List

from .ev_tools import compute_ev_estimate_v1, generate_assumptions, generate_context


def _get(a: Any, key: str, default: Any = None) -> Any:
    """Безопасно достаёт поле из dict или объекта."""
    if isinstance(a, dict):
        return a.get(key, default)
    return getattr(a, key, default)


def _clamp(value: float, min_value: float, max_value: float) -> float:
    if value < min_value:
        return min_value
    if value > max_value:
        return max_value
    return value


def _detect_river_card(board: Optional[List[str]]) -> Optional[str]:
    if not board or len(board) < 5:
        return None
    return board[4]


def _players_to_river(actions: List[Any]) -> int:
    names = set()
    for a in actions:
        if _get(a, "street") == "river":
            pn = _get(a, "player_name") or _get(a, "player") or _get(a, "name")
            if pn:
                names.add(str(pn))
    return max(2, len(names)) if names else 2


def _is_multiway(players_to_river: int) -> bool:
    return players_to_river >= 3


def _is_hero_in_position(hero_position: Optional[str]) -> bool:
    pos = (hero_position or "").upper()
    return pos in ("BTN", "CO", "HJ")


def _parse_bet_amount(action_obj: Any) -> Optional[float]:
    for attr in ("amount", "bet", "size", "value"):
        v = _get(action_obj, attr, None)
        if v is None:
            continue
        try:
            return float(v)
        except Exception:
            continue
    return None


def _estimate_pot_before_river(actions: List[Any]) -> Optional[float]:
    for a in actions:
        if _get(a, "street") == "river":
            v = _get(a, "pot_before", None)
            if v is None:
                v = _get(a, "pot", None)
            if v is not None:
                try:
                    return float(v)
                except Exception:
                    return None
    return None


def _build_sizing(raw_action: str, bet_amount: Optional[float], pot_before: Optional[float]) -> Dict[str, Any]:
    if bet_amount is None or pot_before is None or pot_before <= 0:
        return {"amount": bet_amount, "pot_before": pot_before, "pct_pot": None}
    return {"amount": bet_amount, "pot_before": pot_before, "pct_pot": bet_amount / pot_before}


def _simple_equity_estimate_on_river(hero_turn_decision: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    base = 0.50
    if isinstance(hero_turn_decision, dict):
        eq = hero_turn_decision.get("equity_estimate")
        if isinstance(eq, dict) and eq.get("estimated_equity") is not None:
            try:
                base = float(eq["estimated_equity"])
            except Exception:
                base = 0.50

    base = 0.50 + (base - 0.50) * 0.70
    base = _clamp(base, 0.03, 0.97)

    return {
        "estimated_equity": base,
        "model": "mvp_river_heuristic",
        "notes": "Equity approximation from turn estimate (shrunk toward 0.5).",
    }


def _get_river_action_type(hero_river_action: Any, faced_bet: bool) -> str:
    act = (_get(hero_river_action, "action") or _get(hero_river_action, "action_kind") or "")
    act = str(act).lower()

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


def get_river_ev_action(action_type: str, hero_ip: bool, multiway: bool) -> str:
    ip = "ip" if hero_ip else "oop"
    mw = "mw" if multiway else "hu"
    return f"river_{action_type}_{ip}_{mw}"


def _decision_quality_from_ev(ev_value: float) -> str:
    if ev_value >= 0.05:
        return "good"
    if -0.05 < ev_value < 0.05:
        return "ok"
    if -0.30 < ev_value <= -0.05:
        return "bad"
    return "blunder"


def evaluate_hero_river_decision(
    actions: List[Any],
    hero_name: Optional[str],
    hero_position: Optional[str],
    hero_preflop_analysis: Optional[Any],
    hero_flop_decision: Optional[Dict[str, Any]],
    hero_turn_decision: Optional[Dict[str, Any]],
    board: Optional[List[str]],
) -> Optional[Dict[str, Any]]:

    if not hero_name:
        return None

    river_actions = [a for a in actions if _get(a, "street") == "river"]
    if not river_actions:
        return None

    # ✅ КЛЮЧЕВОЙ ФИКС: hero может быть в player / name
    hero_river_actions = [
        a for a in river_actions
        if (
            _get(a, "player_name") == hero_name
            or _get(a, "player") == hero_name
            or _get(a, "name") == hero_name
        )
    ]
    if not hero_river_actions:
        return None

    first = hero_river_actions[0]
    raw_action = _get(first, "action") or _get(first, "action_kind") or "unknown"
    raw_action = str(raw_action).lower()

    faced_bet = False
    for a in river_actions:
        if a is first:
            break
        act = (_get(a, "action") or _get(a, "action_kind") or "")
        act = str(act).lower()
        if act in ("bet", "raise"):
            faced_bet = True
            break

    action_type = _get_river_action_type(first, faced_bet)

    pot_before = _estimate_pot_before_river(actions)
    bet_amount = _parse_bet_amount(first)
    sizing = _build_sizing(raw_action, bet_amount, pot_before)

    river_card = _detect_river_card(board)
    players_to_river = _players_to_river(actions)
    multiway = _is_multiway(players_to_river)
    hero_ip = _is_hero_in_position(hero_position)

    context = {
        "players_to_river": players_to_river,
        "multiway": multiway,
        "hero_ip": hero_ip,
        "hero_position": hero_position,
        "preflop_role": "unknown" if hero_preflop_analysis is None else "known",
    }

    hand_block = {
        "board_river": river_card,
        "board": board,
        "board_texture": "unknown",
    }

    equity_estimate = _simple_equity_estimate_on_river(hero_turn_decision)

    ev_action = get_river_ev_action(action_type, hero_ip, multiway)

    fold_equity = 0.0
    if action_type in ("bet_vs_check", "raise_vs_bet"):
        fold_equity = 0.30 if (not multiway and hero_ip) else 0.12

    ev_context = generate_context(
        multiway=multiway,
        hero_ip=hero_ip,
        hero_position=str(hero_position or "unknown"),
        villain_position="unknown",
        effective_stack=0.0,
        board_texture="unknown",
    )

    ev_estimate = compute_ev_estimate_v1(
        street="river",
        action_kind=raw_action,
        pot_before=sizing.get("pot_before"),
        investment=sizing.get("amount"),
        estimated_equity=equity_estimate.get("estimated_equity"),
        fold_equity=fold_equity,
        final_pot_if_called=None,
        ev_action_label=ev_action,
        ev_action=ev_action,
        assumptions=generate_assumptions("river", raw_action, ev_context),
        confidence=0.6,
        context=ev_context,
        alternatives={},
    )

    try:
        ev_value = float(ev_estimate.get("ev_action", 0.0))
    except Exception:
        ev_value = 0.0

    decision_quality = _decision_quality_from_ev(ev_value)
    quality_comment = f"EV(action)={ev_value:+.4f} по модели {ev_estimate.get('model', 'v1_baseline')}."
    comment = f"River: {action_type}. IP={hero_ip}. Multiway={multiway}."

    return {
        "action_type": action_type,
        "action_kind": raw_action,
        "sizing": sizing,
        "context": context,
        "hand": hand_block,
        "equity_estimate": equity_estimate,
        "ev_estimate": ev_estimate,
        "missed_value": None,
        "decision_quality": decision_quality,
        "quality_comment": quality_comment,
        "comment": comment,
    }
