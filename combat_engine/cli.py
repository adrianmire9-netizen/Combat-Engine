"""Small terminal frontend; the engine itself has no input/output dependencies."""

import argparse
from pathlib import Path

from .engine import Battle, Combatant, RulesError, load_catalog


def main():
    parser = argparse.ArgumentParser(description="Play a customizable turn-based battle")
    parser.add_argument("--data", type=Path, default=Path("examples/catalog.json"))
    parser.add_argument("--auto", action="store_true", help="Let both teams act automatically")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--max-turns", type=int, default=200)
    args = parser.parse_args()
    catalog = load_catalog(args.data)
    roster = catalog.get("battle", [{"character": cid, "team": str(i)} for i, cid in enumerate(catalog["characters"])])
    battle = Battle(catalog, [Combatant(catalog, entry["character"], entry["team"], name=entry.get("name")) for entry in roster], seed=args.seed)
    printed = 0

    def show_log():
        nonlocal printed
        for line in battle.log[printed:]:
            print(line)
        printed = len(battle.log)

    for _ in range(args.max_turns):
        actor = battle.begin_turn()
        show_log()
        if actor is None:
            break
        for c in battle.combatants:
            statuses = ", ".join(f"{s.id}({s.remaining},x{s.stacks})" for s in c.statuses.values())
            print(f"  {c.name} [{c.team}] HP {c.resources['hp']:g}/{c.stat('max_hp'):g} | {statuses}")
        actions = battle.available_actions(actor)
        if not actions:
            battle.wait()
            continue
        automatic = args.auto or actor.team != roster[0]["team"]
        if automatic:
            # Prefer attacks; keep AI intentionally simple and separate from rules.
            attacks = [a for a in actions if not a.startswith("item:") and catalog["abilities"][a].get("target", "enemy") in {"enemy", "all_enemies"}]
            action = battle.rng.choice(attacks or actions)
        else:
            print(f"\n{actor.name}'s turn")
            for i, action in enumerate(actions, 1):
                print(f"  {i}. {action}")
            print("  0. Wait")
            try:
                choice = int(input("> "))
                if choice == 0:
                    battle.wait()
                    show_log()
                    continue
                if not 1 <= choice <= len(actions):
                    raise ValueError
                action = actions[choice - 1]
            except (ValueError, EOFError):
                print("Invalid input; waiting.")
                battle.wait()
                continue
        aid = catalog["items"][action[5:]]["ability"] if action.startswith("item:") else action
        ability = catalog["abilities"][aid]
        targets = battle.targets(actor, ability)
        target = targets[0] if targets else None
        if not automatic and len(targets) > 1 and ability.get("target", "enemy") in {"enemy", "ally"}:
            for i, candidate in enumerate(targets, 1):
                print(f"  {i}. {candidate.name}")
            try:
                index = int(input("Target > "))
                if not 1 <= index <= len(targets):
                    raise ValueError
                target = targets[index - 1]
            except (ValueError, EOFError):
                print("Invalid target; using first target.")
        try:
            battle.act(action, target)
        except RulesError as error:
            print(error)
            battle.wait()
        show_log()
    show_log()
    if battle.finished:
        print(f"Winner: {battle.winner or 'draw'}")
    else:
        parser.exit(1, "Turn limit reached without a winner.\n")
