"""Local browser editor and battle UI. Run with python -m combat_engine.web."""
import argparse
import json
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from urllib.parse import urlparse

from .engine import Battle, Combatant, RulesError, validate_catalog

ROOT = Path(__file__).parent / 'web'
SESSIONS = {}
LOCK = Lock()


def snapshot(battle):
    actor = battle.active
    actions = []
    if actor and not battle.finished:
        available = battle.available_actions(actor)
        for action in list(actor.abilities) + [f'item:{i}' for i, n in actor.inventory.items() if n > 0]:
            aid = battle.catalog['items'][action[5:]]['ability'] if action.startswith('item:') else action
            definition = battle.catalog['abilities'][aid]
            actions.append(dict(id=action, name=definition.get('name', aid), available=action in available,
                                cooldown=actor.cooldowns.get(aid, 0), costs=battle.action_costs(definition),
                                target=definition.get('target', 'enemy'), range=battle.ability_range(definition), line_of_sight=definition.get('line_of_sight', True),
                                targets=[battle.combatants.index(c) for c in battle.targets(actor, definition)]))
    return dict(round=battle.round, finished=battle.finished, winner=battle.winner,
                stamina_per_turn=battle.catalog.get('rules', {}).get('stamina_per_turn', False),
                active=battle.combatants.index(actor) if actor else None, actions=actions,
                grid=None if not battle.board else dict(width=battle.board.width, height=battle.board.height, blocked=sorted(battle.board.walls), movement_remaining=actor.movement_remaining if actor else 0, move_stamina_cost=battle.catalog['grid'].get('move_stamina_cost', 0.5) if battle.catalog.get('rules', {}).get('stamina_per_turn', False) else 0, reachable=[dict(position=p, path=path, steps=len(path)) for p,path in battle.movement_paths(actor).items()] if actor else []),
                log=battle.log, combatants=[dict(name=c.name, team=c.team, alive=c.alive, species=c.species, position=c.position, movement_remaining=c.movement_remaining,
                initiative=c.initiative(), traits=battle.catalog.get('species', {}).get(c.species, {}).get('traits', []),
                resources=c.resources, caps={k: c.stat('max_' + k) for k in c.resources},
                stats={k: c.stat(k) for k in set(c.base_stats) | set(battle.catalog.get('rules', {}).get('derived_stats', {}))}, inventory=c.inventory,
                resistances={k: c.resistance(k) for k in battle.catalog.get('damage_types', {})},
                statuses=[dict(name=battle.catalog['statuses'][s.id].get('name', s.id),
                               remaining=s.remaining, stacks=s.stacks) for s in c.statuses.values()]) for c in battle.combatants])


class Handler(BaseHTTPRequestHandler):
    def reply(self, status, payload, content_type='application/json'):
        body = json.dumps(payload).encode() if content_type == 'application/json' else payload
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        route = urlparse(self.path).path
        if route == '/api/demo':
            return self.reply(200, self.server.catalog)
        files = {'/': ('index.html', 'text/html; charset=utf-8'),
                 '/app.js': ('app.js', 'text/javascript'), '/style.css': ('style.css', 'text/css')}
        if route not in files:
            return self.reply(404, {'error': 'Not found'})
        name, mime = files[route]
        self.reply(200, (ROOT / name).read_bytes(), mime)

    def do_POST(self):
        # Block cross-origin websites from controlling this local application.
        origin = self.headers.get('Origin')
        if origin and origin != 'http://' + self.headers.get('Host', ''):
            return self.reply(403, {'error': 'Cross-origin requests are not allowed'})
        if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            return self.reply(415, {'error': 'Use application/json'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 2_000_000:
                raise RulesError('Request must be between 1 byte and 2 MB')
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise RulesError('Request must be an object')
            with LOCK:
                if self.path in ('/api/validate', '/api/start'):
                    catalog = data['catalog']
                    validate_catalog(catalog)
                    if self.path == '/api/validate':
                        return self.reply(200, {'valid': True})
                    roster = catalog.get('battle', [])
                    battle = Battle(catalog, [Combatant(catalog, r['character'], r['team'], name=r.get('name'), position=r.get('position')) for r in roster], seed=7)
                    battle.begin_turn()
                    sid = secrets.token_urlsafe(24)
                    if len(SESSIONS) >= 100:
                        SESSIONS.pop(next(iter(SESSIONS)))
                    SESSIONS[sid] = battle
                elif self.path == '/api/action':
                    sid = data.get('session')
                    if sid not in SESSIONS:
                        raise RulesError('Battle expired. Start a new battle.')
                    battle = SESSIONS[sid]
                    if data.get('action') == 'wait':
                        battle.wait()
                    elif data.get('action') == 'auto':
                        battle.auto_action()
                    elif data.get('action') == 'move':
                        battle.move(data.get('destination'))
                    else:
                        index = data.get('target')
                        if index is not None and (type(index) is not int or not 0 <= index < len(battle.combatants)):
                            raise RulesError('Invalid target')
                        battle.act(data['action'], battle.combatants[index] if index is not None else None)
                    battle.begin_turn()
                else:
                    return self.reply(404, {'error': 'Unknown endpoint'})
                self.reply(200, dict(session=sid, **snapshot(battle)))
        except (RulesError, ValueError, KeyError, TypeError, AttributeError) as error:
            self.reply(400, {'error': str(error)})


def main():
    parser = argparse.ArgumentParser(description='Launch the combat editor in your browser')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--data', type=Path, default=Path(__file__).parent / 'demo.json')
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    server.catalog = json.loads(args.data.read_text())
    validate_catalog(server.catalog)
    print(f'Combat Foundry is ready: http://127.0.0.1:{args.port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
