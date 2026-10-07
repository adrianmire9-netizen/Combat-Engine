"""Bounded square-grid geometry, shortest paths, and wall line of sight."""
from collections import deque


def validate_grid(data):
    grid = data.get('grid', {})
    if not isinstance(grid, dict):
        raise ValueError('grid must be an object')
    if not isinstance(grid.get('enabled', False), bool):
        raise ValueError('grid.enabled must be a boolean')
    width, height = grid.get('width', 10), grid.get('height', 8)
    for name, value in [('width', width), ('height', height)]:
        if type(value) is not int or not 2 <= value <= 20:
            raise ValueError(f'grid.{name} must be an integer from 2 to 20')
    def coordinate(value):
        return (isinstance(value, (list, tuple)) and len(value) == 2
                and all(type(n) is int for n in value)
                and 0 <= value[0] < width and 0 <= value[1] < height)
    blocked = grid.get('blocked', [])
    if not isinstance(blocked, list) or any(not coordinate(p) for p in blocked):
        raise ValueError('grid.blocked must contain in-bounds [x, y] integer coordinates')
    walls = {tuple(p) for p in blocked}
    if len(walls) != len(blocked):
        raise ValueError('Duplicate blocked cell')
    for entry in data.get('battle', []):
        p = entry.get('position')
        if p is not None and (not isinstance(p, (list, tuple)) or len(p) != 2 or any(type(n) is not int for n in p)):
            raise ValueError('Starting positions must be [x, y] integer coordinates')
    if grid.get('enabled', False):
        positions = set()
        for entry in data.get('battle', []):
            p = entry.get('position')
            if p is not None:
                if not coordinate(p) or tuple(p) in walls or tuple(p) in positions:
                    raise ValueError('Starting positions must be unique, in bounds, and off walls')
                positions.add(tuple(p))
        if len(data.get('battle', [])) > width * height - len(walls):
            raise ValueError('Not enough open cells for the encounter roster')
    return grid


def distance(a, b):
    return abs(a[0]-b[0])+abs(a[1]-b[1])


class Board:
    def __init__(self, config):
        self.width = config.get('width', 10)
        self.height = config.get('height', 8)
        self.walls = {tuple(p) for p in config.get('blocked', [])}

    def contains(self, p):
        return 0 <= p[0] < self.width and 0 <= p[1] < self.height

    def paths(self, start, occupied=()):
        """All shortest orthogonal paths; do not cross walls or living units."""
        forbidden = self.walls | {tuple(p) for p in occupied}
        result = {start: []}
        queue = deque([start])
        while queue:
            x, y = queue.popleft()
            for p in [(x-1, y), (x+1, y), (x, y-1), (x, y+1)]:
                if self.contains(p) and p not in forbidden and p not in result:
                    result[p] = result[(x, y)] + [p]
                    queue.append(p)
        return result

    def visible(self, a, b):
        """Supercover line: walls, including corner-touching walls, block sight."""
        x, y = a
        dx, dy = b[0]-x, b[1]-y
        nx, ny = abs(dx), abs(dy)
        sx, sy = (1 if dx > 0 else -1), (1 if dy > 0 else -1)
        ix = iy = 0
        while ix < nx or iy < ny:
            decision = (1+2*ix)*ny - (1+2*iy)*nx
            if decision == 0:
                if (x+sx, y) in self.walls or (x, y+sy) in self.walls:
                    return False
                x += sx; y += sy; ix += 1; iy += 1
            elif decision < 0:
                x += sx; ix += 1
            else:
                y += sy; iy += 1
            if (x, y) in self.walls:
                return False
        return True

    def place(self, combatants):
        """Honor explicit starts; automatically spread teams along opposite edges."""
        used = set(self.walls)
        for c in combatants:
            if c.position is not None:
                if (not isinstance(c.position, (tuple, list)) or len(c.position) != 2
                    or any(type(n) is not int for n in c.position)
                    or not self.contains(c.position) or tuple(c.position) in used):
                    raise ValueError('Combatant starting positions must be unique open cells')
                c.position = tuple(c.position)
                used.add(c.position)
        teams = list(dict.fromkeys(c.team for c in combatants))
        for c in combatants:
            if c.position is not None:
                continue
            team = teams.index(c.team)
            cells = [(x,y) for x in range(self.width) for y in range(self.height) if (x,y) not in used]
            if not cells:
                raise ValueError('Not enough open cells for combatants')
            # First two teams face one another; additional teams use top/bottom.
            edge = [lambda p:p[0], lambda p:self.width-1-p[0], lambda p:p[1], lambda p:self.height-1-p[1]][team % 4]
            c.position = min(cells, key=lambda p:(edge(p), abs(p[1]-self.height//2), p[0], p[1]))
            used.add(c.position)
