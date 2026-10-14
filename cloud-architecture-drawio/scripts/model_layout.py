"""Resolve layout shorthands into the absolute model the compiler checks.

Shorthands, all optional:
  * node `w`/`h` omitted: the standard 156x124 card;
  * `grid` with nodes placed by `col`/`row` instead of `x`/`y`;
  * container `x`/`y`/`w`/`h` given as "fit": wrap its children (or, for an
    overlay group, its `members`) with room for the title, or "match:ID" to
    copy that dimension from another container;
  * canvas `width`/`height` as "auto": fit the content, page texts and legend.
The result is an ordinary absolute model; the source model is never modified.
Text widths are estimated here as in the compiler, so a fitted box or an auto
canvas is never narrower than its one-line title.
"""
import copy
import math
import unicodedata

CARD = {'w': 156, 'h': 124}
# Room around fitted children: the title band leaves 52px above the first card,
# which also clears the lead-in of a card connected through its top side.
PAD = {'left': 24, 'top': 56, 'right': 24, 'bottom': 24}
GRID = {'left': 60, 'top': 140, 'column': 236, 'row': 204}
LEGEND_ITEM, LEGEND_LAST, PAGE_SIDE, FOOTER, TITLE_BAND = 205, 200, 30, 90, 90
# The validator keeps shapes inside x 10..width-10 and y 80..height-90.
MARGIN_SIDE, MARGIN_TOP, STUB = 10, 80, 16


def measure(text, font):
    # Integer hundredths avoid Python-version-dependent floating-point summation.
    return font*sum(100 if unicodedata.east_asian_width(c) in 'WF' else 58 for c in text)/100


def wrapped(text, width, font):
    """Conservative width estimate; browser inspection remains mandatory."""
    lines = []
    for paragraph in text.split('\n'):
        line = ''
        for word in paragraph.split():
            trial = (line+' '+word).strip()
            if measure(trial, font) <= width:
                line = trial
                continue
            if line:
                lines.append(line)
                line = ''
            for char in word:
                if measure(line+char, font) > width and line:
                    lines.append(line)
                    line = ''
                line += char
        lines.append(line)
    return lines


def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


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
    return resolve(m)[0]


def resolve(m):
    """Like normalize, and also return the (dx, dy) by which the whole layout was
    moved to clear the page margins. Coordinates written in the model live
    before that move, so an absolute position maps back by subtracting it."""
    if not uses_shorthand(m):
        return m, (0, 0)
    m = copy.deepcopy(m)
    grid = m.pop('grid', {})
    if not isinstance(grid, dict):
        raise ValueError('grid: must be an object with left, top, column and row')
    for key in grid:
        if key not in GRID:
            raise ValueError(f'grid.{key}: unknown key; use left, top, column or row')
    grid = dict(GRID, **grid)
    for key in GRID:
        if not is_number(grid[key]):
            raise ValueError(f'grid.{key}: must be a finite number')
    nodes, boxes = items(m, 'nodes'), items(m, 'containers')
    box_ids = {id(b) for b in boxes}
    for n in nodes:
        for key in ('w', 'h'):
            n.setdefault(key, 12 if n.get('icon')=='generic.junction' else CARD[key])
        for axis, cell, origin, size in (('x', 'col', 'left', 'column'), ('y', 'row', 'top', 'row')):
            if cell in n:
                if axis in n:
                    raise ValueError(f"{n.get('id')}: give either {axis} or {cell}, not both")
                if not is_number(n[cell]):
                    raise ValueError(f"{n.get('id')}: {cell} must be a finite number")
                n[axis] = grid[origin]+n.pop(cell)*grid[size]
        for key in ('x', 'y', 'w', 'h'):
            if not is_number(n.get(key)):
                hint = f" (or give {'col' if key == 'x' else 'row'})" if key in ('x', 'y') else ''
                raise ValueError(f"{n.get('id')}.{key}: must be a finite number{hint}")
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

    def resolve_box(box):
        """Fit a container after its children; detect cycles through match/fit."""
        if all(is_number(box.get(k)) for k in ('x', 'y', 'w', 'h')):
            return box
        if box.get('id') in resolving:
            raise ValueError(f"{box.get('id')}: fit/match refers back to itself")
        resolving.add(box.get('id'))
        fitted_width = box.get('w') == 'fit'
        for key in ('x', 'y', 'w', 'h'):
            value = box.get(key)
            if isinstance(value, str) and value.startswith('match:'):
                other = by_id.get(value[6:])
                if other is None:
                    raise ValueError(f"{box.get('id')}.{key}: {value!r} names no container")
                box[key] = resolve_box(other)[key]
        if any(box.get(k) == 'fit' for k in ('x', 'y', 'w', 'h')):
            # An overlay fits the cards of its members, so its left edge meets the
            # first member's box; centre its title clear of that box's title.
            if box.get('overlay'):
                box.setdefault('labelAlign', 'center')
            inner = [resolve_box(c) if id(c) in box_ids else c for c in children(box)]
            if not inner:
                raise ValueError(f"{box.get('id')}: 'fit' needs at least one child inside it")
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
            if not is_number(box.get(key)):
                raise ValueError(f"{box.get('id')}.{key}: use a finite number, 'fit' or 'match:ID'")
        # A fitted width also holds the one-line title the validator requires.
        if fitted_width and isinstance(box.get('label'), str):
            offset = box.get('labelOffset', 0) if is_number(box.get('labelOffset', 0)) else 0
            box['w'] = max(box['w'], math.ceil(measure(box['label'], 14)+24+offset))
        resolving.discard(box.get('id'))
        return box

    for box in boxes:
        resolve_box(box)
    shapes = nodes+boxes
    dx = dy = 0
    # Nested fits grow outwards; when they reach into the page margins, move
    # everything clear of the title band and side margin. An auto-sized canvas
    # also closes any gap above or beside the content. A card connected through
    # its top side needs its lead-in below the title band.
    if shapes:
        stub = (m.get('routing') or {}).get('stub', STUB) if isinstance(m.get('routing'), dict) else STUB
        stub = stub if is_number(stub) else STUB
        top_ported = {e.get(end) for e in items(m, 'edges') for end, port in (('source', 'sourcePort'), ('target', 'targetPort')) if e.get(port) == 'top'}
        allowed = {id(s): MARGIN_TOP+(stub if s.get('id') in top_ported else 0) for s in shapes}
        wanted = {id(s): max(TITLE_BAND, allowed[id(s)]) for s in shapes}
        left = min(s['x'] for s in shapes)
        if m.get('width') == 'auto':
            dx = PAGE_SIDE-left
        elif left < MARGIN_SIDE:
            dx = PAGE_SIDE-left
        if m.get('height') == 'auto' or any(s['y'] < allowed[id(s)] for s in shapes):
            dy = max(wanted[id(s)]-s['y'] for s in shapes)
            if m.get('height') != 'auto':
                dy = max(0, dy)
        for shape in shapes:
            shape['x'] += dx
            shape['y'] += dy
        for lock in m.get('lockedRoutes',{}).values():
            lock['points']=[[x+dx,y+dy] for x,y in lock['points']]
    if m.get('width') == 'auto':
        kinds = {e.get('kind', 'traffic') for e in items(m, 'edges')}
        legend = PAGE_SIDE+(len(kinds)-1)*LEGEND_ITEM+LEGEND_LAST+PAGE_SIDE if kinds else 0
        texts = [measure(str(m.get('title', 'Cloud architecture')), 24)+60, measure(str(m.get('subtitle', '')), 12)+60]
        width = math.ceil(max([legend]+texts+[s['x']+s['w']+PAGE_SIDE for s in shapes]))
        notes = ' · '.join(str(n) for n in m.get('notes', [])) if isinstance(m.get('notes'), list) else ''
        while len(wrapped(notes, width-60, 11)) > 2 and width < 20000:
            width += 10
        m['width'] = width
    if m.get('height') == 'auto':
        m['height'] = math.ceil(max(s['y']+s['h'] for s in shapes)+FOOTER+20) if shapes else 400
    return m, (dx, dy)
