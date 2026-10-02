"""Resolve layout shorthands into the absolute model the compiler checks.

Shorthands, all optional:
  * node `w`/`h` omitted: the standard 156x124 card;
  * `grid` with nodes placed by `col`/`row` instead of `x`/`y`;
  * container `x`/`y`/`w`/`h` given as "fit": wrap its children (or, for an
    overlay group, its `members`) with room for the title, or "match:ID" to
    copy that dimension from another container;
  * canvas `width`/`height` as "auto": fit the content, title band and legend.
The result is an ordinary absolute model; the source model is never modified.
"""
import copy

CARD = {'w': 156, 'h': 124}
# Room around fitted children: the title band leaves 52px above the first card,
# which also clears the lead-in of a card connected through its top side.
PAD = {'left': 24, 'top': 56, 'right': 24, 'bottom': 24}
GRID = {'left': 60, 'top': 140, 'column': 236, 'row': 204}
LEGEND_ITEM, LEGEND_LAST, PAGE_SIDE, FOOTER, TITLE_BAND = 205, 200, 30, 90, 90


def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def items(m, key):
    values = m.get(key)
    return [i for i in values if isinstance(i, dict)] if isinstance(values, list) else []


def uses_shorthand(m):
    if not isinstance(m, dict):
        return False
    shapes = items(m, 'containers')+items(m, 'nodes')
    return ('grid' in m or m.get('width') == 'auto' or m.get('height') == 'auto'
            or any(isinstance(i.get(k), str) for i in shapes for k in ('x', 'y', 'w', 'h'))
            or any('w' not in n or 'h' not in n or 'col' in n or 'row' in n for n in items(m, 'nodes')))


def normalize(m):
    """Return an absolute copy of the model; raise ValueError for bad shorthands."""
    if not uses_shorthand(m):
        return m
    m = copy.deepcopy(m)
    grid = dict(GRID, **(m.pop('grid') if isinstance(m.get('grid'), dict) else {}))
    for key in ('left', 'top', 'column', 'row'):
        if not is_number(grid[key]):
            raise ValueError(f'grid.{key}: must be a number')
    nodes, boxes = items(m, 'nodes'), items(m, 'containers')
    box_ids = {id(b) for b in boxes}
    for n in nodes:
        for key in ('w', 'h'):
            n.setdefault(key, CARD[key])
        for axis, cell, origin, size in (('x', 'col', 'left', 'column'), ('y', 'row', 'top', 'row')):
            if cell in n:
                if axis in n:
                    raise ValueError(f"{n.get('id')}: give either {axis} or {cell}, not both")
                if not is_number(n[cell]):
                    raise ValueError(f"{n.get('id')}: {cell} must be a number")
                n[axis] = grid[origin]+n.pop(cell)*grid[size]
    by_id = {b.get('id'): b for b in boxes}
    nodes_by_id = {n.get('id'): n for n in nodes}

    def children(box):
        if box.get('overlay'):
            members = box.get('members', [])
            missing = [i for i in members if i not in nodes_by_id and i not in by_id]
            if missing or not members:
                raise ValueError(f"{box.get('id')}: a fitted overlay group needs members naming its nodes" + (f'; unknown {missing}' if missing else ''))
            return [nodes_by_id.get(i) or by_id[i] for i in members]
        return [i for i in nodes+boxes if i.get('parent') == box.get('id') and not i.get('overlay')]

    resolving = set()

    def resolve(box):
        """Fit a container after its children; detect cycles through match/fit."""
        if all(is_number(box.get(k)) for k in ('x', 'y', 'w', 'h')):
            return box
        if box.get('id') in resolving:
            raise ValueError(f"{box.get('id')}: fit/match refers back to itself")
        resolving.add(box.get('id'))
        for key in ('x', 'y', 'w', 'h'):
            value = box.get(key)
            if isinstance(value, str) and value.startswith('match:'):
                other = by_id.get(value[6:])
                if other is None:
                    raise ValueError(f"{box.get('id')}.{key}: {value!r} names no container")
                box[key] = resolve(other)[key]
        if any(box.get(k) == 'fit' for k in ('x', 'y', 'w', 'h')):
            inner = [resolve(c) if id(c) in box_ids else c for c in children(box)]
            if not inner:
                raise ValueError(f"{box.get('id')}: 'fit' needs at least one child inside it")
            if any(not all(is_number(c.get(k)) for k in ('x', 'y', 'w', 'h')) for c in inner):
                raise ValueError(f"{box.get('id')}: 'fit' children need resolved positions")
            left = min(c['x'] for c in inner)-PAD['left']
            top = min(c['y'] for c in inner)-PAD['top']
            if box.get('x') == 'fit':
                box['x'] = left
            if box.get('y') == 'fit':
                box['y'] = top
            if box.get('w') == 'fit':
                if not is_number(box.get('x')):
                    raise ValueError(f"{box.get('id')}: fit width needs x")
                box['w'] = max(c['x']+c['w'] for c in inner)+PAD['right']-box['x']
            if box.get('h') == 'fit':
                if not is_number(box.get('y')):
                    raise ValueError(f"{box.get('id')}: fit height needs y")
                box['h'] = max(c['y']+c['h'] for c in inner)+PAD['bottom']-box['y']
        for key in ('x', 'y', 'w', 'h'):
            if isinstance(box.get(key), str):
                raise ValueError(f"{box.get('id')}.{key}: use a number, 'fit' or 'match:ID'")
        resolving.discard(box.get('id'))
        return box

    for box in boxes:
        resolve(box)
    shapes = nodes+boxes
    # Nested fits grow outwards; move everything clear of the page title band
    # and side margin so the grid origin never has to anticipate nesting depth.
    # An auto-sized canvas also closes any gap left above or beside the content.
    if shapes:
        dx = PAGE_SIDE-min(s['x'] for s in shapes)
        dy = TITLE_BAND-min(s['y'] for s in shapes)
        dx = dx if m.get('width') == 'auto' else max(0, dx)
        dy = dy if m.get('height') == 'auto' else max(0, dy)
        for shape in shapes:
            shape['x'] += dx
            shape['y'] += dy
    if m.get('width') == 'auto':
        kinds = {e.get('kind', 'traffic') for e in items(m, 'edges')}
        legend = PAGE_SIDE+(len(kinds)-1)*LEGEND_ITEM+LEGEND_LAST+PAGE_SIDE if kinds else 0
        m['width'] = max([legend]+[s['x']+s['w']+PAGE_SIDE for s in shapes])
    if m.get('height') == 'auto':
        m['height'] = max(s['y']+s['h'] for s in shapes)+FOOTER+20 if shapes else 400
    return m
