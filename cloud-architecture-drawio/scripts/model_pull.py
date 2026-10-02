"""Bring manual draw.io edits of a compiled diagram back into its model.

Only what the compiler can rebuild is pulled: shape positions and sizes, the
container a shape was dropped into, and the text of titles, details, boundary
titles and connector captions. Items whose geometry did not change keep their
layout shorthands (grid cells, "fit"). Cells the model does not describe, such
as shapes drawn by hand, are listed so they can be modelled or kept manually.
"""
import base64
import copy
import urllib.parse
import xml.etree.ElementTree as ET
import zlib

import model_layout

TOLERANCE = 0.5


def page_model(path, page=1):
    """Return the <mxGraphModel> element of one page, decompressing if needed."""
    root = ET.parse(path).getroot()
    diagrams = root.findall('diagram') if root.tag == 'mxfile' else []
    if not diagrams:
        if root.tag == 'mxGraphModel':
            return root
        raise ValueError(f'{path}: not a draw.io file')
    if page > len(diagrams):
        raise ValueError(f'{path}: page {page} requested, but the file has {len(diagrams)} page(s)')
    diagram = diagrams[page-1]
    model = diagram.find('mxGraphModel')
    if model is None:
        data = (diagram.text or '').strip()
        if not data:
            raise ValueError(f'{path}: page {page} is empty')
        xml = urllib.parse.unquote(zlib.decompress(base64.b64decode(data), -15).decode('utf-8'))
        model = ET.fromstring(xml)
    return model


def absolute_geometry(model):
    """Absolute x/y/w/h and parent ID of every vertex, keyed by cell ID."""
    cells = {cell.get('id'): cell for cell in model.iter('mxCell')}
    found = {}

    def position(cell_id, depth=0):
        cell = cells.get(cell_id)
        if cell is None or cell.get('vertex') != '1' or depth > 64:
            return 0.0, 0.0
        geo = cell.find('mxGeometry')
        x, y = float(geo.get('x', 0)), float(geo.get('y', 0))
        px, py = position(cell.get('parent'), depth+1)
        return x+px, y+py

    for cell_id, cell in cells.items():
        geo = cell.find('mxGeometry')
        if cell.get('vertex') != '1' or geo is None or geo.get('relative') == '1':
            continue
        x, y = position(cell_id)
        found[cell_id] = {'x': x, 'y': y, 'w': float(geo.get('width', 0)), 'h': float(geo.get('height', 0)),
                          'parent': cell.get('parent'), 'value': cell.get('value', '')}
    labels = {cell.get('parent'): cell.get('value', '') for cell in cells.values() if cell.get('id', '').startswith('__label_')}
    return found, labels, set(cells)


def clean(number):
    return int(number) if float(number).is_integer() else round(number, 2)


def pull(source, drawio, page=1):
    """Return (updated model, summary of changes) for an edited diagram."""
    resolved = model_layout.normalize(source)
    shapes, captions, cell_ids = absolute_geometry(page_model(drawio, page))
    model = copy.deepcopy(source)
    summary = {'moved': [], 'resized': [], 'reparented': [], 'relabelled': [], 'missing': [], 'unmodelled': []}
    resolved_by = {i['id']: i for k in ('containers', 'nodes') for i in resolved.get(k, [])}
    modelled = set(resolved_by) | {e['id'] for e in resolved.get('edges', [])}
    containers = {b['id'] for b in resolved.get('containers', [])}

    def text(value):
        return ' '.join(value.split())

    for key in ('containers', 'nodes'):
        for item in model.get(key, []):
            ident, known = item['id'], resolved_by[item['id']]
            cell = shapes.get(ident)
            if cell is None:
                summary['missing'].append(ident)
                continue
            if abs(cell['x']-known['x']) > TOLERANCE or abs(cell['y']-known['y']) > TOLERANCE:
                item['x'], item['y'] = clean(cell['x']), clean(cell['y'])
                item.pop('col', None)
                item.pop('row', None)
                summary['moved'].append(ident)
            if abs(cell['w']-known['w']) > TOLERANCE or abs(cell['h']-known['h']) > TOLERANCE:
                item['w'], item['h'] = clean(cell['w']), clean(cell['h'])
                summary['resized'].append(ident)
            # A fitted dimension stays "fit" only while the box was left alone.
            if ident in summary['moved'] or ident in summary['resized']:
                for dim in ('x', 'y', 'w', 'h'):
                    if isinstance(item.get(dim), str):
                        item[dim] = clean(cell[dim])
            parent = cell['parent'] if cell['parent'] in containers else None
            if parent != known.get('parent'):
                if parent:
                    item['parent'] = parent
                else:
                    item.pop('parent', None)
                summary['reparented'].append(ident)
            if key == 'containers':
                if text(cell['value']) != text(item['label']):
                    item['label'] = cell['value']
                    summary['relabelled'].append(ident)
            else:
                for field, prefix in (('label', '__name_'), ('detail', '__detail_')):
                    part = shapes.get(prefix+ident)
                    # The compiler inserts line breaks to wrap; only real edits count.
                    if part is not None and text(part['value']) != text(item.get(field, '')):
                        item[field] = part['value'].replace('\n', ' ') if '\n' not in item.get(field, '') else part['value']
                        summary['relabelled'].append(f'{ident}.{field}')
    for edge in model.get('edges', []):
        value = captions.get(edge['id'])
        if value is not None and text(value) != text(edge.get('label', '')):
            edge['label'] = value
            summary['relabelled'].append(f"{edge['id']}.label")
        if edge['id'] not in cell_ids:
            summary['missing'].append(edge['id'])
    for cell_id in sorted(cell_ids):
        if cell_id in ('0', '1') or cell_id.startswith('__') or cell_id in modelled:
            continue
        summary['unmodelled'].append(cell_id)
    return model, summary
