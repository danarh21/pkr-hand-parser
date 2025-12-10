from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Dict, Any, Optional
import json
import re

from .equity_engine import estimate_preflop_equity_as_dict
from .decision_engine import evaluate_preflop_decision
from .flop_equity_engine import estimate_flop_equity_simple
from .turn_engine import evaluate_hero_turn_decision

# ---------------------------------------------------------------------
#  МОДЕЛИ ДАННЫХ
# ---------------------------------------------------------------------


@dataclass
class Player:
    seat: int
    name: str
    stack: float
    position: Optional[str] = None  # BTN / SB / BB / UTG / MP / CO


@dataclass
class Action:
    street: str          # preflop / flop / turn / river
    player: str
    action: str          # post_sb / post_bb / bet / raise / call / check / fold / uncalled
    amount: Optional[float] = None

    amount_bb: Optional[float] = None
    pot_before: Optional[float] = None
    pot_after: Optional[float] = None
    pct_pot: Optional[float] = None


@dataclass
class Winner:
    player: str
    amount: float


@dataclass
class ShowdownEntry:
    player: str
    cards: List[str]
    result: Optional[str] = None
    won_amount: Optional[float] = None
    description: Optional[str] = None


@dataclass
class HeroPreflopAnalysis:
    action_type: Optional[str]
    was_first_in: Optional[bool]
    facing_raises: int
    facing_callers: int
    villain_raiser: Optional[str]
    hero_position: Optional[str]
    effective_stack_bb: Optional[float]


@dataclass
class Hand:
    id: int

    hand_id: Optional[str]
    game_type: Optional[str]
    currency: Optional[str]
    small_blind: Optional[float]
    big_blind: Optional[float]
    date: Optional[str]
    time: Optional[str]

    table_name: Optional[str]
    max_players: Optional[int]
    button_seat: Optional[int]

    players: List[Player]
    hero_name: Optional[str]
    hero_cards: List[str]

    hero_position: Optional[str]
    hero_stack_bb: Optional[float]

    hero_preflop_analysis: Optional[HeroPreflopAnalysis]
    hero_preflop_equity: Optional[Dict[str, Any]]
    hero_preflop_decision: Optional[Dict[str, Any]]

      # 🔹 Флоп / терн анализ
    hero_flop_hand_category: Optional[str]          # set / pair / two_pair / ...
    hero_flop_hand_detail: Optional[Dict[str, Any]] # made_hand + pair_kind и т.п.
    hero_flop_decision: Optional[Dict[str, Any]]    # разбор первого решения на флопе
    hero_turn_decision: Optional[Dict[str, Any]]    # разбор первого решения на терне

    actions: List[Action]
    board: List[str]

    pot_preflop: Optional[float]
    pot_flop: Optional[float]
    pot_turn: Optional[float]
    pot_river: Optional[float]

    total_pot: Optional[float]
    rake: Optional[float]
    winners: List[Winner]
    showdown: List[ShowdownEntry]

    raw_text: str


# ---------------------------------------------------------------------
#  ОБЩИЕ ХЕЛПЕРЫ
# ---------------------------------------------------------------------


def parse_amount(raw: str) -> Optional[float]:
    if raw is None:
        return None
    m = re.search(r"[-+]?\d+(?:\.\d+)?", raw)
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def split_into_hands(text: str) -> List[str]:
    lines = text.splitlines()
    hands: List[str] = []
    current: List[str] = []

    for line in lines:
        if line.strip() == "":
            if current:
                hands.append("\n".join(current))
                current = []
        else:
            current.append(line)

    if current:
        hands.append("\n".join(current))

    return hands


def load_and_split(path: str | Path) -> List[str]:
    file_path = Path(path)
    raw_text = file_path.read_text(encoding="utf-8")
    return split_into_hands(raw_text)


# ---------------------------------------------------------------------
#  ПАРСИНГ ЗАГОЛОВКА
# ---------------------------------------------------------------------


def parse_hand_header(hand_text: str):
    hand_id = None
    game_type = None
    currency = None
    sb = None
    bb = None
    date = None
    time = None
    table_name = None
    max_players: Optional[int] = None
    button_seat: Optional[int] = None

    lines = hand_text.splitlines()

    header_line = None
    for line in lines:
        if "Poker Hand #" in line:
            header_line = line.strip()
            break

    if header_line:
        m = re.search(
            r"Poker Hand #(?P<hand_id>\S+):\s*(?P<game_type>.+?)\s*"
            r"\((?P<stakes>[^)]*)\)\s*-\s*"
            r"(?P<date>\d{4}/\d{2}/\d{2})\s+"
            r"(?P<time>\d{2}:\d{2}:\d{2})(?:\s+\S+)?",
            header_line,
        )
        if m:
            hand_id = m.group("hand_id")
            game_type = m.group("game_type").strip()
            stakes = m.group("stakes").strip()
            date = m.group("date")
            time = m.group("time")

            stakes_match = re.search(
                r"(?P<c1>[$€£]?)(?P<sb>[0-9.]+)\s*/\s*(?P<c2>[$€£]?)(?P<bb>[0-9.]+)",
                stakes,
            )
            if stakes_match:
                c1 = stakes_match.group("c1") or stakes_match.group("c2") or "$"
                currency = c1
                sb = parse_amount(stakes_match.group("sb"))
                bb = parse_amount(stakes_match.group("bb"))

    table_line = None
    for line in lines:
        if line.startswith("Table "):
            table_line = line.strip()
            break

    if table_line:
        m2 = re.match(
            r"Table '(.+?)'\s+(\d+)-max Seat #(\d+) is the button",
            table_line,
        )
        if m2:
            table_name = m2.group(1)
            try:
                max_players = int(m2.group(2))
            except ValueError:
                max_players = None
            try:
                button_seat = int(m2.group(3))
            except ValueError:
                button_seat = None

    return hand_id, game_type, currency, sb, bb, date, time, table_name, max_players, button_seat


# ---------------------------------------------------------------------
#  ПАРСИНГ ИГРОКОВ
# ---------------------------------------------------------------------


def parse_players(hand_text: str) -> List[Player]:
    players: List[Player] = []
    pattern = re.compile(
        r"Seat\s+(\d+):\s+(.+?)\s+\(\$([0-9.]+)\s+in chips\)",
        re.IGNORECASE,
    )

    for line in hand_text.splitlines():
        m = pattern.match(line.strip())
        if m:
            seat_str, name, stack_str = m.groups()
            seat = int(seat_str)
            stack = parse_amount(stack_str)
            if stack is None:
                continue
            players.append(Player(seat=seat, name=name.strip(), stack=stack, position=None))

    return players


# ---------------------------------------------------------------------
#  ПОЗИЦИИ
# ---------------------------------------------------------------------


def assign_positions(
    players: List[Player],
    button_seat: Optional[int],
    max_players: Optional[int],
) -> List[Player]:
    if not players or button_seat is None:
        return players

    seat_to_player: Dict[int, Player] = {p.seat: p for p in players}
    seats_sorted = sorted(seat_to_player.keys())

    if button_seat not in seat_to_player:
        return players

    ordered_seats: List[int] = []
    current = button_seat
    ordered_seats.append(current)

    while len(ordered_seats) < len(seat_to_player):
        bigger = [s for s in seats_sorted if s > current]
        nxt = bigger[0] if bigger else seats_sorted[0]
        if nxt in ordered_seats:
            current = nxt
            continue
        ordered_seats.append(nxt)
        current = nxt

    n = len(ordered_seats)
    if n == 1:
        pos_names = ["BTN"]
    elif n == 2:
        pos_names = ["BTN", "BB"]
    elif n == 3:
        pos_names = ["BTN", "SB", "BB"]
    elif n == 4:
        pos_names = ["BTN", "SB", "BB", "UTG"]
    elif n == 5:
        pos_names = ["BTN", "SB", "BB", "UTG", "MP"]
    else:
        pos_names = ["BTN", "SB", "BB", "UTG", "MP", "CO"]

    pos_names = pos_names[:n]

    for seat, pos in zip(ordered_seats, pos_names):
        seat_to_player[seat].position = pos

    return [seat_to_player[p.seat] for p in players]


# ---------------------------------------------------------------------
#  HERO
# ---------------------------------------------------------------------


def parse_hero(hand_text: str) -> tuple[Optional[str], List[str]]:
    hero_name: Optional[str] = None
    hero_cards: List[str] = []

    m = re.search(
        r"Dealt to (\S+) \[([2-9TJQKA][cdhs]) ([2-9TJQKA][cdhs])\]",
        hand_text,
    )
    if m:
        hero_name = m.group(1)
        hero_cards = [m.group(2), m.group(3)]
        return hero_name, hero_cards

    return hero_name, hero_cards


# ---------------------------------------------------------------------
#  ДЕЙСТВИЯ
# ---------------------------------------------------------------------


def parse_actions(hand_text: str) -> List[Action]:
    actions: List[Action] = []

    street = "preflop"
    lines = hand_text.splitlines()

    for line in lines:
        line = line.rstrip("\n")

        if line.startswith("*** "):
            up = line.upper()
            if "HOLE CARDS" in up or "PREFLOP" in up:
                street = "preflop"
            elif "FLOP" in up:
                street = "flop"
            elif "TURN" in up:
                street = "turn"
            elif "RIVER" in up:
                street = "river"
            continue

        m = re.match(r"Uncalled bet \(\$([0-9.]+)\) returned to (.+)", line)
        if m:
            amount = parse_amount(m.group(1))
            player = m.group(2).strip()
            actions.append(Action(street=street, player=player, action="uncalled", amount=amount))
            continue

        m_prefix = re.match(r"([^:]+):\s+(.*)", line)
        if not m_prefix:
            continue

        player = m_prefix.group(1).strip()
        rest = m_prefix.group(2).strip()

        m = re.match(r"posts small blind \$([0-9.]+)", rest, re.IGNORECASE)
        if m:
            amount = parse_amount(m.group(1))
            actions.append(Action(street=street, player=player, action="post_sb", amount=amount))
            continue

        m = re.match(r"posts big blind \$([0-9.]+)", rest, re.IGNORECASE)
        if m:
            amount = parse_amount(m.group(1))
            actions.append(Action(street=street, player=player, action="post_bb", amount=amount))
            continue

        m = re.match(r"raises \$([0-9.]+) to \$([0-9.]+)", rest, re.IGNORECASE)
        if m:
            amount_to = parse_amount(m.group(2))
            actions.append(Action(street=street, player=player, action="raise", amount=amount_to))
            continue

        m = re.match(r"bets \$([0-9.]+)", rest, re.IGNORECASE)
        if m:
            amount = parse_amount(m.group(1))
            actions.append(Action(street=street, player=player, action="bet", amount=amount))
            continue

        m = re.match(r"calls \$([0-9.]+)", rest, re.IGNORECASE)
        if m:
            amount = parse_amount(m.group(1))
            actions.append(Action(street=street, player=player, action="call", amount=amount))
            continue

        if re.match(r"checks", rest, re.IGNORECASE):
            actions.append(Action(street=street, player=player, action="check", amount=None))
            continue

        if re.match(r"folds", rest, re.IGNORECASE):
            actions.append(Action(street=street, player=player, action="fold", amount=None))
            continue

    return actions


# ---------------------------------------------------------------------
#  БОРД
# ---------------------------------------------------------------------


def parse_board(hand_text: str) -> List[str]:
    board: List[str] = []

    flop = re.search(r"\*\*\* FLOP \*\*\* \[(.*?)\]", hand_text, re.IGNORECASE)
    if flop:
        cards = flop.group(1).split()
        board += cards[:3]

    turn = re.search(r"\*\*\* TURN \*\*\*.*?\[(.*?)\]", hand_text, re.IGNORECASE)
    if turn:
        cards = turn.group(1).split()
        if cards:
            board.append(cards[-1])

    river = re.search(r"\*\*\* RIVER \*\*\*.*?\[(.*?)\]", hand_text, re.IGNORECASE)
    if river:
        cards = river.group(1).split()
        if cards:
            board.append(cards[-1])

    if not board:
        m = re.search(r"Board \[([2-9TJQKAcdhs\s]+)\]", hand_text)
        if m:
            board = m.group(1).split()

    return board


# ---------------------------------------------------------------------
#  TOTAL POT / RAKE
# ---------------------------------------------------------------------


def parse_total_pot_and_rake(hand_text: str) -> tuple[Optional[float], Optional[float]]:
    total_pot = None
    rake = None

    m = re.search(
        r"Total pot \$([0-9.]+)\s*\|\s*Rake \$([0-9.]+)",
        hand_text,
        re.IGNORECASE,
    )
    if m:
        total_pot = parse_amount(m.group(1))
        rake = parse_amount(m.group(2))
        return total_pot, rake

    m2 = re.search(r"Total pot \$([0-9.]+)", hand_text, re.IGNORECASE)
    if m2:
        total_pot = parse_amount(m2.group(1))

    m3 = re.search(r"Rake \$([0-9.]+)", hand_text, re.IGNORECASE)
    if m3:
        rake = parse_amount(m3.group(1))

    return total_pot, rake


# ---------------------------------------------------------------------
#  ПОБЕДИТЕЛИ
# ---------------------------------------------------------------------


def parse_winners(hand_text: str) -> List[Winner]:
    winners: List[Winner] = []

    pattern_collected_body = re.compile(
        r"^(.+?) collected \$([0-9.]+) from pot",
        re.IGNORECASE | re.MULTILINE,
    )

    pattern_won_summary = re.compile(
        r"^Seat \d+: (.+?) .* won \(\$([0-9.]+)\)",
        re.IGNORECASE | re.MULTILINE,
    )

    pattern_collected_summary = re.compile(
        r"^Seat \d+: (.+?) .* collected \(\$([0-9.]+)\)",
        re.IGNORECASE | re.MULTILINE,
    )

    for m in pattern_collected_body.finditer(hand_text):
        name = m.group(1).strip()
        amount = parse_amount(m.group(2))
        if amount is not None:
            winners.append(Winner(player=name, amount=amount))

    for m in pattern_won_summary.finditer(hand_text):
        name = m.group(1).strip()
        amount = parse_amount(m.group(2))
        if amount is not None:
            winners.append(Winner(player=name, amount=amount))

    for m in pattern_collected_summary.finditer(hand_text):
        name = m.group(1).strip()
        amount = parse_amount(m.group(2))
        if amount is not None:
            winners.append(Winner(player=name, amount=amount))

    unique: Dict[tuple[str, float], Winner] = {}
    for w in winners:
        key = (w.player, w.amount)
        unique[key] = w

    return list(unique.values())


# ---------------------------------------------------------------------
#  ШОУДАУН
# ---------------------------------------------------------------------


def parse_showdown(hand_text: str) -> List[ShowdownEntry]:
    result: List[ShowdownEntry] = []

    pattern_shows = re.compile(
        r"^(.+?): shows \[([2-9TJQKA][cdhs]) ([2-9TJQKA][cdhs])\](?: \((.+)\))?",
        re.IGNORECASE | re.MULTILINE,
    )

    pattern_showed_seat = re.compile(
        r"^Seat \d+: (.+?) .*showed \[([2-9TJQKA][cdhs]) ([2-9TJQKA][cdhs])\]"
        r"(?: and (won|lost)(?: \(\$([0-9.]+)\))?)?(?: with (.+))?",
        re.IGNORECASE | re.MULTILINE,
    )

    for m in pattern_shows.finditer(hand_text):
        player = m.group(1).strip()
        cards = [m.group(2), m.group(3)]
        desc = m.group(4)
        result.append(
            ShowdownEntry(
                player=player,
                cards=cards,
                result=None,
                won_amount=None,
                description=desc.strip() if desc else None,
            )
        )

    for m in pattern_showed_seat.finditer(hand_text):
        player = m.group(1).strip()
        cards = [m.group(2), m.group(3)]
        res = m.group(4)
        won_amount = parse_amount(m.group(5)) if m.group(5) else None
        desc = m.group(6)
        result.append(
            ShowdownEntry(
                player=player,
                cards=cards,
                result=res.lower() if res else None,
                won_amount=won_amount,
                description=desc.strip() if desc else None,
            )
        )

    unique: Dict[tuple[str, str, str], ShowdownEntry] = {}
    for e in result:
        key = (e.player, e.cards[0], e.cards[1])
        unique[key] = e

    return list(unique.values())


# ---------------------------------------------------------------------
#  АННОТАЦИЯ ДЕЙСТВИЙ ПОТОМ
# ---------------------------------------------------------------------


def annotate_actions_with_pot_and_bb(
    actions: List[Action],
    big_blind: Optional[float],
) -> Dict[str, Optional[float]]:
    pots: Dict[str, Optional[float]] = {
        "preflop": None,
        "flop": None,
        "turn": None,
        "river": None,
    }

    if not actions:
        return pots

    current_pot = 0.0
    current_street = actions[0].street
    committed: Dict[str, float] = {}

    def fix_street(street_name: str, pot_value: float):
        if street_name == "preflop":
            pots["preflop"] = pot_value
        elif street_name == "flop":
            pots["flop"] = pot_value
        elif street_name == "turn":
            pots["turn"] = pot_value
        elif street_name == "river":
            pots["river"] = pot_value

    for act in actions:
        if act.street != current_street:
            fix_street(current_street, current_pot)
            current_street = act.street
            committed = {}

        act.pot_before = current_pot

        if act.action in ("post_sb", "post_bb", "bet", "call"):
            if act.amount is not None:
                current_pot += act.amount
                committed[act.player] = committed.get(act.player, 0.0) + act.amount

        elif act.action == "raise":
            if act.amount is not None:
                prev = committed.get(act.player, 0.0)
                delta = act.amount - prev
                if delta < 0:
                    delta = 0.0
                current_pot += delta
                committed[act.player] = act.amount

        elif act.action == "uncalled":
            if act.amount is not None:
                current_pot -= act.amount

        act.pot_after = current_pot

        if big_blind and act.amount is not None and big_blind > 0:
            act.amount_bb = act.amount / big_blind
        else:
            act.amount_bb = None

        if act.amount is not None and act.pot_before and act.pot_before > 0:
            act.pct_pot = act.amount / act.pot_before
        else:
            act.pct_pot = None

    fix_street(current_street, current_pot)

    return pots


# ---------------------------------------------------------------------
#  АНАЛИЗ ПРЕФЛОПА ГЕРОЯ
# ---------------------------------------------------------------------


def compute_effective_stack_bb(
    players: List[Player],
    hero_name: Optional[str],
    big_blind: Optional[float],
) -> Optional[float]:
    if not hero_name or not big_blind or big_blind <= 0:
        return None

    hero_player = None
    for p in players:
        if p.name == hero_name:
            hero_player = p
            break

    if not hero_player:
        return None

    hero_stack_bb = hero_player.stack / big_blind
    if hero_stack_bb <= 0:
        return None

    best_eff = 0.0
    for p in players:
        if p.name == hero_name:
            continue
        opp_stack_bb = p.stack / big_blind
        eff = min(hero_stack_bb, opp_stack_bb)
        if eff > best_eff:
            best_eff = eff

    if best_eff == 0.0:
        return hero_stack_bb

    return best_eff


def compute_hero_preflop_analysis(
    actions: List[Action],
    players: List[Player],
    hero_name: Optional[str],
    hero_position: Optional[str],
    effective_stack_bb: Optional[float],
) -> Optional[HeroPreflopAnalysis]:
    if not hero_name:
        return None

    preflop_actions = [a for a in actions if a.street == "preflop"]
    if not preflop_actions:
        return HeroPreflopAnalysis(
            action_type=None,
            was_first_in=None,
            facing_raises=0,
            facing_callers=0,
            villain_raiser=None,
            hero_position=hero_position,
            effective_stack_bb=effective_stack_bb,
        )

    hero_preflop_actions = [
        a for a in preflop_actions
        if a.player == hero_name and a.action not in ("uncalled", "post_sb", "post_bb")
    ]

    if not hero_preflop_actions:
        return HeroPreflopAnalysis(
            action_type=None,
            was_first_in=None,
            facing_raises=0,
            facing_callers=0,
            villain_raiser=None,
            hero_position=hero_position,
            effective_stack_bb=effective_stack_bb,
        )

    hero_first = hero_preflop_actions[0]
    idx_hero = preflop_actions.index(hero_first)
    prior = preflop_actions[:idx_hero]

    prior_voluntary = [a for a in prior if a.action in ("bet", "raise", "call")]
    was_first_in = len(prior_voluntary) == 0

    prior_raises = [a for a in prior if a.action == "raise"]
    facing_raises = len(prior_raises)
    villain_raiser = prior_raises[-1].player if prior_raises else None

    if prior_raises:
        last_raise_idx = max(i for i, a in enumerate(prior) if a.action == "raise")
        facing_callers = sum(
            1
            for i, a in enumerate(prior)
            if i > last_raise_idx and a.action == "call"
        )
    else:
        facing_callers = sum(1 for a in prior if a.action == "call")

    act_type = "unknown"

    if hero_first.action == "fold":
        act_type = "fold_preflop"

    elif hero_first.action == "call":
        if facing_raises == 0:
            if facing_callers == 0:
                act_type = "open_limp"
            else:
                act_type = "overlimp"
        else:
            if facing_raises == 1:
                act_type = "call_vs_raise"
            else:
                act_type = "call_vs_3bet_plus"

    elif hero_first.action == "raise":
        if facing_raises == 0:
            if facing_callers == 0:
                act_type = "open_raise"
            else:
                act_type = "iso_raise"
        elif facing_raises == 1:
            act_type = "3bet"
        elif facing_raises == 2:
            act_type = "4bet"
        else:
            act_type = "5bet_plus"

    return HeroPreflopAnalysis(
        action_type=act_type,
        was_first_in=was_first_in,
        facing_raises=facing_raises,
        facing_callers=facing_callers,
        villain_raiser=villain_raiser,
        hero_position=hero_position,
        effective_stack_bb=effective_stack_bb,
    )


def compute_hero_preflop_decision(
    actions: List[Action],
    hero_name: Optional[str],
    hero_preflop_analysis: Optional[HeroPreflopAnalysis],
    hero_preflop_equity: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    if not hero_name or not hero_preflop_analysis or not hero_preflop_equity:
        return None

    preflop_actions = [a for a in actions if a.street == "preflop"]
    if not preflop_actions:
        return None

    hero_preflop_actions = [
        a for a in preflop_actions
        if a.player == hero_name and a.action not in ("uncalled", "post_sb", "post_bb")
    ]
    if not hero_preflop_actions:
        return None

    hero_first = hero_preflop_actions[0]

    pot_before = hero_first.pot_before
    investment = hero_first.amount

    action_type = hero_preflop_analysis.action_type

    if hero_first.action in ("call", "raise", "fold", "check", "bet"):
        action_kind = hero_first.action
    else:
        action_kind = "other"

    estimated_equity = hero_preflop_equity.get("estimated_equity_vs_unknown")
    mos_min_position = hero_preflop_equity.get("mos_min_position")
    hand_key = hero_preflop_equity.get("hand_key")
    hero_position = hero_preflop_analysis.hero_position
    was_first_in = hero_preflop_analysis.was_first_in
    facing_raises = hero_preflop_analysis.facing_raises
    effective_stack_bb = hero_preflop_analysis.effective_stack_bb

    # Базовая оценка первого решения на префлопе
    base_decision = evaluate_preflop_decision(
        action_type=action_type,
        action_kind=action_kind,
        pot_before=pot_before,
        investment=investment,
        estimated_equity=estimated_equity,
        hero_position=hero_position,
        mos_min_position=mos_min_position,
        hand_key=hand_key,
        was_first_in=was_first_in,
        facing_raises=facing_raises,
        effective_stack_bb=effective_stack_bb,
    )

    # Дополнительный разбор: что произошло ПОСЛЕ первого действия героя
    followup = compute_hero_preflop_followup(
        actions=actions,
        hero_name=hero_name,
        hero_preflop_equity=hero_preflop_equity,
    )
    if followup is not None:
        base_decision["followup_vs_aggression"] = followup

    return base_decision


def compute_hero_preflop_followup(
    actions: List[Action],
    hero_name: Optional[str],
    hero_preflop_equity: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """
    Анализ продолжения линии на префлопе:
    пример — герой 3-бетит, получает 4-бет и ФОЛДИТ.

    Возвращает dict с ключами:
      - action_type: 'fold_vs_aggression' / 'fold_vs_3bet_plus'
      - action_kind: 'fold'
      - math: { pot_before, to_call, final_pot_if_call, pot_odds, required_equity,
                estimated_equity, ev_simple }
      - villain: { name }
      - comment, quality, quality_comment
    """
    if not hero_name or not hero_preflop_equity:
        return None

    preflop_actions = [a for a in actions if a.street == "preflop"]
    if not preflop_actions:
        return None

    # Все добровольные действия героя на префлопе
    hero_preflop_actions = [
        a for a in preflop_actions
        if a.player == hero_name and a.action not in ("uncalled", "post_sb", "post_bb")
    ]
    # Нас интересуют только случаи, где герой делал КАК МИНИМУМ два действия
    # (например: 3-бет -> фолд vs 4-бет).
    if len(hero_preflop_actions) < 2:
        return None

    hero_last = hero_preflop_actions[-1]
    if hero_last.action != "fold":
        # follow-up анализ пока делаем только для фолдов
        return None

    # Индекс последнего действия героя в общем списке префлоп-экшенов
    try:
        idx_last = preflop_actions.index(hero_last)
    except ValueError:
        return None

    prior = preflop_actions[:idx_last]

    # Ищем последнее агрессивное действие соперника до фолда героя (бет/рейз)
    last_agg_idx = None
    last_agg = None
    for i, a in enumerate(prior):
        if a.action in ("bet", "raise"):
            last_agg_idx = i
            last_agg = a

    if last_agg is None:
        # Герой сфолдил без явной агрессии перед этим — неинтересно.
        return None

    villain_name = last_agg.player

    # Считаем, сколько каждый игрок уже вложил в банк к моменту фолда героя
    contributions: Dict[str, float] = {}
    for i, a in enumerate(prior):
        if a.amount is None:
            continue
        contributions[a.player] = contributions.get(a.player, 0.0) + a.amount

    hero_invested = contributions.get(hero_name, 0.0)
    villain_invested = contributions.get(villain_name, 0.0)

    # Сколько нужно было доплатить герою, чтобы уравнять ставку соперника.
    # Это приближение, но для наших целей (оценка EV фолда) достаточно точное.
    to_call = max(villain_invested - hero_invested, 0.0)

    pot_before = hero_last.pot_before
    if pot_before is None:
        return None

    final_pot_if_call = pot_before + to_call if to_call > 0 else pot_before
    pot_odds = None
    required_equity = None
    if to_call > 0 and final_pot_if_call > 0:
        pot_odds = to_call / final_pot_if_call
        required_equity = pot_odds

    estimated_equity = hero_preflop_equity.get("estimated_equity_vs_unknown")
    ev_simple = None
    if estimated_equity is not None and to_call > 0 and final_pot_if_call > 0:
        # Очень упрощённая модель EV:
        # EV(call) = equity * final_pot_if_call - to_call
        ev_simple = estimated_equity * final_pot_if_call - to_call

    # Классифицируем тип ситуации
    # (fold после уже вложенного рейза, например 3-бет/4-бет-пот).
    raises_before_hero = [a for a in prior if a.action == "raise"]
    if len(raises_before_hero) >= 2:
        action_type = "fold_vs_3bet_plus"
    else:
        action_type = "fold_vs_aggression"

    action_kind = "fold"

    # Оценка качества решения по разнице между оценочной equity и требуемой equity
    decision_quality = "unknown"
    quality_comment = "Не удалось точно оценить решение: не хватает данных о банке или ставках."

    if required_equity is not None and estimated_equity is not None:
        edge = estimated_equity - required_equity
        if edge <= -0.05:
            decision_quality = "good"
            quality_comment = (
                "По пот-оддсам кол выглядел бы убыточным, твоя оценочная equity "
                "ниже требуемой. Фолд против дополнительной агрессии выглядит аккуратным решением."
            )
        elif -0.05 < edge < 0.05:
            decision_quality = "close"
            quality_comment = (
                "Спот пограничный: оценочная equity примерно соответствует требуемой. "
                "Фолд — консервативный, но защитимый выбор."
            )
        else:
            decision_quality = "risky"
            quality_comment = (
                "По голой equity тебя, вероятно, устраивал бы кол/ол-ин против этого повышения. "
                "Фолд может быть излишне тайтовым (возможно, недобор EV)."
            )

    comment_parts = []
    comment_parts.append(
        f"После уже вложенных денег на префлопе ты получил(а) дополнительную агрессию от {villain_name} "
        f"и выбрал(а) фолд."
    )
    if pot_odds is not None and required_equity is not None and estimated_equity is not None:
        comment_parts.append(
            f" Пот-оддсы требуют около {required_equity:.2f} equity, твоя оценочная equity ≈ {estimated_equity:.2f}."
        )
    if ev_simple is not None:
        comment_parts.append(
            f" В простой модели EV (без учёта позиций и реализуемости) разница EV(call−fold) ≈ {ev_simple:.3f}."
        )

    comment = " ".join(comment_parts)

    return {
        "action_type": action_type,
        "action_kind": action_kind,
        "villain": {
            "name": villain_name,
        },
        "math": {
            "pot_before": pot_before,
            "to_call": to_call,
            "final_pot_if_call": final_pot_if_call,
            "pot_odds": pot_odds,
            "required_equity": required_equity,
            "estimated_equity": estimated_equity,
            "ev_simple": ev_simple,
            "model": "preflop_followup_model",
        },
        "decision_quality": decision_quality,
        "quality_comment": quality_comment,
        "comment": comment,
    }

# ---------------------------------------------------------------------
#  АНАЛИЗ РУКИ ГЕРОЯ НА ФЛОПЕ (категория + тип пары)
# ---------------------------------------------------------------------


def _card_rank(card: str) -> int:
    """Вернёт числовой ранг карты: 2–14 (A = 14)."""
    rank_char = card[0]
    if rank_char.isdigit():
        return int(rank_char)
    mapping = {
        "T": 10,
        "J": 11,
        "Q": 12,
        "K": 13,
        "A": 14,
    }
    return mapping.get(rank_char.upper(), 0)


def _card_suit(card: str) -> str:
    """Вернёт масть карты: c/d/h/s."""
    return card[1].lower()


def evaluate_flop_hand_category(hero_cards: List[str], board: List[str]) -> Optional[str]:
    """
    Грубая классификация силы руки героя НА ФЛОПЕ:
    high_card / pair / two_pair / set / straight / flush / full_house / quads / straight_flush.

    ВАЖНО: используем только флоп (первые 3 карты борда), даже если в hand_history есть turn/river.
    """
    if len(hero_cards) != 2 or len(board) < 3:
        return None

    flop_cards = board[:3]
    cards = hero_cards + flop_cards

    if len(cards) != 5:
        return None

    ranks = [_card_rank(c) for c in cards]
    suits = [_card_suit(c) for c in cards]

    # Проверка флеша / стрит-флеша
    suit_counts: Dict[str, int] = {}
    for s in suits:
        suit_counts[s] = suit_counts.get(s, 0) + 1
    is_flush = any(cnt == 5 for cnt in suit_counts.values())

    # Проверка стрита
    unique_ranks = sorted(set(ranks))
    is_straight = False

    if len(unique_ranks) >= 5:
        # Обычный стрит
        if unique_ranks[-1] - unique_ranks[0] == 4 and len(unique_ranks) == 5:
            is_straight = True

        # Вариант колёсика A2345
        if set(unique_ranks) == {14, 2, 3, 4, 5}:
            is_straight = True

    # Подсчёт совпадений по рангам
    rank_counts: Dict[int, int] = {}
    for r in ranks:
        rank_counts[r] = rank_counts.get(r, 0) + 1

    counts = sorted(rank_counts.values(), reverse=True)

    if is_flush and is_straight:
        return "straight_flush"

    if 4 in counts:
        return "quads"

    if 3 in counts and 2 in counts:
        return "full_house"

    if is_flush:
        return "flush"

    if is_straight:
        return "straight"

    if 3 in counts:
        return "set"

    if counts.count(2) >= 2:
        return "two_pair"

    if 2 in counts:
        return "pair"

    return "high_card"


def compute_hero_flop_detail(
    hero_cards: List[str],
    board: List[str],
    hero_flop_hand_category: Optional[str],
) -> Optional[Dict[str, Any]]:
    """
    Детализация флопа для героя.
    Пока делаем минимально полезный набор:
      - made_hand: совпадает с hero_flop_hand_category
      - pair_kind: top_pair / overpair / underpair / middle_pair / bottom_pair / board_pair / None
    """
    if len(hero_cards) != 2 or len(board) < 3 or not hero_flop_hand_category:
        return None

    detail: Dict[str, Any] = {
        "made_hand": hero_flop_hand_category,
        "pair_kind": None,
    }

    flop_cards = board[:3]
    cards = hero_cards + flop_cards

    # Если это не просто "pair", pair_kind не нужен
    if hero_flop_hand_category != "pair":
        return detail

    hero_ranks = [_card_rank(c) for c in hero_cards]
    board_ranks = [_card_rank(c) for c in flop_cards]
    all_ranks = hero_ranks + board_ranks

    rank_counts: Dict[int, int] = {}
    for r in all_ranks:
        rank_counts[r] = rank_counts.get(r, 0) + 1

    # Ищем ранг, который образует пару
    pair_ranks = [r for r, cnt in rank_counts.items() if cnt == 2]
    if not pair_ranks:
        # На всякий случай: если вдруг по какой-то причине пара не найдена
        return detail

    # Если пар несколько (редко, но теоретически возможно), выбираем старшую
    pair_rank = max(pair_ranks)

    top_board = max(board_ranks)
    bottom_board = min(board_ranks)

    # Случай: пара только на доске (герой не участвует в паре)
    if pair_rank not in hero_ranks:
        detail["pair_kind"] = "board_pair"
        return detail

    # Случай: карманная пара героя (оба тайтовых ранга у героя, на борде нет такого ранга)
    if pair_rank in hero_ranks and pair_rank not in board_ranks:
        if pair_rank > top_board:
            detail["pair_kind"] = "overpair"
        elif pair_rank < bottom_board:
            detail["pair_kind"] = "underpair"
        else:
            detail["pair_kind"] = "middle_pair"
        return detail

    # Случай: пара частично на доске, частично у героя (классические top/mid/bottom pair)
    if pair_rank == top_board:
        detail["pair_kind"] = "top_pair"
    elif pair_rank == bottom_board:
        detail["pair_kind"] = "bottom_pair"
    else:
        detail["pair_kind"] = "middle_pair"

    return detail


# ---------------------------------------------------------------------
#  РАЗБОР РЕШЕНИЯ ГЕРОЯ НА ФЛОПЕ
# ---------------------------------------------------------------------


def _estimate_flop_strength_score(
    category: Optional[str],
    pair_kind: Optional[str],
) -> Optional[float]:
    """
    Грубый "strength_score" от 0 до 1 на флопе.
    Это не точное эквити, а относительная сила комбинации.
    """
    if category is None:
        return None

    if category == "straight_flush":
        return 0.98
    if category == "quads":
        return 0.95
    if category == "full_house":
        return 0.92
    if category == "flush":
        return 0.86
    if category == "straight":
        return 0.82
    if category == "set":
        return 0.78
    if category == "two_pair":
        return 0.72
    if category == "pair":
        if pair_kind == "overpair":
            return 0.75
        if pair_kind == "top_pair":
            return 0.70
        if pair_kind == "middle_pair":
            return 0.55
        if pair_kind == "bottom_pair":
            return 0.50
        if pair_kind == "board_pair":
            return 0.35
        return 0.50
    if category == "high_card":
        return 0.20

    return 0.50


def compute_hero_flop_decision(
    actions: List[Action],
    hero_name: Optional[str],
    hero_position: Optional[str],
    hero_preflop_analysis: Optional[HeroPreflopAnalysis],
    hero_flop_hand_category: Optional[str],
    hero_flop_hand_detail: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """
    Разбор ПЕРВОГО решения героя на флопе.

    Возвращает словарь:
      - action_type: логическая категория (cbet / bet_vs_check / call_vs_bet / raise_vs_bet / check / fold_vs_bet)
      - action_kind: реальное действие (bet/call/check/raise/fold)
      - sizing: { amount, pot_before, pct_pot }
      - context: { players_to_flop, multiway, hero_ip, hero_position, preflop_role }
      - hand: { category, pair_kind, strength_score }
      - equity_estimate: { estimated_equity, model, explanation }
      - decision_quality: оценка качества (good / ok / risky / bad / unknown)
      - quality_comment: текстовое объяснение оценки
      - comment: общий краткий комментарий по споту
    """
    if not hero_name:
        return None

    flop_actions = [a for a in actions if a.street == "flop"]
    if not flop_actions:
        return None

    hero_flop_actions = [
        a for a in flop_actions
        if a.player == hero_name and a.action not in ("uncalled",)
    ]
    if not hero_flop_actions:
        return None

    first = hero_flop_actions[0]
    idx_first = flop_actions.index(first)
    prior = flop_actions[:idx_first]

    facing_bet = any(a.action in ("bet", "raise") for a in prior)

    # Определяем роль префлоп
    preflop_role = "unknown"
    if hero_preflop_analysis:
        atype = hero_preflop_analysis.action_type
        if atype in ("open_raise", "iso_raise", "3bet", "4bet", "5bet_plus"):
            preflop_role = "aggressor"
        elif atype in ("call_vs_raise", "call_vs_3bet_plus", "open_limp", "overlimp"):
            preflop_role = "caller"
        elif atype == "fold_preflop":
            preflop_role = "folder"
        elif atype is None and hero_position == "BB":
            preflop_role = "checked_bb"

    # Определяем action_type на флопе
    if first.action == "bet":
        # если герой был префлоп-агрессором и до него никто не ставил
        if preflop_role == "aggressor" and not facing_bet:
            action_type = "cbet"
        else:
            action_type = "bet_vs_check"
    elif first.action == "check":
        action_type = "check"
    elif first.action == "call":
        if facing_bet:
            action_type = "call_vs_bet"
        else:
            action_type = "call"
    elif first.action == "raise":
        if facing_bet:
            action_type = "raise_vs_bet"
        else:
            action_type = "raise"
    elif first.action == "fold":
        if facing_bet:
            action_type = "fold_vs_bet"
        else:
            action_type = "fold"
    else:
        action_type = first.action

    # Сколько игроков дошло до флопа
    players_to_flop = len({a.player for a in flop_actions})

    # IP / OOP на флопе: если герой ходит последним среди остальных, считаем IP
    last_other_idx = -1
    for i, a in enumerate(flop_actions):
        if a.player != hero_name:
            last_other_idx = i
    hero_ip = idx_first > last_other_idx if last_other_idx >= 0 else True

    pair_kind = None
    if hero_flop_hand_detail:
        pair_kind = hero_flop_hand_detail.get("pair_kind")

    strength_score = _estimate_flop_strength_score(
        category=hero_flop_hand_category,
        pair_kind=pair_kind,
    )

    sizing = {
        "amount": first.amount,
        "pot_before": first.pot_before,
        "pct_pot": first.pct_pot,
    }

    context = {
        "players_to_flop": players_to_flop,
        "multiway": players_to_flop > 2,
        "hero_ip": hero_ip,
        "hero_position": hero_position,
        "preflop_role": preflop_role,
    }

    hand_info = {
        "category": hero_flop_hand_category,
        "pair_kind": pair_kind,
        "strength_score": strength_score,
    }

    # -------------------------------
    # ОЦЕНКА EQUITY НА ФЛОПЕ
    # -------------------------------
    equity_estimate = estimate_flop_equity_simple(
        category=hero_flop_hand_category,
        pair_kind=pair_kind,
        strength_score=strength_score,
        multiway=context["multiway"],
        hero_ip=context["hero_ip"],
        preflop_role=context["preflop_role"],
    )

    # -------------------------------
    # ОЦЕНКА КАЧЕСТВА РЕШЕНИЯ НА ФЛОПЕ
    # -------------------------------
    decision_quality = "unknown"
    quality_comment = "Не удалось оценить качество решения на флопе: не хватает данных по силе руки или структуре спота."

    if strength_score is not None and hero_flop_hand_category is not None:
        q = "unknown"
        reason = ""

        multiway = context["multiway"]
        ip = context["hero_ip"]

        # Вспомогательные флаги
        very_strong = strength_score >= 0.75     # set+, сильная оверпара/стрит/флеш
        strong = strength_score >= 0.65          # top pair хорошего кикера, оверпара
        medium = 0.45 <= strength_score < 0.65   # средние пары / две пары на сложных досках
        weak = strength_score <= 0.35            # air / board_pair / совсем слабое SDV

        if action_type in ("cbet", "bet_vs_check"):
            # Велью-бет сильной руки
            if very_strong or strong:
                q = "good"
                reason = "Сильная рука и ставка на флопе выглядит стандартным велью-бетом."
            elif medium:
                q = "ok"
                reason = "Ставка с рукой средней силы. В целом нормально, но сильно зависит от текстуры и диапазонов."
            else:
                # Блефовая ставка
                if not multiway and ip:
                    q = "ok"
                    reason = "Блефовая ставка на флопе в хедз-ап поте в позиции — стандартный приём."
                else:
                    q = "risky"
                    reason = "Блефовая ставка на флопе в мультипоте или без позиции выглядит рискованно."

        elif action_type == "check":
            if very_strong and not multiway and ip:
                q = "risky"
                reason = "Чек с очень сильной рукой в хедз-ап поте в позиции может недобрать велью."
            elif weak:
                q = "good"
                if ip:
                    reason = "Чек с очень слабой рукой в позиции — стандартная линия: ты контролируешь банк и избегaешь минусовых блефов."
                else:
                    reason = "Чек с очень слабой рукой без позиции — оптимальное решение: ты минимизируешь потери и не раздуваешь банк с air."
            else:
                q = "ok"
                if ip:
                    reason = "Чек с рукой средней/достаточной силы на флопе допустим, особенно в мультипоте или на сложных бордах."
                else:
                    reason = "Чек с рукой средней силы на флопе допустим, особенно вне позиции или в мультипоте."

        elif action_type in ("call_vs_bet", "call"):
            if strong or very_strong:
                q = "good"
                reason = "Колл со сильной рукой против ставки на флопе выглядит разумным розыгрышем."
            elif weak:
                q = "risky"
                reason = "Колл со слабой рукой без хороших дро может быть минусовым решением."
            else:
                q = "ok"
                reason = "Колл с рукой средней силы выглядит нормальным, особенно против стандартного сайзинга."

        elif action_type in ("raise_vs_bet", "raise"):
            if very_strong:
                q = "good"
                reason = "Рейз с очень сильной рукой на флопе — стандартный велью-розыгрыш."
            elif strong or medium:
                q = "ok"
                reason = "Рейз с рукой средней/сильной силы может быть ок, но сильно зависит от спектров и структуры доски."
            else:
                # блефовый рейз
                if not multiway and ip:
                    q = "ok"
                    reason = "Блефовый рейз на флопе в хедз-ап поте в позиции — агрессивный, но допустимый приём."
                else:
                    q = "risky"
                    reason = "Блефовый рейз со слабой рукой в мультипоте или без позиции выглядит рискованным."

        elif action_type in ("fold_vs_bet", "fold"):
            if strong or very_strong:
                q = "bad"
                reason = "Фолд достаточно сильной руки на флопе чаще всего выглядит слишком тайтовым."
            elif weak:
                q = "good"
                reason = "Фолд слабой руки без перспективных дро против ставки на флопе — нормальное аккуратное решение."
            else:
                q = "ok"
                reason = "Фолд руки средней силы на флопе может быть ок, особенно против крупного сайзинга или тайтовых диапазонов."


        decision_quality = q
        if reason:
            quality_comment = reason

    # -------------------------------
    # Общий комментарий по споту
    # -------------------------------
    pct_str = None
    if first.pct_pot is not None:
        pct_str = f"{first.pct_pot * 100:.1f}%"
    size_part = ""
    if first.action in ("bet", "raise") and first.amount is not None and first.pot_before is not None:
        size_part = f" Размер ставки: {first.amount:.2f} в пот {first.pot_before:.2f}"
        if pct_str:
            size_part += f" (~{pct_str} пота)."

    pos_part = "в позиции" if hero_ip else "без позиции"
    multi_part = "в мультипоте" if players_to_flop > 2 else "в хедз-ап банке"

    hand_part = ""
    if hero_flop_hand_category:
        hand_part = f" Категория руки на флопе: {hero_flop_hand_category}"
        if pair_kind:
            hand_part += f" ({pair_kind})."

    quality_part = ""
    if decision_quality != "unknown":
        quality_part = f" Оценка решения движком: {decision_quality}. {quality_comment}"

    equity_part = ""
    if equity_estimate and equity_estimate.get("estimated_equity") is not None:
        equity_part = (
            f" Оценочная equity против диапазона оппонента на флопе ≈ "
            f"{equity_estimate['estimated_equity']:.2f}."
        )

    comment = (
        f"Тип действия на флопе: {action_type}. "
        f"Ты играешь {multi_part} {pos_part}.{size_part}{hand_part}{quality_part}{equity_part}"
    )

    return {
        "action_type": action_type,
        "action_kind": first.action,
        "sizing": sizing,
        "context": context,
        "hand": hand_info,
        "equity_estimate": equity_estimate,
        "decision_quality": decision_quality,
        "quality_comment": quality_comment,
        "comment": comment,
    }

# ---------------------------------------------------------------------
#  TXT → JSON
# ---------------------------------------------------------------------


def parse_file_to_hands(path: str | Path) -> List[Dict[str, Any]]:
    hand_texts = load_and_split(path)
    hands_objects: List[Hand] = []

    for idx, hand_text in enumerate(hand_texts, start=1):
        (
            hand_id,
            game_type,
            currency,
            sb,
            bb,
            date,
            time,
            table_name,
            max_players,
            button_seat,
        ) = parse_hand_header(hand_text)

        players = parse_players(hand_text)
        players = assign_positions(players, button_seat, max_players)

        hero_name, hero_cards = parse_hero(hand_text)

        hero_position: Optional[str] = None
        hero_stack_bb: Optional[float] = None
        if hero_name is not None and bb and bb > 0:
            for p in players:
                if p.name == hero_name:
                    hero_position = p.position
                    hero_stack_bb = p.stack / bb
                    break

        effective_stack_bb = compute_effective_stack_bb(players, hero_name, bb)

        actions = parse_actions(hand_text)
        board = parse_board(hand_text)
        total_pot, rake = parse_total_pot_and_rake(hand_text)
        winners = parse_winners(hand_text)
        showdown = parse_showdown(hand_text)

        pots = annotate_actions_with_pot_and_bb(actions, bb)

        hero_preflop_analysis = compute_hero_preflop_analysis(
            actions=actions,
            players=players,
            hero_name=hero_name,
            hero_position=hero_position,
            effective_stack_bb=effective_stack_bb,
        )

        villain_position: Optional[str] = None
        if hero_preflop_analysis and hero_preflop_analysis.villain_raiser:
            vr_name = hero_preflop_analysis.villain_raiser
            for p in players:
                if p.name == vr_name:
                    villain_position = p.position
                    break

        hero_preflop_equity: Optional[Dict[str, Any]] = None
        if hero_cards:
            hero_preflop_equity = estimate_preflop_equity_as_dict(
                hero_cards=hero_cards,
                hero_position=hero_position,
                villain_position=villain_position,
            )

        hero_preflop_decision: Optional[Dict[str, Any]] = None
        if hero_preflop_analysis and hero_preflop_equity:
            hero_preflop_decision = compute_hero_preflop_decision(
                actions=actions,
                hero_name=hero_name,
                hero_preflop_analysis=hero_preflop_analysis,
                hero_preflop_equity=hero_preflop_equity,
            )

        # --- Флоп-анализ: только если герой реально дошёл до флопа ---
        hero_has_flop_action = False
        if hero_name is not None:
            hero_has_flop_action = any(
                a.street == "flop" and a.player == hero_name
                for a in actions
            )

        if not hero_has_flop_action:
            hero_flop_hand_category: Optional[str] = None
            hero_flop_hand_detail: Optional[Dict[str, Any]] = None
            hero_flop_decision: Optional[Dict[str, Any]] = None
            hero_turn_decision: Optional[Dict[str, Any]] = None
        else:
            hero_flop_hand_category = evaluate_flop_hand_category(
                hero_cards=hero_cards,
                board=board,
            )
            hero_flop_hand_detail = compute_hero_flop_detail(
                hero_cards=hero_cards,
                board=board,
                hero_flop_hand_category=hero_flop_hand_category,
            )
            hero_flop_decision = compute_hero_flop_decision(
                actions=actions,
                hero_name=hero_name,
                hero_position=hero_position,
                hero_preflop_analysis=hero_preflop_analysis,
                hero_flop_hand_category=hero_flop_hand_category,
                hero_flop_hand_detail=hero_flop_hand_detail,
            )
            hero_turn_decision = evaluate_hero_turn_decision(
                actions=actions,
                hero_name=hero_name,
                hero_position=hero_position,
                hero_preflop_analysis=hero_preflop_analysis,
                hero_flop_decision=hero_flop_decision,
                board=board,
            )

        hand = Hand(
            id=idx,
            hand_id=hand_id,
            game_type=game_type,
            currency=currency,
            small_blind=sb,
            big_blind=bb,
            date=date,
            time=time,
            table_name=table_name,
            max_players=max_players,
            button_seat=button_seat,
            players=players,
            hero_name=hero_name,
            hero_cards=hero_cards,
            hero_position=hero_position,
            hero_stack_bb=hero_stack_bb,
            hero_preflop_analysis=hero_preflop_analysis,
            hero_preflop_equity=hero_preflop_equity,
            hero_preflop_decision=hero_preflop_decision,
            hero_flop_hand_category=hero_flop_hand_category,
            hero_flop_hand_detail=hero_flop_hand_detail,
            hero_flop_decision=hero_flop_decision,
            hero_turn_decision=hero_turn_decision,
            actions=actions,
            board=board,
            pot_preflop=pots["preflop"],
            pot_flop=pots["flop"],
            pot_turn=pots["turn"],
            pot_river=pots["river"],
            total_pot=total_pot,
            rake=rake,
            winners=winners,
            showdown=showdown,
            raw_text=hand_text,
        )

        hands_objects.append(hand)

    return [asdict(hand) for hand in hands_objects]


def parse_file_to_json_string(path: str | Path) -> str:
    hands = parse_file_to_hands(path)
    return json.dumps(hands, ensure_ascii=False, indent=2)
