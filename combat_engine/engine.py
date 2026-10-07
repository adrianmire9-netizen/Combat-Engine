"""Data-driven combat with no runtime dependencies or executable data formulas."""

from __future__ import annotations

import copy
import json
import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any


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
    for section in ("abilities", "statuses", "items", "characters"):
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
            _number(value, f"{where}.{key}", minimum)

    def effects(values: list, where: str) -> None:
        if not isinstance(values, list):
            raise RulesError(f"{where} must be a list")
        for effect in values:
            if not isinstance(effect, dict) or effect.get("kind") not in EFFECTS:
                raise RulesError(f"Unknown effect in {where}: {effect}")
            if effect.get("recipient", "target") not in {"target", "self"}:
                raise RulesError(f"Invalid recipient in {where}")
            _number(effect.get("chance", 1), f"{where}.chance", 0)
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

    for aid, ability in data.get("abilities", {}).items():
        if aid.startswith("item:"):
            raise RulesError("Ability IDs cannot start with the reserved 'item:' prefix")
        if ability.get("target", "enemy") not in TARGETS:
            raise RulesError(f"Invalid target for {aid}")
        numeric_map(ability.get("costs", {}), f"{aid}.costs", 0)
        _integer(ability.get("cooldown", 0), f"{aid}.cooldown")
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
    for cid, char in data.get("characters", {}).items():
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
    def __init__(self, catalog: dict, character_id: str, team: str, *, name: str | None = None):
        template = copy.deepcopy(catalog["characters"][character_id])
        self.catalog = catalog
        self.character_id = character_id
        self.name = name or template.get("name", character_id)
        self.team = team
        self.base_stats = template["stats"]
        self.base_resistances = template.get("resistances", {})
        self.abilities = template.get("abilities", [])
        self.equipment = template.get("equipment", [])
        self.inventory = template.get("inventory", {})
        self.statuses: dict[str, StatusInstance] = {}
        self.cooldowns: dict[str, int] = {}
        self.resources = {key[4:]: self.stat(key) for key in self.base_stats if key.startswith("max_")}
        self.resources.update(template.get("resources", {}))
        self.clamp_resources()

    def modifiers(self):
        for iid in self.equipment:
            yield self.catalog["items"][iid], 1
        for status in self.statuses.values():
            yield self.catalog["statuses"][status.id], status.stacks

    def stat(self, key: str) -> float:
        value = self.base_stats.get(key, 0)
        modifiers = list(self.modifiers())
        value += sum(mod.get("stat_bonuses", {}).get(key, 0) * stacks for mod, stacks in modifiers)
        for mod, stacks in modifiers:
            value *= mod.get("stat_multipliers", {}).get(key, 1) ** stacks
        return max(1 if key == "max_hp" else 0, value)

    def resistance(self, damage_type: str) -> float:
        value = self.base_resistances.get(damage_type, 0)
        value += sum(mod.get("resistances", {}).get(damage_type, 0) * stacks for mod, stacks in self.modifiers())
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
                self._queue = sorted((c for c in self.combatants if c.alive), key=lambda c: -c.stat("speed"))
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
            stunned = any(self.catalog["statuses"][s.id].get("skip_turn", False) for s in actor.statuses.values())
            if not actor.alive or stunned or self.finished:
                if stunned and actor.alive:
                    self.log.append(f"{actor.name} cannot act.")
                self._end_turn()
                continue
            return actor
        return None

    def available_actions(self, actor: Combatant) -> list[str]:
        actions = list(actor.abilities) + [f"item:{iid}" for iid, count in actor.inventory.items() if count > 0]
        result = []
        for action in actions:
            aid = self.catalog["items"][action[5:]]["ability"] if action.startswith("item:") else action
            ability = self.catalog["abilities"][aid]
            if actor.cooldowns.get(aid, 0) == 0 and all(actor.resources.get(k, 0) >= v for k, v in ability.get("costs", {}).items()):
                result.append(action)
        return result

    def targets(self, actor: Combatant, ability: dict) -> list[Combatant]:
        mode = ability.get("target", "enemy")
        if mode == "self":
            return [actor] if actor.alive else []
        allies = mode in {"ally", "all_allies"}
        return [c for c in self.combatants if c.alive and (c.team == actor.team) == allies]

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
        for key, amount in ability.get("costs", {}).items():
            actor.resources[key] = actor.resources.get(key, 0) - amount
        if item_id:
            actor.inventory[item_id] -= 1
        self.log.append(f"{actor.name} uses {ability.get('name', aid)}.")
        for effect in ability.get("effects", []):
            recipients = [actor] if effect.get("recipient") == "self" else selected
            for recipient in recipients:
                if recipient.alive:
                    self._effect(effect, actor, recipient)
        if ability.get("cooldown", 0):
            actor.cooldowns[aid] = ability["cooldown"]
            self._turn_cooldowns.discard(aid)
        self._end_turn()

    def wait(self) -> None:
        if self.active is None or self.finished:
            raise RulesError("No active turn")
        self.log.append(f"{self.active.name} waits.")
        self._end_turn()

    def _effect(self, effect: dict, source: Combatant, target: Combatant, *, multiplier: int = 1) -> None:
        if self.rng.random() >= effect.get("chance", 1):
            self.log.append(f"Effect misses {target.name}.")
            return
        kind = effect["kind"]
        amount = max(0, effect.get("power", 0) + sum(source.stat(k) * v for k, v in effect.get("scaling", {}).items())) * multiplier
        if kind == "damage":
            damage_type = effect.get("damage_type", "physical")
            armor_stat = effect.get("armor_stat", "armor" if damage_type == "physical" else None)
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
