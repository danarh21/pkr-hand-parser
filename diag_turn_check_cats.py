import json

with open("hands.json","r",encoding="utf-8") as f:
    hands=json.load(f)

def get_dec(h, street):
    d=h.get(f"hero_{street}_decision")
    return d if isinstance(d,dict) else None

turn_check_ids=[]
cats_in_checks=set()

for h in hands:
    d=get_dec(h,"turn")
    if not d: 
        continue
    if d.get("action_type")=="check":
        hid=h.get("hand_id")
        cat=h.get("hero_flop_hand_category")
        turn_check_ids.append((hid, cat))
        cats_in_checks.add(cat)

print("TURN CHECK HANDS (hand_id, hero_flop_hand_category):")
for hid, cat in turn_check_ids:
    print("  ", hid, "=>", cat)

print()
print("UNIQUE CATEGORIES IN TURN-CHECK HANDS:")
for c in sorted(list(cats_in_checks), key=lambda x: str(x)):
    print("  ", c)

print()
print("STRONG_CATS currently expected:")
print("  two_pair, set, straight, flush, full_house, quads")
