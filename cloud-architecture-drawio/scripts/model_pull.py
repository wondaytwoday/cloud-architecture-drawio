"""Bring manual draw.io edits of a compiled diagram back into its model.

Only what the compiler can rebuild is pulled: shape positions and sizes, the
container a shape was dropped into, connector ends moved to another modelled
shape, and the text of titles, details, boundary titles, connector captions,
the page title, subtitle, notes and legend. Styles and hand-bent connector
paths are not pulled; the router plans paths again.

Items whose geometry did not change keep their layout shorthands (grid cells,
"fit"). The pulled model is resolved again and compared with the drawing: a
fitted box that would no longer land where it is drawn gets the drawn numbers,
and when the shorthands cannot reproduce the drawing at all, every shape gets
its drawn absolute geometry instead. Cells the model does not describe, such as
shapes drawn by hand, are listed so they can be modelled or kept manually.
"""
import base64
import binascii
import copy
import difflib
import math
from pathlib import Path
import struct
import urllib.parse
import xml.etree.ElementTree as ET
import zlib

import model_layout
from model_validation import legend_captions

TOLERANCE = 0.5
WRAPPERS = ('UserObject', 'object')
PORT_KEYS = {'source': ('sourcePort', 'sourceOffset'), 'target': ('targetPort', 'targetOffset')}


def parse(text, path):
    try:
        return ET.fromstring(text)
    except ET.ParseError as exc:
        raise ValueError(f'{path}: not a readable draw.io file ({exc})') from None


def png_diagram(data, path):
    """The diagram draw.io stores in an editable PNG (tEXt or zTXt chunk)."""
    pos = 8
    while pos+8 <= len(data):
        length, kind = struct.unpack('>I4s', data[pos:pos+8])
        body = data[pos+8:pos+8+length]
        if kind in (b'tEXt', b'zTXt'):
            key, _, value = body.partition(b'\0')
            if key in (b'mxfile', b'mxGraphModel'):
                try:
                    text = (zlib.decompress(value[1:]) if kind == b'zTXt' else value).decode('latin-1')
                except zlib.error:
                    text = zlib.decompress(value[1:], -15).decode('latin-1')
                return urllib.parse.unquote(text) if text.startswith('%') else text
        if kind == b'IEND':
            break
        pos += 12+length
    raise ValueError(f'{path}: this PNG holds no draw.io diagram; open it in draw.io and save it as .drawio')


def read_file(path):
    """Root element of a .drawio file, or of the diagram inside an editable PNG or SVG."""
    data = Path(path).read_bytes()
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        return parse(png_diagram(data, path), path)
    try:
        root = parse(data.decode('utf-8-sig'), path)
    except UnicodeDecodeError:
        raise ValueError(f'{path}: not a readable draw.io file') from None
    if root.tag.rsplit('}', 1)[-1] == 'svg':
        content = root.get('content')
        if not content:
            raise ValueError(f'{path}: this SVG holds no draw.io diagram')
        root = parse(content, path)
    return root


def page_count(path):
    root = read_file(path)
    return len(root.findall('diagram')) if root.tag == 'mxfile' else 1


def page_model(path, page=1):
    """Return the <mxGraphModel> element of one page, decompressing if needed."""
    root = read_file(path)
    diagrams = root.findall('diagram') if root.tag == 'mxfile' else []
    if not diagrams:
        if root.tag == 'mxGraphModel' and page == 1:
            return root
        raise ValueError(f'{path}: not a draw.io file' if root.tag != 'mxGraphModel' else f'{path}: page {page} requested, but the file has 1 page')
    if not 1 <= page <= len(diagrams):
        raise ValueError(f'{path}: page {page} requested, but the file has {len(diagrams)} page(s)')
    diagram = diagrams[page-1]
    model = diagram.find('mxGraphModel')
    if model is None:
        data = (diagram.text or '').strip()
        if not data:
            raise ValueError(f'{path}: page {page} is empty')
        try:
            xml = urllib.parse.unquote(zlib.decompress(base64.b64decode(data), -15).decode('utf-8'))
        except (binascii.Error, zlib.error, UnicodeDecodeError):
            raise ValueError(f'{path}: page {page} is not a readable compressed diagram') from None
        model = parse(xml, path)
    return model


def cells(model):
    """(id, value, mxCell) for every cell, unwrapping <UserObject>/<object>,
    which draw.io uses for cells with links, tooltips or data properties."""
    inner = set()
    for el in model.iter():
        if el.tag in WRAPPERS and el.find('mxCell') is not None:
            cell = el.find('mxCell')
            inner.add(id(cell))
            if el.get('id') is not None:
                yield el.get('id'), el.get('label', ''), cell
    for el in model.iter('mxCell'):
        if id(el) not in inner and el.get('id') is not None:
            yield el.get('id'), el.get('value', ''), el


def drawing(model):
    """Vertices with absolute geometry, edges, connector captions and all IDs."""
    found = {cid: (value, cell) for cid, value, cell in cells(model)}
    shapes, edges, captions = {}, {}, {}

    def position(cell_id, depth=0):
        item = found.get(cell_id)
        if item is None or item[1].get('vertex') != '1' or depth > 64:
            return 0.0, 0.0
        geo = item[1].find('mxGeometry')
        x, y = (float(geo.get('x', 0)), float(geo.get('y', 0))) if geo is not None else (0.0, 0.0)
        px, py = position(item[1].get('parent'), depth+1)
        return x+px, y+py

    for cid, (value, cell) in found.items():
        if cell.get('edge') == '1':
            edges[cid] = {'source': cell.get('source'), 'target': cell.get('target'), 'value': value}
            continue
        geo = cell.find('mxGeometry')
        if cell.get('vertex') != '1' or geo is None:
            continue
        if geo.get('relative') == '1':
            if cid.startswith('__label_'):
                captions[cell.get('parent')] = value
            continue
        x, y = position(cid)
        shapes[cid] = {'x': x, 'y': y, 'w': float(geo.get('width', 0)), 'h': float(geo.get('height', 0)),
                       'parent': cell.get('parent'), 'value': value}
    return shapes, edges, captions, set(found)


def clean(number):
    return int(number) if float(number).is_integer() else round(number, 2)


def restore(original, compiled, edited):
    """The model text for an edited cell. The compiler wraps titles and details
    with line breaks; breaks it inserted in text the user left unchanged become
    the space (or nothing, inside a long word) they replaced."""
    normal = '\n'.join(' '.join(p.split()) for p in original.split('\n'))
    plain, j = [], 0
    for ch in compiled:
        if j < len(normal) and ch == normal[j]:
            plain.append(ch)
            j += 1
        elif ch == '\n' and j < len(normal) and normal[j] == ' ':
            plain.append(' ')
            j += 1
        elif ch == '\n':
            plain.append('')
        else:
            plain.append(ch)
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, compiled, edited, autojunk=False).get_opcodes():
        out.append(''.join(plain[i1:i2]) if op == 'equal' else edited[j1:j2])
    return ''.join(out)


def off(drawn, box):
    return any(abs(drawn[k]-box[k]) > TOLERANCE for k in ('x', 'y', 'w', 'h'))


def pull(source, drawio, page=1):
    """Return (updated model, summary of changes) for an edited diagram."""
    resolved, (dx, dy) = model_layout.resolve(source)
    shapes, edges, captions, cell_ids = drawing(page_model(drawio, page))
    model = copy.deepcopy(source)
    summary = {'moved': [], 'resized': [], 'reparented': [], 'relabelled': [], 'reconnected': [],
               'missing': [], 'unmodelled': [], 'ignored': [], 'pinned': [], 'layout': 'kept'}
    resolved_by = {i['id']: i for k in ('containers', 'nodes') for i in resolved.get(k, [])}
    modelled = set(resolved_by) | {e['id'] for e in resolved.get('edges', [])}
    containers = {b['id'] for b in resolved.get('containers', [])}
    # Another page of a bundle may hold this model's build.
    found = len(set(resolved_by) & set(shapes))
    if resolved_by and found < len(resolved_by):
        for other in range(1, page_count(drawio)+1):
            if other != page and len(set(resolved_by) & set(drawing(page_model(drawio, other))[0])) > found:
                raise ValueError(f'{drawio}: page {other} matches this model better than page {page}; pass --page {other}')
    shift = {'x': dx, 'y': dy, 'w': 0, 'h': 0}

    def model_frame(cell, dim):
        """A drawn coordinate in the model's own frame, before the page shift."""
        return clean(cell[dim]-shift[dim])

    def text(item, field, compiled, value, name):
        if value == compiled:
            return
        updated = restore(item.get(field, ''), compiled, value)
        if updated:
            item[field] = updated
        else:
            item.pop(field, None)
        summary['relabelled'].append(name)

    for key in ('containers', 'nodes'):
        for item in model.get(key, []):
            ident, known = item['id'], resolved_by[item['id']]
            cell = shapes.get(ident)
            if cell is None:
                summary['missing'].append(ident)
                continue
            moved = abs(cell['x']-known['x']) > TOLERANCE or abs(cell['y']-known['y']) > TOLERANCE
            resized = abs(cell['w']-known['w']) > TOLERANCE or abs(cell['h']-known['h']) > TOLERANCE
            if moved:
                item['x'], item['y'] = model_frame(cell, 'x'), model_frame(cell, 'y')
                item.pop('col', None)
                item.pop('row', None)
                summary['moved'].append(ident)
            if resized:
                item['w'], item['h'] = clean(cell['w']), clean(cell['h'])
                summary['resized'].append(ident)
            # A fitted dimension stays "fit" only while the box was left alone.
            if moved or resized:
                for dim in ('x', 'y', 'w', 'h'):
                    if isinstance(item.get(dim), str):
                        item[dim] = model_frame(cell, dim)
            parent = cell['parent'] if cell['parent'] in containers else None
            if parent != known.get('parent'):
                if parent:
                    item['parent'] = parent
                else:
                    item.pop('parent', None)
                summary['reparented'].append(ident)
            if key == 'containers':
                text(item, 'label', known['label'], cell['value'], ident)
                continue
            for field, prefix, font in (('label', '__name_', 13), ('detail', '__detail_', 11)):
                part = shapes.get(prefix+ident)
                if part is not None:
                    compiled = '\n'.join(model_layout.wrapped(known.get(field, ''), known['w']-8, font))
                    text(item, field, compiled, part['value'], f'{ident}.{field}')

    for edge in model.get('edges', []):
        ident = edge['id']
        cell = edges.get(ident)
        if cell is None:
            summary['missing'].append(ident)
            continue
        caption = captions.get(ident)
        typed = cell['value'].strip()
        if caption and typed:
            summary['ignored'].append(f'{ident}: text typed on the connector itself; the caption cell was kept')
        value = caption if caption else typed
        if value != edge.get('label', ''):
            if value:
                edge['label'] = value
            else:
                edge.pop('label', None)
            summary['relabelled'].append(f'{ident}.label')
        for end in ('source', 'target'):
            now = cell[end]
            if now == edge[end]:
                continue
            if now in resolved_by:
                edge[end] = now
                for k in PORT_KEYS[end]:
                    edge.pop(k, None)
                summary['reconnected'].append(f'{ident}.{end}')
            else:
                summary['ignored'].append(f'{ident}.{end}: ' + (f'attached to unmodelled cell {now!r}' if now else 'left unattached'))

    for field, cid in (('title', '__title'), ('subtitle', '__subtitle')):
        if cid in shapes:
            default = 'Cloud architecture' if field == 'title' else ''
            if shapes[cid]['value'] != model.get(field, default):
                model[field] = shapes[cid]['value']
                summary['relabelled'].append(field)
    if '__notes' in shapes:
        notes = shapes['__notes']['value']
        if notes != ' · '.join(model.get('notes', [])):
            model['notes'] = [n for n in notes.split(' · ') if n.strip()]
            if not model['notes']:
                model.pop('notes')
            summary['relabelled'].append('notes')
    defaults = legend_captions(dict(resolved, legend={}))
    current = legend_captions(resolved)
    for kind, caption in current.items():
        cell = shapes.get('__legend_text_'+kind)
        if cell is not None and cell['value'] != caption:
            legend = model.setdefault('legend', {})
            if cell['value'] == defaults.get(kind):
                legend.pop(kind, None)
            else:
                legend[kind] = cell['value']
            if not legend:
                model.pop('legend')
            summary['relabelled'].append(f'legend.{kind}')

    for cell_id in sorted(cell_ids):
        if cell_id in ('0', '1') or cell_id.startswith('__') or cell_id in modelled:
            continue
        summary['unmodelled'].append(cell_id)

    # The model must rebuild into the drawing.
    if model_layout.uses_shorthand(model):
        touched = {resolved_by[i].get('parent') for i in summary['reparented']} | {model_item(model, i).get('parent') for i in summary['reparented']}
        model = settle(model, shapes, resolved, (dx, dy), touched, summary)
    return model, summary


def model_item(model, ident):
    return next(i for k in ('containers', 'nodes') for i in model.get(k, []) if i['id'] == ident)


def settle(model, shapes, resolved, shift, touched, summary):
    """Resolve the pulled model again and compare it with the drawing. A fitted
    or matched box that would land elsewhere, or that lost its last child, gets
    its drawn numbers ("pinned"); when that cannot reproduce the drawing, for
    example because the page shift changed, every shape gets its drawn geometry."""
    def frame(box, dim):
        return clean(shapes[box['id']][dim]-(shift[0] if dim == 'x' else shift[1] if dim == 'y' else 0))

    def pin(boxes):
        for box in boxes:
            for dim in ('x', 'y', 'w', 'h'):
                if isinstance(box.get(dim), str):
                    box[dim] = frame(box, dim)
            summary['pinned'].append(box['id'])
        return bool(boxes)

    def loose(ids):
        return [b for b in model.get('containers', []) if b['id'] in ids and b['id'] in shapes
                and any(isinstance(b.get(d), str) for d in ('x', 'y', 'w', 'h'))]

    for _ in range(len(model.get('containers', []))+2):
        try:
            check, moved_by = model_layout.resolve(model)
        except (ValueError, TypeError, KeyError, OverflowError):
            # A fitted box that lost its last child cannot fit anything.
            if pin(loose(touched)):
                touched = set()
                continue
            break
        if moved_by != shift:
            break
        placed = {i['id']: i for k in ('containers', 'nodes') for i in check.get(k, []) if i['id'] in shapes}
        wrong = {i for i, box in placed.items() if off(shapes[i], box)}
        if not wrong:
            return model
        if not pin(loose(wrong)):
            break
    summary['layout'] = 'absolute'
    return absolute(model, shapes, resolved)


def absolute(model, shapes, resolved):
    """The model with every shape at its drawn geometry and no layout shorthands."""
    m = copy.deepcopy(model)
    m.pop('grid', None)
    resolved_by = {i['id']: i for k in ('containers', 'nodes') for i in resolved.get(k, [])}
    for key in ('containers', 'nodes'):
        for item in m.get(key, []):
            box = shapes.get(item['id']) or resolved_by[item['id']]
            for dim in ('x', 'y', 'w', 'h'):
                item[dim] = clean(box[dim])
            item.pop('col', None)
            item.pop('row', None)
    placed = [i for k in ('containers', 'nodes') for i in m.get(k, [])]
    if placed:
        m['width'] = max(resolved['width'], math.ceil(max(i['x']+i['w'] for i in placed)+model_layout.PAGE_SIDE))
        m['height'] = max(resolved['height'], math.ceil(max(i['y']+i['h'] for i in placed)+model_layout.FOOTER+20))
    return m
