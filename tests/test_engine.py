import copy
import unittest
from pathlib import Path

from combat_engine import Battle, Combatant, RulesError, load_catalog
from combat_engine.engine import validate_catalog


class CombatTests(unittest.TestCase):
    def setUp(self):
        self.data = load_catalog(Path(__file__).resolve().parent.parent / "examples/catalog.json")
        self.data["characters"]["knight"]["stats"]["speed"] = 30
        self.hero = Combatant(self.data, "knight", "heroes")
        self.foe = Combatant(self.data, "brute", "monsters")
        self.battle = Battle(self.data, [self.hero, self.foe], seed=1)

    def test_equipment_armor_and_resistance(self):
        self.assertEqual(self.hero.stat("attack"), 15)
        self.battle.begin_turn()
        self.battle.act("slash", self.foe)
        self.assertAlmostEqual(self.foe.resources["hp"], 100 - (4 + 15 - 5) * 0.9)

    def test_invalid_action_does_not_change_state_or_rng(self):
        self.battle.begin_turn()
        before = (dict(self.hero.resources), dict(self.hero.inventory), self.battle.rng.getstate(), list(self.battle.log))
        with self.assertRaises(RulesError):
            self.battle.act("bash", self.hero)
        self.assertEqual(before, (self.hero.resources, self.hero.inventory, self.battle.rng.getstate(), self.battle.log))
        self.assertIs(self.battle.active, self.hero)
        with self.assertRaises(RulesError):
            self.battle.act("fireball", self.foe)

    def test_costs_cooldowns_and_stun(self):
        self.battle.begin_turn()
        self.battle.act("bash", self.foe)
        self.assertEqual(self.hero.resources["stamina"], 9)
        # Brute skips its turn, so the next actor is the knight.
        self.assertIs(self.battle.begin_turn(), self.hero)
        self.assertNotIn("stun", self.foe.statuses)
        self.assertNotIn("bash", self.battle.available_actions(self.hero))
        self.battle.wait()
        self.battle.begin_turn()
        self.battle.wait()
        self.battle.begin_turn()
        self.assertNotIn("bash", self.battle.available_actions(self.hero))
        self.battle.wait()
        self.battle.begin_turn()
        self.battle.wait()
        self.battle.begin_turn()
        self.assertIn("bash", self.battle.available_actions(self.hero))

    def test_guard_lasts_until_end_of_next_owner_turn(self):
        self.battle.begin_turn()
        self.battle.act("guard")
        self.assertEqual(self.hero.stat("armor"), 14)
        self.battle.begin_turn()
        self.battle.act("slash", self.hero)
        self.assertEqual(self.hero.resources["hp"], 95)
        self.battle.begin_turn()
        self.assertIn("guarded", self.hero.statuses)
        self.battle.wait()
        self.assertEqual(self.hero.stat("armor"), 6)

    def test_consumable_count_heal_and_empty_inventory(self):
        self.hero.resources["hp"] = 80
        self.battle.begin_turn()
        self.battle.act("item:potion", self.hero)
        self.assertEqual(self.hero.resources["hp"], 100)
        self.assertEqual(self.hero.inventory["potion"], 1)
        self.hero.inventory["potion"] = 0
        self.assertNotIn("item:potion", self.battle.available_actions(self.hero))

    def test_area_damage(self):
        other = Combatant(self.data, "goblin", "monsters")
        battle = Battle(self.data, [self.hero, self.foe, other])
        battle.begin_turn()
        battle.act("whirlwind")
        self.assertLess(self.foe.resources["hp"], 100)
        self.assertLess(other.resources["hp"], 55)
        self.assertEqual(self.hero.resources["hp"], 100)

    def test_poison_stacking_ticks_duration_and_cleanse(self):
        effect = {"kind": "status", "status": "poison"}
        for _ in range(5):
            self.battle._effect(effect, self.hero, self.foe)
        self.assertEqual(self.foe.statuses["poison"].stacks, 3)
        self.battle.begin_turn()
        self.battle.wait()
        self.battle.begin_turn()
        self.assertEqual(self.foe.resources["hp"], 91)
        self.battle.wait()
        self.assertEqual(self.foe.statuses["poison"].remaining, 2)
        self.battle._effect({"kind": "cleanse", "tag": "poison"}, self.hero, self.foe)
        self.assertNotIn("poison", self.foe.statuses)

    def test_damage_immunity_weakness_and_no_negative_damage(self):
        self.foe.base_resistances["fire"] = 1
        self.battle._effect({"kind": "damage", "power": 10, "damage_type": "fire"}, self.hero, self.foe)
        self.assertEqual(self.foe.resources["hp"], 100)
        self.foe.base_resistances["fire"] = -0.5
        self.battle._effect({"kind": "damage", "power": 10, "damage_type": "fire"}, self.hero, self.foe)
        self.assertEqual(self.foe.resources["hp"], 85)
        self.battle._effect({"kind": "damage", "power": 1}, self.hero, self.foe)
        self.assertEqual(self.foe.resources["hp"], 85)

    def test_custom_resource_and_stat(self):
        self.data["characters"]["knight"]["stats"].update(max_rage=10, luck=7)
        self.data["abilities"]["rage_strike"] = {"costs": {"rage": 2}, "effects": [{"kind": "damage", "scaling": {"luck": 2}, "armor_stat": None}]}
        self.data["characters"]["knight"]["abilities"].append("rage_strike")
        hero = Combatant(self.data, "knight", "heroes")
        battle = Battle(self.data, [hero, self.foe])
        battle.begin_turn()
        battle.act("rage_strike", self.foe)
        self.assertEqual(hero.resources["rage"], 8)
        self.assertEqual(self.foe.resources["hp"], 87.4)
        battle._effect({"kind": "restore", "resource": "rage", "power": 20}, hero, hero)
        self.assertEqual(hero.resources["rage"], 10)

    def test_defeat_and_winner(self):
        self.foe.resources["hp"] = 1
        self.battle.begin_turn()
        self.battle.act("slash", self.foe)
        self.assertTrue(self.battle.finished)
        self.assertEqual(self.battle.winner, "heroes")
        self.assertIsNone(self.battle.begin_turn())
        with self.assertRaises(RulesError):
            self.battle.act("slash", self.foe)

    def test_round_reorders_by_modified_speed(self):
        self.battle.begin_turn()
        self.battle.wait()
        self.battle.begin_turn()
        self.battle.wait()
        self.foe.base_stats["speed"] = 50
        self.assertIs(self.battle.begin_turn(), self.foe)
        self.assertEqual(self.battle.round, 2)

    def test_status_tick_can_end_battle(self):
        self.foe.resources["hp"] = 2
        self.battle._effect({"kind": "status", "status": "poison"}, self.hero, self.foe)
        self.battle.begin_turn()
        self.battle.wait()
        self.assertIsNone(self.battle.begin_turn())
        self.assertEqual(self.battle.winner, "heroes")

    def test_invalid_catalog(self):
        for edit in (
            lambda d: d["abilities"]["slash"].update(target="unknown"),
            lambda d: d["abilities"]["slash"].update(costs={"mana": -1}),
            lambda d: d["statuses"]["burn"].update(duration=0),
            lambda d: d["characters"]["knight"].update(equipment=["sword", "sword"]),
            lambda d: d["characters"]["knight"]["stats"].update(max_hp=float("nan")),
            lambda d: d["characters"]["knight"].update(abilities="slash"),
            lambda d: d["battle"][0].update(character="missing"),
        ):
            data = copy.deepcopy(self.data)
            edit(data)
            with self.assertRaises(RulesError):
                validate_catalog(data)

    def test_status_expires_after_exact_tick_count(self):
        self.battle._effect({"kind": "status", "status": "burn"}, self.hero, self.foe)
        for _ in range(2):
            self.assertIs(self.battle.begin_turn(), self.hero)
            self.battle.wait()
            self.assertIs(self.battle.begin_turn(), self.foe)
            self.battle.wait()
        self.assertEqual(self.foe.resources["hp"], 92)
        self.assertNotIn("burn", self.foe.statuses)

    def test_zero_chance_and_self_effect_on_area_action(self):
        self.data["abilities"]["whirlwind"]["effects"].extend([
            {"kind": "status", "status": "poison", "chance": 0},
            {"kind": "restore", "resource": "stamina", "power": 1, "recipient": "self"},
        ])
        other = Combatant(self.data, "goblin", "monsters")
        battle = Battle(self.data, [self.hero, self.foe, other])
        battle.begin_turn()
        battle.act("whirlwind")
        self.assertEqual(self.hero.resources["stamina"], 9)
        self.assertNotIn("poison", self.foe.statuses)
        self.assertNotIn("poison", other.statuses)

    def test_seeded_full_battle_is_reproducible(self):
        def play():
            actors = [Combatant(self.data, entry["character"], entry["team"]) for entry in self.data["battle"]]
            battle = Battle(self.data, actors, seed=42)
            turns = 0
            while not battle.finished and turns < 200:
                actor = battle.begin_turn()
                if actor is None:
                    break
                attacks = [a for a in battle.available_actions(actor) if not a.startswith("item:") and self.data["abilities"][a].get("target", "enemy") in {"enemy", "all_enemies"}]
                if attacks:
                    action = battle.rng.choice(attacks)
                    targets = battle.targets(actor, self.data["abilities"][action])
                    battle.act(action, targets[0])
                else:
                    battle.wait()
                turns += 1
            self.assertTrue(battle.finished)
            return battle.winner, battle.log
        self.assertEqual(play(), play())


if __name__ == "__main__":
    unittest.main()
