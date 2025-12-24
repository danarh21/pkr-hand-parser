import json

with open("hands.json", "r", encoding="utf-8") as f:
    hands = json.load(f)

def street_count(h, street):
    return sum(1 for a in (h.get("actions") or []) if isinstance(a, dict) and a.get("street") == street)

def hero_street_count(h, street):
    hero = h.get("hero_name")
    return sum(
        1 for a in (h.get("actions") or [])
        if isinstance(a, dict)
        and a.get("street") == street
        and (
            a.get("player_name") == hero
            or a.get("player") == hero
            or a.get("name") == hero
        )
    )

hands_with_turn_actions = sum(1 for h in hands if street_count(h, "turn") > 0)
hands_with_river_actions = sum(1 for h in hands if street_count(h, "river") > 0)

hands_hero_acted_turn = sum(1 for h in hands if hero_street_count(h, "turn") > 0)
hands_hero_acted_river = sum(1 for h in hands if hero_street_count(h, "river") > 0)

print("hands_with_turn_actions:", hands_with_turn_actions, "/", len(hands))
print("hands_with_river_actions:", hands_with_river_actions, "/", len(hands))
print("hands_where_hero_acted_on_turn:", hands_hero_acted_turn, "/", len(hands))
print("hands_where_hero_acted_on_river:", hands_hero_acted_river, "/", len(hands))

# sample hand with turn actions
sample = None
for h in hands:
    if street_count(h, "turn") > 0:
        sample = h
        break

print()
print("SAMPLE HAND:")
print("hand_id:", sample.get("hand_id") if sample else None)
print("hero_name:", sample.get("hero_name") if sample else None)

if sample:
    turn_actions = [a for a in (sample.get("actions") or []) if isinstance(a, dict) and a.get("street") == "turn"]
    print("turn_actions_in_sample:", len(turn_actions))
    for i, a in enumerate(turn_actions[:3], start=1):
        print("TURN_ACTION", i, "player_name=", a.get("player_name"), "| player=", a.get("player"), "| name=", a.get("name"))
        print("TURN_ACTION", i, "action=", a.get("action"), "| action_kind=", a.get("action_kind"))
        print("TURN_ACTION", i, "amount=", a.get("amount"), "| bet=", a.get("bet"), "| size=", a.get("size"), "| value=", a.get("value"))
        print("keys=", sorted(list(a.keys())))
        print("---")

    print("hero_turn_decision_present:", bool(sample.get("hero_turn_decision")))
    print("hero_river_decision_present:", bool(sample.get("hero_river_decision")))
