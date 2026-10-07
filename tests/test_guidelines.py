import copy
import unittest
from pathlib import Path
from combat_engine import Battle, Combatant, RulesError, load_catalog
from combat_engine.engine import validate_catalog


class GuidelineTests(unittest.TestCase):
    def setUp(self):
        self.data = load_catalog(Path(__file__).parents[1] / 'examples/guidelines.json')
        # Minimal deterministic actions so budget/armor tests don't depend on hits.
        self.data['abilities']['test_hit'] = {'target': 'enemy', 'effects': [{'kind': 'damage', 'power': 5, 'damage_type': 'slash'}]}
        for d in self.data['characters'].values():
            d['abilities'] = ['test_hit']
            d['inventory'] = {}
        self.data['characters']['knight']['stats'].update(speed=100, stamina=3, max_stamina=0, endurance=0)
        self.hero = Combatant(self.data, 'knight', 'heroes')
        self.foe = Combatant(self.data, 'brute', 'enemies')
        self.battle = Battle(self.data, [self.hero, self.foe], seed=7)

    def test_stamina_multiple_actions_and_refill(self):
        self.assertIs(self.battle.begin_turn(), self.hero)
        self.battle.act('test_hit', self.foe)
        self.assertIs(self.battle.active, self.hero)
        self.assertEqual(self.hero.resources['stamina'], 2)
        self.battle.act('test_hit', self.foe)
        self.assertIs(self.battle.active, self.hero)
        self.battle.act('test_hit', self.foe)
        self.assertIsNone(self.battle.active)
        self.assertIs(self.battle.begin_turn(), self.foe)
        self.battle.wait()
        self.assertIs(self.battle.begin_turn(), self.hero)
        self.assertEqual(self.hero.resources['stamina'], 3)

    def test_explicit_stamina_cost_overrides_default(self):
        self.data['rules']['default_action_cost'] = 2
        self.data['abilities']['test_hit']['costs'] = {'stamina': 1.5}
        self.battle.begin_turn()
        self.battle.act('test_hit', self.foe)
        self.assertEqual(self.hero.resources['stamina'], 1.5)
        self.battle.act('test_hit', self.foe)
        self.assertIsNone(self.battle.active)

    def test_invalid_target_does_not_spend_budget(self):
        self.battle.begin_turn()
        before = copy.deepcopy(self.hero.resources)
        with self.assertRaises(RulesError):
            self.battle.act('test_hit', self.hero)
        self.assertEqual(self.hero.resources, before)
        self.assertIs(self.battle.active, self.hero)

    def test_cooldown_and_status_expire_per_turn_not_per_action(self):
        self.data['abilities']['guard']['action_cost'] = 1
        self.hero.abilities.append('guard')
        self.data['abilities']['test_hit']['cooldown'] = 2
        self.battle.begin_turn()
        self.battle.act('guard')
        self.battle.act('test_hit', self.foe)
        self.assertEqual(self.hero.statuses['guarded'].remaining, 1)
        self.assertEqual(self.hero.cooldowns['test_hit'], 2)
        self.battle.wait()
        self.battle.begin_turn(); self.battle.wait(); self.battle.begin_turn()
        self.battle.act('guard')
        self.assertEqual(self.hero.cooldowns['test_hit'], 2)
        self.battle.wait()
        self.assertEqual(self.hero.cooldowns['test_hit'], 1)

    def test_derived_stats_and_species_modifiers(self):
        d=self.data['characters']['knight']
        d['stats']['endurance'] = 10
        self.data['species']['human']['stat_bonuses']['endurance'] = 2
        self.data['species']['human']['stat_multipliers'] = {'max_hp': 2}
        c=Combatant(self.data,'knight','heroes')
        self.assertEqual(c.stat('max_hp'), (d['stats']['max_hp']+12*2)*2)
        self.assertAlmostEqual(c.stat('max_stamina'), 4.2)
        self.assertEqual(c.resources['hp'],c.stat('max_hp'))

    def test_perception_changes_initiative(self):
        self.hero.base_stats.update(speed=10,perception=1)
        self.foe.base_stats.update(speed=9,perception=20)
        self.assertIs(self.battle.begin_turn(),self.foe)

    def test_species_equipment_restrictions(self):
        self.data['items']['mail']['allowed_species']=['ogre']
        with self.assertRaisesRegex(RulesError,'species cannot equip'):
            validate_catalog(self.data)
        self.data['items']['mail']['allowed_species']=['human']
        validate_catalog(self.data)
        self.data['characters']['knight']['species']='unknown'
        with self.assertRaisesRegex(RulesError,'unknown species'):
            validate_catalog(self.data)

    def test_physical_subtypes_and_group_resistance(self):
        self.foe.base_stats['armor']=2
        self.foe.base_resistances={'physical':0.2,'slash':0.3}
        self.data['species']['ogre']['resistances']={'physical':0.1}
        self.assertAlmostEqual(self.foe.resistance('slash'),0.6)
        self.assertAlmostEqual(self.foe.resistance('pierce'),0.3)
        before=self.foe.resources['hp']
        self.battle.begin_turn();self.battle.act('test_hit',self.foe)
        self.assertAlmostEqual(before-self.foe.resources['hp'],1.2)

    def test_elemental_group_immunity_and_armor_override(self):
        self.foe.base_resistances={'elemental':1}
        self.data['abilities']['test_hit']['effects'][0]['damage_type']='shock'
        before=self.foe.resources['hp']
        self.battle.begin_turn();self.battle.act('test_hit',self.foe)
        self.assertEqual(before,self.foe.resources['hp'])
        self.foe.base_resistances={}
        self.data['abilities']['test_hit']['effects'][0].update(damage_type='ballistic',armor_stat=None)
        self.battle.act('test_hit',self.foe)
        self.assertEqual(before-self.foe.resources['hp'],5)

    def test_accuracy_and_willpower_resistance(self):
        a=self.data['abilities']['test_hit']
        a['accuracy']={'base':0,'attacker':{},'defender':{}}
        before=self.foe.resources['hp']
        self.battle.begin_turn();self.battle.act('test_hit',self.foe)
        self.assertEqual(before,self.foe.resources['hp'])
        self.assertTrue(any('misses' in line for line in self.battle.log))
        a['accuracy']={'base':0,'attacker':{'intelligence':1},'defender':{}}
        a['effects']=[{'kind':'status','status':'stun','resistance_scaling':{'willpower':1}}]
        self.battle.act('test_hit',self.foe)
        self.assertNotIn('stun',self.foe.statuses)
        self.foe.base_stats['willpower']=0
        self.battle.act('test_hit',self.foe)
        self.assertIn('stun',self.foe.statuses)

    def test_self_stun_ends_multiaction_turn_immediately(self):
        self.data['abilities']['self_stun']={'target':'self','effects':[{'kind':'status','status':'stun'}]}
        self.hero.abilities.append('self_stun')
        self.battle.begin_turn();self.battle.act('self_stun')
        self.assertIsNone(self.battle.active)
        self.assertGreater(self.hero.resources['stamina'],0)
        self.assertIs(self.battle.begin_turn(),self.foe)

    def test_missed_target_preserves_caster_only_effect(self):
        self.data['abilities']['test_hit']['accuracy']={'base':0}
        self.data['abilities']['test_hit']['effects'].append({'kind':'status','status':'guarded','recipient':'self'})
        self.battle.begin_turn();self.battle.act('test_hit',self.foe)
        self.assertIn('guarded',self.hero.statuses)
        self.assertEqual(self.foe.resources['hp'],self.foe.stat('max_hp'))

    def test_invalid_new_rules_are_rejected(self):
        for apply in [lambda d:d['rules'].update(derived_stats={'endurance':{'endurance':1}}),lambda d:d['damage_types']['slash'].update(group='nope'),lambda d:d['abilities']['test_hit'].update(accuracy={'base':2}),lambda d:d['rules'].update(default_action_cost=0),lambda d:d['stat_definitions']['strength'].update(secondary_uses='bad')]:
            d=copy.deepcopy(self.data);apply(d)
            with self.assertRaises(RulesError):validate_catalog(d)

    def test_demo_finishes_with_multiaction_ai(self):
        from test_web import WebTests
        api=WebTests();api.setUp();api.catalog=load_catalog(Path(__file__).parents[1]/'examples/guidelines.json')
        state=api.start()
        for _ in range(300):
            if state['finished']:break
            status,state=api.post('/api/action',{'session':state['session'],'action':'auto'})
            self.assertEqual(status,200)
        self.assertTrue(state['finished'])
        self.assertTrue(state['stamina_per_turn'])
        self.assertIn('species',state['combatants'][0])
