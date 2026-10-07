"""Exercise the UI API without binding a network socket."""
import copy
import io
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from combat_engine.web import Handler, SESSIONS


class WebTests(unittest.TestCase):
    def setUp(self):
        SESSIONS.clear()
        self.catalog = json.loads((Path(__file__).parents[1] / 'combat_engine/demo.json').read_text())

    def post(self, path, data, origin=None):
        body = json.dumps(data).encode()
        h = Handler.__new__(Handler)
        h.path = path
        h.headers = {'Content-Type': 'application/json', 'Content-Length': str(len(body)), 'Host': '127.0.0.1:8765'}
        if origin:
            h.headers['Origin'] = origin
        h.rfile = io.BytesIO(body)
        h.server = SimpleNamespace(catalog=self.catalog)
        result = []
        h.reply = lambda status, payload: result.append((status, copy.deepcopy(payload)))
        h.do_POST()
        return result[0]

    def start(self):
        status, battle = self.post('/api/start', {'catalog': self.catalog})
        self.assertEqual(status, 200)
        return battle

    def test_targeted_action_and_invalid_target_preserve_turn(self):
        battle = self.start()
        self.assertEqual(battle['combatants'][battle['active']]['name'], 'Mage')
        session = battle['session']
        status, _ = self.post('/api/action', {'session': session, 'action': 'fireball', 'target': 0})
        self.assertEqual(status, 400)
        self.assertEqual(SESSIONS[session].active.resources['mana'], 30)
        status, next_turn = self.post('/api/action', {'session': session, 'action': 'fireball', 'target': 2})
        self.assertEqual(status, 200)
        self.assertLess(next_turn['combatants'][2]['resources']['hp'], 55)
        self.assertEqual(next_turn['combatants'][1]['resources']['mana'], 24)

    def test_separate_sessions_and_complete_ai_battle(self):
        one, two = self.start(), self.start()
        self.assertNotEqual(one['session'], two['session'])
        for _ in range(200):
            if one['finished']:
                break
            status, one = self.post('/api/action', {'session': one['session'], 'action': 'auto'})
            self.assertEqual(status, 200)
        self.assertTrue(one['finished'])
        self.assertEqual(SESSIONS[two['session']].active.name, 'Mage')
        self.assertEqual(SESSIONS[two['session']].combatants[2].resources['hp'], 55)

    def test_catalog_validation_and_cross_origin_rejection(self):
        self.catalog['characters']['knight']['equipment'].append('missing')
        status, error = self.post('/api/validate', {'catalog': self.catalog})
        self.assertEqual(status, 400)
        self.assertIn('unknown equipment', error['error'])
        status, _ = self.post('/api/start', {}, 'https://other.example')
        self.assertEqual(status, 403)

    def test_snapshot_exposes_item_costs_statuses_and_cooldowns(self):
        b = self.start()
        self.assertTrue(any(a['id'] == 'item:potion' for a in b['actions']))
        _, b = self.post('/api/action', {'session': b['session'], 'action': 'fireball', 'target': 2})
        for _ in range(3):
            _, b = self.post('/api/action', {'session': b['session'], 'action': 'wait'})
        fire = next(a for a in b['actions'] if a['id'] == 'fireball')
        self.assertFalse(fire['available'])
        self.assertEqual(fire['cooldown'], 1)
        self.assertEqual(fire['costs'], {'mana': 6})
