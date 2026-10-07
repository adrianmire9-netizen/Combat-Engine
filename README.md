# Custom Combat Engine

A customizable turn-based combat engine in Python, with a browser content editor
and playable battle arena. Define your game through forms or JSON, then test it
with the same engine used by the terminal and Python API.
Requires Python 3.10+; no runtime dependencies, services, or credentials.

## Browser UI — Combat Foundry

From this checkout, run:

```sh
python START_UI.py
```

This starts a local server and opens `http://127.0.0.1:8765` in your browser.
Alternatively use `python -m combat_engine.web` and open that address yourself.
Keep the terminal running; press Ctrl+C to stop. Python 3.10+ is required. No
additional packages or internet connection are needed. If port 8765 is occupied,
use `python -m combat_engine.web --port 8766` and open port 8766 instead.

- **Characters:** create templates, arbitrary stats and resources, typed
  resistances, ability lists, equipment loadouts, and consumable quantities.
- **Abilities:** build ordered effects with damage, healing, resource restoration,
  statuses, and cleanse. Configure targeting, costs, cooldowns, scaling, and chance.
- **Items & armor:** create equipment for any slot with bonuses, multipliers, and
  resistances, or consumables linked to an ability.
- **Statuses:** configure duration, stacking, stun, tags, modifiers, and ticking effects.
- **Encounter:** choose character instances, names, and teams. Save the encounter
  before starting a battle. A character template can appear more than once.
- **Battle arena:** control every team manually or click AI turn for one automated
  turn. Select an action and target, watch resources, cooldowns, statuses, and logs.

Definitions save in this browser's local storage. **Export JSON** downloads a
portable catalog; **Import** validates and replaces your catalog. Export for
backups, browser changes, or use with the CLI. Existing battles keep their starting
catalog; restart to apply edits. Battles are kept in server memory and are lost
when the server stops. The demo includes four characters and a playable encounter.

Every definition also has an advanced JSON editor for all supported fields.
Renaming IDs updates references; deleting referenced content is rejected. Validation
errors appear in the editor without discarding your edits. This is a local app,
not a hosted or multiplayer service. The AI uses the engine's simple action chooser.

## Terminal demo

From this checkout:

```sh
python -m combat_engine
python -m combat_engine --auto --seed 7
python -m unittest discover -s tests -v
```

The demo includes a knight and mage versus a goblin and brute. You control the
first team; enemies use a simple AI. Choose numbered actions and targets, or `0`
to wait. For your own content:

```sh
python -m combat_engine --data path/to/your-catalog.json
```

## Create and customize content

Edit [examples/catalog.json](examples/catalog.json), or copy it into your own file.
Each section is a dictionary keyed by an ID you choose. IDs connect definitions;
`name` is an optional display label. There is no fixed set of damage types or stats.

| Section | What you define |
| --- | --- |
| `characters` | Base stats, starting resources, learned abilities, equipment, inventory, resistances |
| `abilities` | Targeting, resource costs, cooldown, ordered effects |
| `items` | Equipment with a slot and modifiers, or consumables that invoke an ability |
| `statuses` | Duration, bonuses/multipliers, resistances, ticking effects, stacking, stun |
| `battle` | List of `{ "character": "id", "team": "team-name" }`; optional `name` for duplicates |

### Stats and resources

Every character needs `stats.max_hp >= 1`. Common stats are `attack`, `magic`,
`armor`, and `speed`; add any others, such as `luck`, `strength`, or `holy_power`.
Missing stats default to zero.

`max_mana`, `max_stamina`, or any `max_NAME` defines a resource called `NAME`.
Resources start full unless overridden in the character's `resources` object.
Ability `costs` spend those resources. Resources do not regenerate automatically;
use restore effects or a ticking status. HP is the resource that determines defeat.

Equipment and statuses accept `stat_bonuses` (additive) and `stat_multipliers`
(multiplicative). Bonuses apply first, then multipliers. Stats are clamped to
zero, except max HP, which has a minimum of one. Resource caps follow modified
stats; reducing a cap clamps the current resource and does not refund it later.

### Abilities and effects

```json
{
  "name": "Frost Lance",
  "target": "enemy",
  "costs": {"mana": 5},
  "cooldown": 1,
  "effects": [
    {"kind": "damage", "damage_type": "ice", "power": 10, "scaling": {"magic": 1.5}},
    {"kind": "status", "status": "chilled", "chance": 0.75}
  ]
}
```

Add this under a new ID in `abilities`, define `chilled` in `statuses`, and add
the ability ID to a character's `abilities` list.

Targets: `enemy`, `ally` (includes self), `self`, `all_enemies`, `all_allies`.
Targets must be living combatants. Effects run in order; defeated targets receive
no further effects. Each effect can specify `recipient: "self"` to affect the
caster once, even in an area ability. `chance` is a probability from 0 to 1,
rolled separately for each effect and recipient.

| Effect `kind` | Fields |
| --- | --- |
| `damage` | `power`, `scaling`, `damage_type`, optional `armor_stat` |
| `heal` | `power`, `scaling`; restores HP up to its cap |
| `restore` | `resource`, `power`, `scaling` |
| `status` | `status` ID, optional `duration` override |
| `cleanse` | Optional `status` ID and/or `tag`; omitted filters remove all statuses |

Amount = `max(0, power + sum(caster stat × scaling coefficient))`. Data uses
numeric coefficients rather than executable expressions. Extend effect handling
in `engine.py` if you need new mechanics such as resurrection or summons.

Damage = `max(0, amount - armor) × (1 - resistance)`, rounded to two decimals.
Physical damage uses the target's `armor` stat by default. Other damage types
ignore armor unless you provide an `armor_stat` (e.g. `"magic_defense"`). Set
`armor_stat: null` to bypass armor, including for physical damage.

`resistances` maps any damage type to a fraction: `0.25` reduces damage by 25%,
`1` grants immunity, and `-0.5` increases damage by 50%. Character, equipment,
and status resistances add together and clamp to [-1, 1]. Unknown types use zero.

### Equipment, inventory, and statuses

Equipment uses `kind: "equipment"`, an arbitrary `slot` name, and optional
stat/resistance modifiers. A character's `equipment` list can contain one item
per slot. Loadouts are configured before combat; there is no equip action yet.
Consumables use `kind: "consumable"` and an `ability` ID; character `inventory`
maps item IDs to counts. Using one consumes a count and applies the referenced
ability's usual targeting, costs, and cooldown.

Statuses support:

- `duration`: number of affected owner turns, minimum one.
- `tick_effects`: damage, heal, or restore at the start of each owner turn;
  scaling uses the latest applier's current stats, even if the applier is defeated.
- `skip_turn: true`: prevents actions while allowing ticks and expiration.
- `stacking`: `refresh` (default), `replace`, or `stack` with `max_stacks`.
  Refresh/stack retains the longer remaining duration; replace creates a new instance.
- `stat_bonuses`, `stat_multipliers`, `resistances`, and arbitrary `tags` for cleanse.

Stacked bonuses, resistances, and tick amounts multiply by stack count; stat
multipliers are raised to that count. A newly applied/refreshed status gets its
full duration over future owner turns. Existing statuses expire at the end of
their owner's turn. A one-turn self guard therefore covers incoming attacks
until the end of the caster's next turn. There is no built-in status immunity.

### Turn rules

Living combatants act once per round, sorted by descending speed; equal speeds
use roster order. Speed changes affect the next round's ordering. Start-of-turn
status ticks happen before actions. A cooldown of N blocks the next N owner
turns, counting skipped or waited turns. Invalid actions raise `RulesError`
without consuming a turn or changing resources. Battle ends when at most one
team has living members; if no one survives, the result is a draw.

The terminal demo has a turn limit to stop stalled battles. AI is deliberately
basic and does not strategically heal, conserve resources, or select targets.

## Use the engine in your own game

```python
from combat_engine import Battle, Combatant, load_catalog

data = load_catalog("examples/catalog.json")
hero = Combatant(data, "knight", "heroes")
enemy = Combatant(data, "goblin", "monsters")
battle = Battle(data, [hero, enemy], seed=7)

actor = battle.begin_turn()   # Processes ticks and skips stunned/dead actors.
if actor is not None:
    target = enemy if actor is hero else hero
    battle.act("slash", target)
print("\n".join(battle.log))
```

Repeat `begin_turn()` followed by `act()` or `wait()` until `battle.finished`.
Query `available_actions(actor)`, `targets(actor, ability)`, resources, statuses,
and `battle.log` for UI. `battle.winner` returns the winning team or `None`.
Pass different names to `Combatant(..., name="Goblin A")` for duplicate templates;
each instance has independent resources, equipment lists, inventory, and statuses.
Treat catalog definitions as immutable during a battle. When supplying dictionaries
directly rather than loading JSON, call `validate_catalog` before constructing
characters. The browser UI provides a graphical editor, JSON import/export, and browser-local catalog persistence.
