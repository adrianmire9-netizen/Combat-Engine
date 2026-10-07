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
- **Battle arena:** control every team manually or click AI action for one automated
  action. Select an action and target, watch resources, cooldowns, statuses, and logs.

Definitions save in this browser's local storage. **Export JSON** downloads a
portable catalog; **Import** validates and replaces your catalog. Export for
backups, browser changes, or use with the CLI. Existing battles keep their starting
catalog; restart to apply edits. Battles are kept in server memory and are lost
when the server stops. The demo includes four characters and a playable encounter.

Every definition also has an advanced JSON editor for all supported fields.
Renaming IDs updates references; deleting referenced content is rejected. Validation
errors appear in the editor without discarding your edits. This is a local app,
not a hosted or multiplayer service. The AI uses the engine's simple action chooser.

## Tactical grid combat

The browser demo now starts on a 10×8 tactical grid. **Encounter** includes a map
editor: change dimensions (2–20 cells per axis), paint/erase walls, choose a unit
in the map-tool dropdown, and click its starting tile. **Save encounter & grid**
before testing. Unplaced units spawn automatically along opposing team edges.
Wide grids scroll horizontally on small screens; keep open routes between teams
when designing melee encounters.

In the arena, click **Move** to highlight reachable cells, hover or focus a tile to
preview its shortest path and stamina cost, then click to move. Choose an ability,
click a highlighted unit on the map (or use the target dropdown), and click **Use**.
**End turn** finishes early. **AI action** performs one attack or movement action;
it navigates around walls toward enemies.

- Movement is orthogonal. Walls and living units block paths; defeated units
  disappear from the board and their cells can be crossed.
- Tiles per turn = floor(base movement + speed × movement-speed scaling).
  A character `movement` stat overrides this formula. Modifiers to that stat work
  when the character defines it. The default is 3 + speed × 0.1.
- In stamina-budget turns, movement also costs stamina per step (default 0.5).
  Without stamina-budget rules, the tile allowance permits movement before the
  usual single ability action. Movement alone does not advance cooldowns/statuses.
- Ability range uses Manhattan distance, so diagonal neighbors are two tiles away.
  Default ranges are enemy 1, ally 3, self 0. The sample Fireball reaches 5 tiles.
  Ability editors expose **Range** and **Require line of sight**. Walls, including
  walls touched at a corner, block sight. Units do not block sight.
- Area abilities affect matching living units in range of the caster with sight,
  rather than the entire map. There is no ground-targeted blast radius yet.
- Map coordinates are zero-based `[x, y]`, with `(0, 0)` in the top left.
  Invalid positions, destinations, or targets do not spend resources.

Older catalogs keep their existing rules. Enable the grid in Encounter to use
existing characters with automatic placement, or export a backup and import
`examples/grid.json` for the complete tactical demo. `examples/guidelines.json`
remains the stat-system demo, and `examples/catalog.json` remains the legacy demo.
Catalog JSON export/import includes grid settings, walls, and starting positions.
Battle progress (including moved positions) remains temporary.

CLI: `python -m combat_engine --auto --data examples/grid.json --max-turns 300`.
Manual grid CLI prompts for `x,y` movement before abilities. Python API:
`Combatant(..., position=[1, 2])`, `battle.movement_paths(actor)`,
`battle.move([x, y])`, and `battle.auto_action()`.

## Added stat and damage guidelines

The browser demo now includes your Speed, Stamina, Species, Strength, Endurance,
Dexterity, Intelligence, Willpower, and Perception guidelines. Physical subtypes
are Blunt, Slash, Pierce, and Ballistic; Elemental subtypes are Fire, Cold, Shock,
and Acid; Exotic subtypes are Radiation and Poison.

Use **Species** to create creature categories with innate stats, resistances, and
traits. Assign a species in the character editor; equipment can restrict allowed
species. Use **System guidelines** to read/edit the attribute reference, damage
groups, initiative scaling, derived caps, and stamina turn rules. The ability
editor supports accuracy/dodge scaling; effect chance can scale from caster
attributes or be reduced by target attributes such as willpower.

The new default demo refills stamina each owner turn, allowing multiple actions.
Click **End turn** when you want to finish early, or **AI action** to automate one
action. Cooldowns and status durations advance once per owner turn. Existing
catalogs keep their old behavior until you enable the new rules. Browser-saved
catalogs receive the reference definitions without overwriting their characters.

To try the new presets on a saved catalog, export a backup, then import
`examples/guidelines.json`. The legacy demo remains `examples/catalog.json`.
See [GUIDELINES.md](GUIDELINES.md) for exact sample formulas and the distinction
between implemented mechanics and possible secondary uses from the source.

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

Species, equipment, and statuses accept `stat_bonuses` (additive) and `stat_multipliers`
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
Physical damage uses the target's `armor` stat by default. Registered physical subtypes also use armor. Other damage types
ignore armor unless you provide an `armor_stat` (e.g. `"magic_defense"`). Set
`armor_stat: null` to bypass armor, including for physical damage.

`resistances` maps any damage type to a fraction: `0.25` reduces damage by 25%,
`1` grants immunity, and `-0.5` increases damage by 50%. Character, species, equipment,
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

Living combatants receive one turn per round. Legacy catalogs sort by descending
speed; new catalogs use the editable initiative formula. Ties use roster order.
Legacy turns allow one action; stamina-budget turns allow multiple affordable
actions until ended voluntarily, no actions remain affordable, or the actor
is defeated or stunned. Speed changes affect the next round's ordering. Start-of-turn
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
