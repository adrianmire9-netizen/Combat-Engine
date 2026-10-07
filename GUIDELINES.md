# Stats and damage guidelines

The source attachment specifies primary purposes and **possible** secondary uses;
it does not supply numeric formulas. The new demo uses editable sample formulas.

| Attribute | Primary purpose | Possible secondary uses |
| --- | --- | --- |
| Speed | Initiative/order | Dodge, Movement, Reaction attacks |
| Stamina | Actions per turn | Sprinting, Blocking, Special actions |
| Species | Creature category | Resistances, Equipment restrictions, Special traits |
| Strength | Physical power | Melee damage, Carrying, Knockback |
| Endurance | Physical durability | HP, Stamina, Physical resistance |
| Dexterity | Precision | Accuracy, Ranged attacks, Dodge |
| Intelligence | Mental capability | Tech/magic accuracy, Abilities |
| Willpower | Mental resilience | Mental resistance, Status effects |
| Perception | Awareness | Initiative, Accuracy, Detecting things |

Species is a category, not a numeric stat. Create species in the library and
assign them to characters. Species bonuses and multipliers modify stats;
resistances add to character, equipment, and status resistances. Traits are
descriptive labels. Equipment `allowed_species` lists restrict loadouts;
an empty list permits all species, including characters without a species.

Damage groups:
- Physical: Blunt, Slash, Pierce, Ballistic.
- Elemental: Fire, Cold, Shock, Acid.
- Exotic: Radiation, Poison.

A group resistance adds to the subtype resistance. Physical subtype damage uses
armor by default. Elemental and exotic damage bypass armor unless configured.
Each type can set `armor_stat`; an effect can override it, with null bypassing
armor. Custom types remain supported.

## Editable sample mechanics

The default browser demo and `examples/guidelines.json` enable:
- Initiative = speed + perception × 0.25. Equal values use roster order.
- HP cap = base max_hp + endurance × 2.
- Stamina cap = base max_stamina + stamina × 1 + endurance × 0.1.
- Stamina refills at the start of each owner turn, after status ticks. Each action
  spends `costs.stamina`, or `action_cost`, or the system's default action cost
  (1). The explicit cost replaces the default; they are not added. A minimum
  0.01 cost prevents completely free actions. Turns remain active while there
  are affordable abilities/items. End turn voluntarily with the arena button.
  Cooldowns and status durations advance at the end of an owner turn, not after
  each action. A self-stun takes effect immediately and ends the active turn.
- Strength scales sample melee attacks; intelligence scales magic/healing.
- Sword Slash and Fireball have editable accuracy formulas. One hit roll per
  target gates the ordered target effects; caster-only effects still resolve.
  Accuracy = clamp(base + attacker coefficients − defender coefficients, 0, 1).
- Shield Bash and Venom status chance is reduced by target willpower × 0.01.
  Effect chance = clamp(base chance + caster chance_scaling − target
  resistance_scaling, 0, 1). This also supports mental resistance and other
  attribute-based status protection without fixed stat names.

Species and stat/damage definitions, initiative, derived scaling, and the action
budget can be edited in the UI. Precision formulas and effect chance scaling are
available in the ability/effect editor. Derived stats must use base attributes,
not other derived stats, to prevent cycles.

Movement, detection, carrying, knockback, sprinting, and reaction attacks are
recorded as possible design uses; this arena has no spatial or exploration
system for them. Blocking is available through armor/resistance status effects.
Create ranged damage using dexterity scaling and a pierce/ballistic damage type.

Existing catalogs without new rules retain one action per turn, persistent
resource pools, speed-only initiative, and their previous damage formulas.
The legacy `examples/catalog.json` remains available. Browser-saved catalogs
receive the reference definitions but do not automatically enable new formulas;
use System guidelines to configure rules, or import `examples/guidelines.json`.
Export your catalog before replacing it.
