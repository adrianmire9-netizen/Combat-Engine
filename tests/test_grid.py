import copy
import unittest
from pathlib import Path
from combat_engine import Battle, Combatant, RulesError, load_catalog
from combat_engine.engine import validate_catalog
from combat_engine.grid import Board


class GridTests(unittest.TestCase):
    def setUp(self):
        self.data = {
            'rules': {'stamina_per_turn': True},
            'grid': {'enabled': True, 'width': 7, 'height': 5, 'blocked': [], 'movement_base': 4, 'movement_speed_scaling': 0, 'move_stamina_cost': 0.5},
            'characters': {
                'hero': {'stats': {'max_hp': 100, 'max_stamina': 5, 'speed': 10}, 'abilities': ['hit', 'shot']},
                'enemy': {'stats': {'max_hp': 100, 'max_stamina': 5, 'speed': 5}, 'abilities': ['hit']},
            },
            'abilities': {
                'hit': {'range': 1, 'target': 'enemy', 'effects': [{'kind': 'damage', 'power': 10}]},
                'shot': {'range': 4, 'target': 'enemy', 'effects': [{'kind': 'damage', 'power': 10}]},
            }, 'items': {}, 'statuses': {},
        }
        self.hero = Combatant(self.data, 'hero', 'a', position=[0, 2])
        self.enemy = Combatant(self.data, 'enemy', 'b', position=[6, 2])
        self.battle = Battle(self.data, [self.hero, self.enemy], seed=7)
        self.battle.begin_turn()

    def test_move_shortest_path_and_stamina(self):
        self.battle.move([3,2])
        self.assertEqual(self.hero.position,(3,2))
        self.assertEqual(self.hero.movement_remaining,1)
        self.assertEqual(self.hero.resources['stamina'],3.5)
        self.assertIs(self.battle.active,self.hero)
        self.assertIn('shot',self.battle.available_actions(self.hero))
        self.assertNotIn('hit',self.battle.available_actions(self.hero))
        self.battle.act('shot',self.enemy)
        self.assertEqual(self.enemy.resources['hp'],90)

    def test_wall_detour_costs_actual_path_length(self):
        self.battle.board.walls={(1,2)}
        paths=self.battle.movement_paths(self.hero)
        self.assertEqual(len(paths[(2,2)]),4)
        self.battle.move([2,2])
        self.assertEqual(self.hero.resources['stamina'],3)
        self.assertEqual(self.hero.movement_remaining,0)

    def test_invalid_moves_leave_everything_unchanged(self):
        self.battle.board.walls={(1,2)}
        for destination in [[1,2],[6,2],[-1,0],[0,2],[5,0],[1.1,2],[True,2],None]:
            before=(self.hero.position,dict(self.hero.resources),self.hero.movement_remaining,list(self.battle.log),self.battle.rng.getstate())
            with self.assertRaises(RulesError):self.battle.move(destination)
            self.assertEqual(before,(self.hero.position,self.hero.resources,self.hero.movement_remaining,self.battle.log,self.battle.rng.getstate()))

    def test_living_units_block_path_and_dead_units_do_not(self):
        board=Board({'width':5,'height':2,'blocked':[[x,1] for x in range(5)]})
        self.battle.board=board
        self.hero.position=(0,0);self.enemy.position=(1,0)
        self.assertNotIn((2,0),self.battle.movement_paths(self.hero))
        other=Combatant(self.data,'enemy','b',position=[4,0]);self.battle.combatants.append(other)
        self.enemy.resources['hp']=0
        self.assertIn((2,0),self.battle.movement_paths(self.hero))

    def test_range_and_sight_reject_without_mutation(self):
        before=dict(self.hero.resources)
        with self.assertRaises(RulesError):self.battle.act('hit',self.enemy)
        self.assertEqual(before,self.hero.resources)
        self.enemy.position=(3,2)
        self.battle.board.walls={(1,2)}
        self.assertNotIn(self.enemy,self.battle.targets(self.hero,self.data['abilities']['shot']))
        with self.assertRaises(RulesError):self.battle.act('shot',self.enemy)
        self.assertEqual(before,self.hero.resources)
        self.data['abilities']['shot']['line_of_sight']=False
        self.battle.act('shot',self.enemy)
        self.assertEqual(self.enemy.resources['hp'],90)

    def test_sight_corner_and_diagonal_distance(self):
        board=Board({'width':5,'height':5,'blocked':[[1,0]]})
        self.assertFalse(board.visible((0,0),(1,1)))
        self.assertFalse(board.visible((0,0),(3,0)))
        self.assertTrue(board.visible((0,0),(0,3)))
        self.hero.position=(2,2);self.enemy.position=(3,3)
        self.assertNotIn(self.enemy,self.battle.targets(self.hero,self.data['abilities']['hit']))

    def test_area_ability_only_hits_matching_units_in_range(self):
        self.data['abilities']['hit'].update(target='all_enemies',range=2)
        self.hero.position=(2,2);self.enemy.position=(3,2)
        distant=Combatant(self.data,'enemy','b',position=[6,4]);ally=Combatant(self.data,'hero','a',position=[2,1])
        self.battle.combatants.extend([distant,ally])
        self.battle.act('hit')
        self.assertEqual(self.enemy.resources['hp'],90)
        self.assertEqual(distant.resources['hp'],100)
        self.assertEqual(ally.resources['hp'],100)

    def test_move_budget_and_stamina_reset_per_owner_turn(self):
        self.battle.move([2,2]);self.battle.wait();self.battle.begin_turn();self.battle.wait()
        self.assertIs(self.battle.begin_turn(),self.hero)
        self.assertEqual(self.hero.movement_remaining,4)
        self.assertEqual(self.hero.resources['stamina'],5)
        self.hero.resources['stamina']=0.5
        self.assertNotIn((4,2),self.battle.movement_paths(self.hero))
        self.battle.move([3,2])
        self.assertIsNone(self.battle.active)

    def test_explicit_movement_stat_and_legacy_move_then_attack(self):
        self.data['rules']['stamina_per_turn']=False
        self.hero.base_stats['movement']=2
        self.battle.wait();self.battle.begin_turn();self.battle.wait();self.battle.begin_turn()
        self.assertEqual(self.hero.movement_remaining,2)
        self.enemy.position=(3,2)
        before=self.hero.resources['stamina'];self.battle.move([2,2])
        self.assertEqual(before,self.hero.resources['stamina'])
        self.battle.act('hit',self.enemy)
        self.assertIsNone(self.battle.active)

    def test_automatic_placement_and_invalid_starts(self):
        units=[Combatant(self.data,'hero','a') for _ in range(3)]+[Combatant(self.data,'enemy','b') for _ in range(3)]
        b=Battle(self.data,units)
        self.assertEqual(len({u.position for u in units}),6)
        self.assertTrue(all(u.position[0]==0 for u in units[:3]))
        self.assertTrue(all(u.position[0]==6 for u in units[3:]))
        for pos in [[0,2],[7,0],[0.5,2]]:
            with self.assertRaises(RulesError):Battle(self.data,[Combatant(self.data,'hero','a',position=[0,2]),Combatant(self.data,'enemy','b',position=pos)])

    def test_invalid_grid_catalogs(self):
        mutations=[lambda d:d['grid'].update(width=21),lambda d:d['grid'].update(blocked=[[1,2],[1,2]]),lambda d:d['grid'].update(move_stamina_cost=-1),lambda d:d['abilities']['hit'].update(range=-1),lambda d:d['abilities']['hit'].update(line_of_sight='yes'),lambda d:d.update(battle=[{'character':'hero','team':'a','position':[0,0]},{'character':'enemy','team':'b','position':[0,0]}]),lambda d:d['grid'].update(blocked=[[True,1]])]
        for mutation in mutations:
            data=copy.deepcopy(self.data);mutation(data)
            with self.assertRaises(RulesError):validate_catalog(data)

    def test_disabled_grid_still_validates_coordinate_shape(self):
        self.data['grid']['enabled']=False
        self.data['battle']=[{'character':'hero','team':'a','position':{'x':0,'y':1}}]
        with self.assertRaisesRegex(RulesError,'integer coordinates'):
            validate_catalog(self.data)

    def test_ai_navigates_detour_and_finishes(self):
        self.battle.board.walls={(2,y) for y in range(1,5)}
        positions=[]
        for _ in range(150):
            actor=self.battle.begin_turn()
            if actor is None:break
            self.battle.auto_action();positions.append(self.hero.position)
        self.assertTrue(self.battle.finished)
        self.assertTrue(any(p[1]==0 for p in positions))
        self.assertTrue(any('moves' in line for line in self.battle.log))

    def test_grid_api_positions_moves_and_legacy_sessions(self):
        from test_web import WebTests
        api=WebTests();api.setUp()
        api.catalog=load_catalog(Path(__file__).parents[1]/'examples/grid.json')
        state=api.start();actor=state['active']
        self.assertEqual(state['combatants'][actor]['position'],(1,5))
        move=next(m for m in state['grid']['reachable'] if m['position']==(2,5))
        status,after=api.post('/api/action',{'session':state['session'],'action':'move','destination':[2,5]})
        self.assertEqual(status,200)
        self.assertEqual(after['combatants'][actor]['position'],(2,5))
        self.assertEqual(after['active'],actor)
        status,error=api.post('/api/action',{'session':state['session'],'action':'move','destination':[4,5]})
        self.assertEqual(status,400)
        for _ in range(300):
            if after['finished']:break
            status,after=api.post('/api/action',{'session':state['session'],'action':'auto'})
            self.assertEqual(status,200)
        self.assertTrue(after['finished'])
        api.setUp();legacy=api.start()
        self.assertIsNone(legacy['grid'])
