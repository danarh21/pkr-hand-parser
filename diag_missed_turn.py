import json

with open("hands.json","r",encoding="utf-8") as f:
    hands = json.load(f)

def get_dec(h, street):
    key = f"hero_{street}_decision"
    d = h.get(key)
    if isinstance(d, dict):
        return d
    st = h.get(street)
    if isinstance(st, dict):
        d2 = st.get("hero_decision") or st.get("decision")
        if isinstance(d2, dict):
            return d2
    streets = h.get("streets")
    if isinstance(streets, dict):
        st2 = streets.get(street)
        if isinstance(st2, dict):
            d3 = st2.get("hero_decision") or st2.get("decision")
            if isinstance(d3, dict):
                return d3
    return None

def sf(x):
    try:
        if x is None: return None
        return float(x)
    except:
        return None

turn_rows = []
turn_check_rows = []

for h in hands:
    hid = h.get("hand_id")
    d = get_dec(h, "turn")
    if not isinstance(d, dict):
        continue

    action_type = d.get("action_type")
    ctx = d.get("context") if isinstance(d.get("context"), dict) else {}
    hero_ip = ctx.get("hero_ip")
    multiway = ctx.get("multiway")

    eq = None
    eqd = d.get("equity_estimate")
    if isinstance(eqd, dict):
        eq = sf(eqd.get("estimated_equity"))

    pot_before = None
    sz = d.get("sizing")
    if isinstance(sz, dict):
        pot_before = sf(sz.get("pot_before"))
    if pot_before is None:
        # вдруг положили прямо в action / или в pot_turn
        pot_before = sf(h.get("pot_turn")) or sf(h.get("pot_flop"))

    mv = d.get("missed_value")
    mv_ev = 0.0
    if isinstance(mv, dict):
        mv_ev = sf(mv.get("missed_value_ev")) or 0.0

    row = (hid, action_type, hero_ip, multiway, eq, pot_before, mv_ev)
    turn_rows.append(row)
    if action_type == "check":
        turn_check_rows.append(row)

print("TURN DECISIONS:", len(turn_rows))
for r in turn_rows:
    print("  ", r)

print()
print("TURN CHECK ONLY:", len(turn_check_rows))
for r in turn_check_rows:
    print("  ", r)

print()
print("SUMMARY CHECK CONDITIONS (eq>=0.60, pot_before not None, hero_ip=True, multiway=False):")
ok = 0
for hid, action_type, hero_ip, multiway, eq, pot_before, mv_ev in turn_check_rows:
    cond = (eq is not None and eq >= 0.60 and pot_before is not None and hero_ip is True and multiway is False)
    if cond: ok += 1
    print(f"  {hid}: hero_ip={hero_ip} multiway={multiway} eq={eq} pot_before={pot_before} => {cond}")
print("CHECK SPOTS PASSING CONDITIONS:", ok)
