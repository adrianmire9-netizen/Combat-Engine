"""Data-driven combat with no runtime dependencies or executable data formulas."""

from __future__ import annotations

import copy
import json
import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from .grid import Board, distance, validate_grid


class RulesError(ValueError):
    """An invalid definition or action; invalid actions do not consume a turn."""


TARGETS = {"enemy", "ally", "self", "all_enemies", "all_allies"}
EFFECTS = {"damage", "heal", "restore", "status", "cleanse"}


def _number(value: Any, where: str, minimum: float | None = None) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise RulesError(f"{where} must be a finite number")
    if minimum is not None and value < minimum:
        raise RulesError(f"{where} must be >= {minimum}")


def _integer(value: Any, where: str, minimum: int = 0) -> None:
    _number(value, where, minimum)
    if int(value) != value:
        raise RulesError(f"{where} must be an integer")


def validate_catalog(data: dict) -> None:
    """Fail early on invalid references and supported effect shapes."""
    if not isinstance(data, dict):
        raise RulesError("Catalog must be an object")
    for section in ("abilities", "statuses", "items", "characters", "species", "stat_definitions", "damage_types"):
        if not isinstance(data.get(section, {}), dict):
            raise RulesError(f"{section} must be an object keyed by unique IDs")
        for identifier, definition in data.get(section, {}).items():
            if not isinstance(identifier, str) or not identifier or not isinstance(definition, dict):
                raise RulesError(f"{section} entries need a nonempty ID and an object definition")

    def string_list(values: Any, where: str) -> None:
        if not isinstance(values, list) or any(not isinstance(v, str) for v in values):
            raise RulesError(f"{where} must be a list of strings")

    def numeric_map(values: dict, where: str, minimum: float | None = None) -> None:
        if not isinstance(values, dict):
            raise RulesError(f"{where} must be an object")
        for key, value in values.items():
            if not isinstance(key, str) or not key:
                raise RulesError(f"{where} keys must be nonempty strings")
            _number(value, f"{where}.{key}", minimum)

    rules = data.get("rules", {})
    if not isinstance(rules, dict):
        raise RulesError("rules must be an object")
    if not isinstance(rules.get("stamina_per_turn", False), bool):
        raise RulesError("rules.stamina_per_turn must be a boolean")
    _number(rules.get("default_action_cost", 1), "rules.default_action_cost", 0.01)
    numeric_map(rules.get("initiative", {"speed": 1}), "rules.initiative")
    derived = rules.get("derived_stats", {})
    if not isinstance(derived, dict):
        raise RulesError("rules.derived_stats must be an object")
    for stat, scaling in derived.items():
        numeric_map(scaling, f"rules.derived_stats.{stat}")
        if any(source in derived for source in scaling):
            raise RulesError("Derived stats must scale from base stats, not other derived stats")
    for sid, definition in data.get("species", {}).items():
        for field in ("stat_bonuses", "stat_multipliers", "resistances"):
            numeric_map(definition.get(field, {}), f"species.{sid}.{field}")
        string_list(definition.get("traits", []), f"species.{sid}.traits")
        if not isinstance(definition.get("description", ""), str):
            raise RulesError(f"species.{sid}.description must be a string")
    for stat, definition in data.get("stat_definitions", {}).items():
        for field in ("name", "purpose"):
            if not isinstance(definition.get(field, ""), str):
                raise RulesError(f"stat_definitions.{stat}.{field} must be a string")
        string_list(definition.get("secondary_uses", []), f"stat_definitions.{stat}.secondary_uses")
        if definition.get("kind", "number") not in {"number", "category"}:
            raise RulesError(f"stat_definitions.{stat}.kind must be number or category")
    for tid, definition in data.get("damage_types", {}).items():
        group = definition.get("group")
        if group is not None and (group not in data["damage_types"] or group == tid):
            raise RulesError(f"{tid}: invalid damage group")
        if group is not None and data["damage_types"][group].get("group") is not None:
            raise RulesError("Damage groups cannot be nested")
        if "armor_stat" in definition and definition["armor_stat"] is not None and not isinstance(definition["armor_stat"], str):
            raise RulesError(f"{tid}.armor_stat must be a stat name or null")

    def effects(values: list, where: str) -> None:
        if not isinstance(values, list):
            raise RulesError(f"{where} must be a list")
        for effect in values:
            if not isinstance(effect, dict) or effect.get("kind") not in EFFECTS:
                raise RulesError(f"Unknown effect in {where}: {effect}")
            if effect.get("recipient", "target") not in {"target", "self"}:
                raise RulesError(f"Invalid recipient in {where}")
            _number(effect.get("chance", 1), f"{where}.chance", 0)
            numeric_map(effect.get("chance_scaling", {}), f"{where}.chance_scaling")
            numeric_map(effect.get("resistance_scaling", {}), f"{where}.resistance_scaling", 0)
            if effect.get("chance", 1) > 1:
                raise RulesError(f"{where}.chance must be <= 1")
            if effect["kind"] == "status":
                if effect.get("status") not in data.get("statuses", {}):
                    raise RulesError(f"Unknown status in {where}")
                if "duration" in effect:
                    _integer(effect["duration"], f"{where}.duration", 1)
            if effect["kind"] in {"damage", "heal", "restore"}:
                _number(effect.get("power", 0), f"{where}.power", 0)
                numeric_map(effect.get("scaling", {}), f"{where}.scaling")
                if effect["kind"] == "restore" and not isinstance(effect.get("resource"), str):
                    raise RulesError(f"{where}.restore needs a resource name")
            if effect["kind"] == "damage":
                if not isinstance(effect.get("damage_type", "physical"), str):
                    raise RulesError(f"{where}.damage_type must be a string")
                if "armor_stat" in effect and effect["armor_stat"] is not None and not isinstance(effect["armor_stat"], str):
                    raise RulesError(f"{where}.armor_stat must be a stat name or null")

    for aid, ability in data.get("abilities", {}).items():
        if aid.startswith("item:"):
            raise RulesError("Ability IDs cannot start with the reserved 'item:' prefix")
        if ability.get("target", "enemy") not in TARGETS:
            raise RulesError(f"Invalid target for {aid}")
        numeric_map(ability.get("costs", {}), f"{aid}.costs", 0)
        _integer(ability.get("cooldown", 0), f"{aid}.cooldown")
        if "action_cost" in ability:
            _number(ability["action_cost"], f"{aid}.action_cost", 0.01)
        if "accuracy" in ability:
            accuracy = ability["accuracy"]
            if not isinstance(accuracy, dict):
                raise RulesError(f"{aid}.accuracy must be an object")
            _number(accuracy.get("base", 1), f"{aid}.accuracy.base", 0)
            if accuracy.get("base", 1) > 1:
                raise RulesError(f"{aid}.accuracy.base must be <= 1")
            numeric_map(accuracy.get("attacker", {}), f"{aid}.accuracy.attacker")
            numeric_map(accuracy.get("defender", {}), f"{aid}.accuracy.defender", 0)
        effects(ability.get("effects", []), aid)
    for sid, status in data.get("statuses", {}).items():
        string_list(status.get("tags", []), f"{sid}.tags")
        if not isinstance(status.get("skip_turn", False), bool):
            raise RulesError(f"{sid}.skip_turn must be a boolean")
        _integer(status.get("duration", 1), f"{sid}.duration", 1)
        _integer(status.get("max_stacks", 1), f"{sid}.max_stacks", 1)
        for field in ("stat_bonuses", "stat_multipliers", "resistances"):
            numeric_map(status.get(field, {}), f"{sid}.{field}")
        if status.get("stacking", "refresh") not in {"refresh", "stack", "replace"}:
            raise RulesError(f"Invalid stacking mode for {sid}")
        effects(status.get("tick_effects", []), sid)
        if any(e["kind"] in {"status", "cleanse"} for e in status.get("tick_effects", [])):
            raise RulesError(f"{sid}: status ticks support damage, heal, and restore only")
    for iid, item in data.get("items", {}).items():
        if item.get("kind") not in {"equipment", "consumable"}:
            raise RulesError(f"Invalid item kind for {iid}")
        if item["kind"] == "consumable" and item.get("ability") not in data.get("abilities", {}):
            raise RulesError(f"Unknown consumable ability for {iid}")
        for field in ("stat_bonuses", "stat_multipliers", "resistances"):
            numeric_map(item.get(field, {}), f"{iid}.{field}")
        if item["kind"] == "equipment" and not isinstance(item.get("slot"), str):
            raise RulesError(f"Equipment {iid} needs a slot")
        string_list(item.get("allowed_species", []), f"{iid}.allowed_species")
        if any(s not in data.get("species", {}) for s in item.get("allowed_species", [])):
            raise RulesError(f"{iid}: unknown allowed species")
    for cid, char in data.get("characters", {}).items():
        if not isinstance(char.get("species", ""), str):
            raise RulesError(f"{cid}.species must be a species ID string")
        if char.get("species") and char["species"] not in data.get("species", {}):
            raise RulesError(f"{cid}: unknown species")
        string_list(char.get("abilities", []), f"{cid}.abilities")
        string_list(char.get("equipment", []), f"{cid}.equipment")
        if not isinstance(char.get("inventory", {}), dict):
            raise RulesError(f"{cid}.inventory must be an object")
        numeric_map(char.get("stats", {}), f"{cid}.stats")
        _number(char.get("stats", {}).get("max_hp", 0), f"{cid}.max_hp", 1)
        for stat, value in char["stats"].items():
            if stat.startswith("max_"):
                _number(value, f"{cid}.{stat}", 0)
        numeric_map(char.get("resources", {}), f"{cid}.resources", 0)
        numeric_map(char.get("resistances", {}), f"{cid}.resistances")
        for resource, value in char.get("resources", {}).items():
            cap = char["stats"].get(f"max_{resource}")
            if cap is None or value > cap:
                raise RulesError(f"{cid}.{resource} requires a sufficient max_{resource} stat")
        for aid in char.get("abilities", []):
            if aid not in data.get("abilities", {}):
                raise RulesError(f"{cid}: unknown ability {aid}")
        slots = set()
        for iid in char.get("equipment", []):
            item = data.get("items", {}).get(iid, {})
            if item.get("kind") != "equipment":
                raise RulesError(f"{cid}: unknown equipment {iid}")
            if item["slot"] in slots:
                raise RulesError(f"{cid}: duplicate equipment slot {item['slot']}")
            slots.add(item["slot"])
            if item.get("allowed_species") and char.get("species") not in item["allowed_species"]:
                raise RulesError(f"{cid}: species cannot equip {iid}")
        for iid, count in char.get("inventory", {}).items():
            if data.get("items", {}).get(iid, {}).get("kind") != "consumable":
                raise RulesError(f"{cid}: unknown consumable {iid}")
            _integer(count, f"{cid}.inventory.{iid}")
    if "battle" in data:
        if not isinstance(data["battle"], list):
            raise RulesError("battle must be a roster list")
        for entry in data["battle"]:
            if not isinstance(entry, dict) or entry.get("character") not in data.get("characters", {}):
                raise RulesError("Battle roster references an unknown character")
            if not isinstance(entry.get("team"), str) or not entry["team"]:
                raise RulesError("Battle roster needs nonempty team names")
    try:
        grid = validate_grid(data)
    except ValueError as error:
        raise RulesError(str(error)) from error
    for key, default in (("movement_base", 3), ("movement_speed_scaling", 0.1), ("move_stamina_cost", 0.5)):
        _number(grid.get(key, default), f"grid.{key}", 0)
    for aid, ability in data.get("abilities", {}).items():
        _integer(ability.get("range", 1), f"{aid}.range")
        if not isinstance(ability.get("line_of_sight", True), bool):
            raise RulesError(f"{aid}.line_of_sight must be a boolean")


def load_catalog(path: str | Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_catalog(data)
    return data


@dataclass
class StatusInstance:
    id: str
    remaining: int
    source: Combatant
    stacks: int = 1


class Combatant:
    def __init__(self, catalog: dict, character_id: str, team: str, *, name: str | None = None, position: list | tuple | None = None):
        template = copy.deepcopy(catalog["characters"][character_id])
        self.catalog = catalog
        self.character_id = character_id
        self.name = name or template.get("name", character_id)
        self.team = team
        self.position = position
        self.movement_remaining = 0
        self.species = template.get("species", "")
        self.base_stats = template["stats"]
        self.base_resistances = template.get("resistances", {})
        self.abilities = template.get("abilities", [])
        self.equipment = template.get("equipment", [])
        self.inventory = template.get("inventory", {})
        self.statuses: dict[str, StatusInstance] = {}
        self.cooldowns: dict[str, int] = {}
        stat_keys = set(self.base_stats) | set(catalog.get("rules", {}).get("derived_stats", {}))
        self.resources = {key[4:]: self.stat(key) for key in stat_keys if key.startswith("max_")}
        self.resources.update(template.get("resources", {}))
        self.clamp_resources()

    def modifiers(self):
        if self.species:
            yield self.catalog["species"][self.species], 1
        for iid in self.equipment:
            yield self.catalog["items"][iid], 1
        for status in self.statuses.values():
            yield self.catalog["statuses"][status.id], status.stacks

    def _modified_stat(self, key: str, base: float) -> float:
        value = base
        modifiers = list(self.modifiers())
        value += sum(mod.get("stat_bonuses", {}).get(key, 0) * stacks for mod, stacks in modifiers)
        for mod, stacks in modifiers:
            value *= mod.get("stat_multipliers", {}).get(key, 1) ** stacks
        return max(1 if key == "max_hp" else 0, value)

    def stat(self, key: str) -> float:
        scaling = self.catalog.get("rules", {}).get("derived_stats", {}).get(key, {})
        base = self.base_stats.get(key, 0) + sum(
            self._modified_stat(source, self.base_stats.get(source, 0)) * coefficient
            for source, coefficient in scaling.items())
        return self._modified_stat(key, base)

    def initiative(self) -> float:
        return sum(self.stat(k) * v for k, v in self.catalog.get("rules", {}).get("initiative", {"speed": 1}).items())

    def resistance(self, damage_type: str) -> float:
        group = self.catalog.get("damage_types", {}).get(damage_type, {}).get("group")
        keys = [damage_type] + ([group] if group else [])
        value = sum(self.base_resistances.get(key, 0) for key in keys)
        value += sum(sum(mod.get("resistances", {}).get(key, 0) for key in keys) * stacks for mod, stacks in self.modifiers())
        return min(1, max(-1, value))

    @property
    def alive(self) -> bool:
        return self.resources.get("hp", 0) > 0

    def clamp_resources(self) -> None:
        for key in self.resources:
            self.resources[key] = max(0, min(self.resources[key], self.stat(f"max_{key}")))


class Battle:
    """Call begin_turn(), then act() or wait(); invalid actions preserve state."""

    def __init__(self, catalog: dict, combatants: list[Combatant], *, seed: int | None = None):
        validate_catalog(catalog)
        if len(combatants) < 2 or len({c.team for c in combatants}) < 2:
            raise RulesError("A battle needs combatants on at least two teams")
        if len({id(c) for c in combatants}) != len(combatants):
            raise RulesError("A combatant cannot appear twice")
        if any(c.catalog is not catalog for c in combatants):
            raise RulesError("All combatants must use the battle's catalog")
        self.catalog = catalog
        self.combatants = list(combatants)
        self.rng = random.Random(seed)
        self.log: list[str] = []
        self.round = 0
        self.active: Combatant | None = None
        self._queue: list[Combatant] = []
        self._turn_statuses: list[StatusInstance] = []
        self._turn_cooldowns: set[str] = set()
        self.board = Board(catalog["grid"]) if catalog.get("grid", {}).get("enabled", False) else None
        if self.board:
            try:
                self.board.place(self.combatants)
            except ValueError as error:
                raise RulesError(str(error)) from error

    @property
    def finished(self) -> bool:
        return len({c.team for c in self.combatants if c.alive}) <= 1

    @property
    def winner(self) -> str | None:
        teams = {c.team for c in self.combatants if c.alive}
        return next(iter(teams)) if len(teams) == 1 else None

    def begin_turn(self) -> Combatant | None:
        if self.active is not None:
            return self.active
        while not self.finished:
            if not self._queue:
                self.round += 1
                self._queue = sorted((c for c in self.combatants if c.alive), key=lambda c: -c.initiative())
                self.log.append(f"Round {self.round}")
            actor = self._queue.pop(0)
            if not actor.alive:
                continue
            self.active = actor
            self._turn_statuses = list(actor.statuses.values())
            self._turn_cooldowns = set(actor.cooldowns)
            for status in self._turn_statuses:
                for effect in self.catalog["statuses"][status.id].get("tick_effects", []):
                    if actor.alive:
                        self._effect(effect, status.source, actor, multiplier=status.stacks)
            if self.catalog.get("rules", {}).get("stamina_per_turn", False):
                actor.resources["stamina"] = actor.stat("max_stamina")
            if self.board:
                config = self.catalog["grid"]
                actor.movement_remaining = math.floor(actor.stat("movement") if "movement" in actor.base_stats or "movement" in self.catalog.get("rules", {}).get("derived_stats", {}) else config.get("movement_base", 3) + actor.stat("speed") * config.get("movement_speed_scaling", 0.1))
            stunned = any(self.catalog["statuses"][s.id].get("skip_turn", False) for s in actor.statuses.values())
            if not actor.alive or stunned or self.finished:
                if stunned and actor.alive:
                    self.log.append(f"{actor.name} cannot act.")
                self._end_turn()
                continue
            return actor
        return None

    def action_costs(self, ability: dict) -> dict:
        costs = dict(ability.get("costs", {}))
        if self.catalog.get("rules", {}).get("stamina_per_turn", False):
            # Explicit stamina costs override the per-action default. A positive
            # floor prevents free actions from keeping a turn open indefinitely.
            costs["stamina"] = max(0.01, costs.get("stamina", ability.get("action_cost", self.catalog["rules"].get("default_action_cost", 1))))
        return costs

    def available_actions(self, actor: Combatant) -> list[str]:
        actions = list(actor.abilities) + [f"item:{iid}" for iid, count in actor.inventory.items() if count > 0]
        result = []
        for action in actions:
            aid = self.catalog["items"][action[5:]]["ability"] if action.startswith("item:") else action
            ability = self.catalog["abilities"][aid]
            if actor.cooldowns.get(aid, 0) == 0 and all(actor.resources.get(k, 0) + 1e-9 >= v for k, v in self.action_costs(ability).items()) and self.targets(actor, ability):
                result.append(action)
        return result

    def targets(self, actor: Combatant, ability: dict) -> list[Combatant]:
        mode = ability.get("target", "enemy")
        if mode == "self":
            return [actor] if actor.alive else []
        allies = mode in {"ally", "all_allies"}
        candidates = [c for c in self.combatants if c.alive and (c.team == actor.team) == allies]
        if self.board:
            reach = self.ability_range(ability)
            candidates = [c for c in candidates if distance(actor.position, c.position) <= reach
                          and (not ability.get("line_of_sight", True) or self.board.visible(actor.position, c.position))]
        return candidates

    @staticmethod
    def ability_range(ability: dict) -> int:
        return ability.get("range", 0 if ability.get("target") == "self" else 3 if ability.get("target") in {"ally", "all_allies"} else 1)

    def movement_paths(self, actor: Combatant) -> dict:
        if not self.board or actor is not self.active or not actor.alive or self.finished:
            return {}
        paths = self.board.paths(actor.position, [c.position for c in self.combatants if c is not actor and c.alive])
        budget = actor.movement_remaining
        cost = self.catalog["grid"].get("move_stamina_cost", 0.5) if self.catalog.get("rules", {}).get("stamina_per_turn", False) else 0
        if cost > 0:
            budget = min(budget, math.floor((actor.resources.get("stamina", 0) + 1e-9) / cost))
        return {p: path for p, path in paths.items() if 0 < len(path) <= budget}

    def move(self, destination: list | tuple) -> None:
        actor = self.active
        if not self.board or actor is None or self.finished:
            raise RulesError("Movement requires an active grid battle")
        if not isinstance(destination, (list, tuple)) or len(destination) != 2 or any(type(n) is not int for n in destination):
            raise RulesError("Choose an integer [x, y] destination")
        path = self.movement_paths(actor).get(tuple(destination))
        if path is None:
            raise RulesError("Cell is blocked, occupied, or beyond your movement/stamina budget")
        steps = len(path)
        actor.position = tuple(destination)
        actor.movement_remaining -= steps
        if self.catalog.get("rules", {}).get("stamina_per_turn", False):
            actor.resources["stamina"] = max(0, round(actor.resources.get("stamina", 0) - steps * self.catalog["grid"].get("move_stamina_cost", 0.5), 8))
        self.log.append(f"{actor.name} moves {steps} tiles to ({destination[0]}, {destination[1]}).")
        if not self.available_actions(actor) and not self.movement_paths(actor):
            self._end_turn()

    def auto_action(self) -> None:
        """One AI action: attack in range, approach an enemy, use a fallback, or end."""
        actor = self.active
        if actor is None or self.finished:
            raise RulesError("No active turn")
        actions = self.available_actions(actor)
        def definition(action):
            aid = self.catalog["items"][action[5:]]["ability"] if action.startswith("item:") else action
            return self.catalog["abilities"][aid]
        attacks = [a for a in actions if not a.startswith("item:") and definition(a).get("target", "enemy") in {"enemy", "all_enemies"}]
        if not attacks and self.board:
            enemies = [c for c in self.combatants if c.alive and c.team != actor.team]
            occupied = [c.position for c in self.combatants if c.alive and c is not actor]
            routes = self.board.paths(actor.position, occupied)
            # Pursue a reachable square adjacent to an enemy; path distance
            # lets AI navigate walls instead of oscillating by Manhattan distance.
            goals = [(p, path) for p, path in routes.items() if any(distance(p, e.position) == 1 for e in enemies)]
            moves = self.movement_paths(actor)
            if goals and moves:
                _, route = min(goals, key=lambda pair: (len(pair[1]), pair[0]))
                reachable = [p for p in route if p in moves]
                if reachable:
                    self.move(reachable[-1])
                    return
        if actions:
            action = self.rng.choice(attacks or actions)
            targets = self.targets(actor, definition(action))
            self.act(action, targets[0] if targets else None)
        else:
            self.wait()

    def act(self, action: str, target: Combatant | None = None) -> None:
        actor = self.active
        if actor is None or self.finished:
            raise RulesError("Call begin_turn() before acting in an unfinished battle")
        if action not in self.available_actions(actor):
            raise RulesError(f"Unavailable action: {action}")
        item_id = action[5:] if action.startswith("item:") else None
        aid = self.catalog["items"][item_id]["ability"] if item_id else action
        ability = self.catalog["abilities"][aid]
        mode = ability.get("target", "enemy")
        candidates = self.targets(actor, ability)
        if mode.startswith("all_") or mode == "self":
            if target is not None and target not in candidates:
                raise RulesError("Invalid target")
            selected = candidates
        else:
            if target not in candidates:
                raise RulesError("Choose a living target on the correct team")
            selected = [target]
        # All checks happen before resources, inventory, cooldowns, or RNG change.
        for key, amount in self.action_costs(ability).items():
            actor.resources[key] = max(0, round(actor.resources.get(key, 0) - amount, 8))
        if item_id:
            actor.inventory[item_id] -= 1
        self.log.append(f"{actor.name} uses {ability.get('name', aid)}.")
        accuracy = ability.get("accuracy")
        if accuracy:
            hit_targets = []
            for recipient in selected:
                chance = min(1, max(0, accuracy.get("base", 1)
                    + sum(actor.stat(k) * v for k, v in accuracy.get("attacker", {}).items())
                    - sum(recipient.stat(k) * v for k, v in accuracy.get("defender", {}).items())))
                if self.rng.random() < chance:
                    hit_targets.append(recipient)
                else:
                    self.log.append(f"{actor.name} misses {recipient.name} ({chance:.0%} hit chance).")
            selected = hit_targets
        for effect in ability.get("effects", []):
            recipients = [actor] if effect.get("recipient") == "self" else selected
            for recipient in recipients:
                if recipient.alive:
                    self._effect(effect, actor, recipient)
        if ability.get("cooldown", 0):
            actor.cooldowns[aid] = ability["cooldown"]
            self._turn_cooldowns.discard(aid)
        actor.clamp_resources()
        stunned = any(self.catalog["statuses"][s.id].get("skip_turn", False) for s in actor.statuses.values())
        if not self.catalog.get("rules", {}).get("stamina_per_turn", False) or self.finished or not actor.alive or stunned or (not self.available_actions(actor) and not self.movement_paths(actor)):
            self._end_turn()

    def wait(self) -> None:
        if self.active is None or self.finished:
            raise RulesError("No active turn")
        self.log.append(f"{self.active.name} ends their turn." if self.catalog.get("rules", {}).get("stamina_per_turn", False) else f"{self.active.name} waits.")
        self._end_turn()

    def _effect(self, effect: dict, source: Combatant, target: Combatant, *, multiplier: int = 1) -> None:
        chance = min(1, max(0, effect.get("chance", 1)
            + sum(source.stat(k) * v for k, v in effect.get("chance_scaling", {}).items())
            - sum(target.stat(k) * v for k, v in effect.get("resistance_scaling", {}).items())))
        if self.rng.random() >= chance:
            self.log.append(f"Effect misses {target.name}.")
            return
        kind = effect["kind"]
        amount = max(0, effect.get("power", 0) + sum(source.stat(k) * v for k, v in effect.get("scaling", {}).items())) * multiplier
        if kind == "damage":
            damage_type = effect.get("damage_type", "physical")
            type_definition = self.catalog.get("damage_types", {}).get(damage_type, {})
            group = type_definition.get("group")
            armor_stat = effect.get("armor_stat", type_definition.get("armor_stat", "armor" if damage_type == "physical" or group == "physical" else None))
            armor = target.stat(armor_stat) if armor_stat else 0
            damage = round(max(0, amount - armor) * (1 - target.resistance(damage_type)), 2)
            dealt = min(target.resources["hp"], damage)
            target.resources["hp"] -= dealt
            self.log.append(f"{target.name} takes {dealt:g} {damage_type} damage.")
            if not target.alive:
                self.log.append(f"{target.name} is defeated.")
        elif kind in {"heal", "restore"}:
            resource = "hp" if kind == "heal" else effect["resource"]
            current = target.resources.get(resource, 0)
            restored = max(0, min(amount, target.stat(f"max_{resource}") - current))
            target.resources[resource] = current + restored
            self.log.append(f"{target.name} recovers {restored:g} {resource}.")
        elif kind == "status":
            sid = effect["status"]
            definition = self.catalog["statuses"][sid]
            duration = effect.get("duration", definition.get("duration", 1))
            existing = target.statuses.get(sid)
            mode = definition.get("stacking", "refresh")
            if existing and mode != "replace":
                existing.remaining = max(existing.remaining, duration)
                existing.source = source
                if mode == "stack":
                    existing.stacks = min(definition.get("max_stacks", 1), existing.stacks + 1)
            else:
                target.statuses[sid] = StatusInstance(sid, duration, source)
            # A newly refreshed status gets its full future turn duration.
            self._turn_statuses = [s for s in self._turn_statuses if s is not target.statuses[sid]]
            target.clamp_resources()
            self.log.append(f"{target.name} gains {definition.get('name', sid)}.")
        elif kind == "cleanse":
            for sid in list(target.statuses):
                definition = self.catalog["statuses"][sid]
                if ("status" not in effect or effect["status"] == sid) and ("tag" not in effect or effect["tag"] in definition.get("tags", [])):
                    del target.statuses[sid]
                    self.log.append(f"{target.name} loses {definition.get('name', sid)}.")
            target.clamp_resources()

    def _end_turn(self) -> None:
        actor = self.active
        if actor is None:
            return
        for status in self._turn_statuses:
            if actor.statuses.get(status.id) is status:
                status.remaining -= 1
                if status.remaining <= 0:
                    del actor.statuses[status.id]
                    self.log.append(f"{status.id} expires on {actor.name}.")
        for aid in self._turn_cooldowns:
            actor.cooldowns[aid] -= 1
            if actor.cooldowns[aid] <= 0:
                del actor.cooldowns[aid]
        actor.clamp_resources()
        self.active = None
