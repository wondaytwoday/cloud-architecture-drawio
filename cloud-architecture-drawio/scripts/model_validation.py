"""Structural, text-fit and selected CSP checks for the draw.io model.

This is deliberately not a network reachability or deployment validator.  The
compiler supplies its text wrapping and header geometry so validation uses the
same presentation assumptions as rendering.
"""
import math


PROVIDERS = {'aws', 'azure', 'gcp', 'multi'}
KINDS = {'cloud', 'account', 'project', 'region', 'vpc', 'vnet', 'az', 'subnet', 'group'}
EDGE_KINDS = {'traffic', 'dns', 'association', 'replication', 'egress', 'management'}
PORTS = {'auto', 'top', 'bottom', 'left', 'right'}
# These keys denote the service itself, not its private access endpoint.  Do not
# add generic services with both subnet-hosted and managed deployment modes.
OUTSIDE_SUBNET = {
    'aws.cloudfront', 'aws.route53', 'aws.s3',
    'azure.frontdoor', 'azure.sql', 'azure.storage',
    'gcp.sql', 'gcp.storage', 'gcp.dns',
}


def _finite(value):
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _rect(item):
    return tuple(item[key] for key in ('x', 'y', 'w', 'h'))


def _inside(a, b):
    return a[0] >= b[0] and a[1] >= b[1] and a[0]+a[2] <= b[0]+b[2] and a[1]+a[3] <= b[1]+b[3]


def _overlap(a, b):
    return a[0] < b[0]+b[2] and b[0] < a[0]+a[2] and a[1] < b[1]+b[3] and b[1] < a[1]+a[3]


def validate_structure(m, catalog, wrapped, header_rect):
    """Return ``(errors, warnings)`` without mutating a JSON-compatible model.

    ``catalog`` is the compiler's icon mapping; ``wrapped(text, width, font)``
    returns lines; ``header_rect(container)`` returns an absolute x/y/w/h tuple.
    Invalid primitive types stop validation before geometry or ancestry checks.
    """
    errors, warnings = [], []
    if not isinstance(m, dict):
        return ['Model must be a JSON object'], []

    provider = m.get('provider')
    if not isinstance(provider, str) or provider not in PROVIDERS:
        errors.append('provider must be aws, azure, gcp or multi')
    for key in ('width', 'height'):
        if not _finite(m.get(key)) or m[key] <= 0:
            errors.append(f'{key}: mandatory positive finite canvas dimension')
    for key in ('title', 'subtitle'):
        if key in m and not isinstance(m[key], str):
            errors.append(f'{key}: must be a string')
    notes = m.get('notes', [])
    if not isinstance(notes, list) or any(not isinstance(n, str) for n in notes):
        errors.append('notes: must be a list of strings')

    routing = m.get('routing', {})
    if not isinstance(routing, dict):
        errors.append('routing: must be an object')
    else:
        if not _finite(routing.get('clearance', 8)) or routing.get('clearance', 8) < 0:
            errors.append('routing.clearance: must be a finite number >= 0')
        if not _finite(routing.get('stub', 16)) or routing.get('stub', 16) <= 0:
            errors.append('routing.stub: must be a finite number > 0')

    collections = {}
    for name in ('containers', 'nodes', 'edges'):
        values = m.get(name, [])
        if not isinstance(values, list):
            errors.append(f'{name}: must be a list of objects')
            collections[name] = []
            continue
        collections[name] = []
        for index, item in enumerate(values):
            location = f'{name}[{index}]'
            if not isinstance(item, dict):
                errors.append(f'{location}: must be an object')
                continue
            collections[name].append(item)
            identifier = item.get('id')
            if not isinstance(identifier, str) or not identifier.strip():
                errors.append(f'{location}: ID must be a nonempty string')
            elif identifier in ('0', '1') or identifier.startswith('__'):
                errors.append(f'{location}: reserved ID {identifier!r}; use a stable resource-specific ID')
            label = identifier if isinstance(identifier, str) and identifier else location
            if name != 'edges':
                for key in ('x', 'y', 'w', 'h'):
                    if not _finite(item.get(key)):
                        errors.append(f'{label}: x/y/w/h must be finite numbers ({key})')
                for key in ('w', 'h'):
                    if _finite(item.get(key)) and item[key] <= 0:
                        errors.append(f'{label}: nonpositive size ({key})')
                if not isinstance(item.get('label'), str) or not item['label'].strip():
                    errors.append(f'{label}: label must be a nonempty string')
                for key in ('parent', 'zone'):
                    if key in item and (not isinstance(item[key], str) or not item[key]):
                        errors.append(f'{label}: {key} must be a nonempty string when supplied')
                if 'provider' in item and (not isinstance(item['provider'], str) or item['provider'] not in PROVIDERS):
                    errors.append(f'{label}: invalid provider')
            if name == 'containers':
                if not isinstance(item.get('kind'), str) or item['kind'] not in KINDS:
                    errors.append(f'{label}: unknown container kind')
                for key in ('overlay', 'public'):
                    if key in item and not isinstance(item[key], bool):
                        errors.append(f'{label}: {key} must be a boolean')
                if not isinstance(item.get('labelAlign', 'left'), str) or item.get('labelAlign', 'left') not in ('left', 'center', 'right'):
                    errors.append(f'{label}: labelAlign must be left, center or right')
                if 'labelOffset' in item and (not _finite(item['labelOffset']) or item['labelOffset'] < 0):
                    errors.append(f'{label}: labelOffset must be a finite number >= 0')
                elif item.get('labelOffset', 0) and item.get('labelAlign', 'left') != 'left':
                    errors.append(f'{label}: labelOffset is supported only with labelAlign=left')
            elif name == 'nodes':
                if not isinstance(item.get('icon', 'generic'), str):
                    errors.append(f'{label}: icon must be a string')
                if not isinstance(item.get('detail', ''), str):
                    errors.append(f'{label}: detail must be a string')
            else:
                for key in ('source', 'target'):
                    if not isinstance(item.get(key), str) or not item[key]:
                        errors.append(f'{label}: {key} must name a node ID')
                if not isinstance(item.get('label', ''), str):
                    errors.append(f'{label}: edge label must be a string')
                if not isinstance(item.get('kind', 'traffic'), str) or item.get('kind', 'traffic') not in EDGE_KINDS:
                    errors.append(f'{label}: unknown edge kind')
                for key in ('sourcePort', 'targetPort'):
                    if not isinstance(item.get(key, 'auto'), str) or item.get(key, 'auto') not in PORTS:
                        errors.append(f'{label}: invalid {key}')
                for key in ('sourceOffset', 'targetOffset'):
                    if key in item and (not _finite(item[key]) or not 0.1 <= item[key] <= 0.9):
                        errors.append(f'{label}: {key} must be a finite number from 0.1 to 0.9')
                if 'priority' in item and not _finite(item['priority']):
                    errors.append(f'{label}: priority must be a finite number')

    # No potentially malformed value reaches hashing, ancestry or geometry.
    if errors:
        return errors, warnings
    boxes, nodes, edges = (collections[k] for k in ('containers', 'nodes', 'edges'))
    ids = [item['id'] for item in boxes+nodes+edges]
    if len(set(ids)) != len(ids):
        return ['Duplicate IDs'], warnings
    box_by = {b['id']: b for b in boxes}
    node_ids = {n['id'] for n in nodes}
    page = (0, 0, m['width'], m['height'])

    def ancestors(item):
        result, seen = [], {item['id']}
        parent = item.get('parent')
        while parent in box_by and parent not in seen:
            seen.add(parent)
            result.append(box_by[parent])
            parent = box_by[parent].get('parent')
        return result

    def provider_of(item):
        for candidate in [item]+ancestors(item):
            if candidate.get('provider') in ('aws', 'azure', 'gcp'):
                return candidate['provider']
        return provider

    def fits(label, text, width, font, max_lines, remedy):
        if width <= 0 or len(wrapped(text, width, font)) > max_lines:
            errors.append(f'{label}: exceeds {max_lines} line(s) at {font}px; {remedy}')

    fits('title', m.get('title', 'Cloud architecture'), m['width']-60, 24, 1, 'widen canvas or shorten title')
    fits('subtitle', m.get('subtitle', ''), m['width']-60, 12, 1, 'widen canvas or shorten subtitle')
    fits('notes', ' · '.join(m.get('notes', [])), m['width']-60, 11, 2, 'shorten notes or move details to accompanying documentation')
    if m['height'] < 166:
        errors.append('height: reserve space for the page title and 90px footer')
    legend_count = len({e.get('kind', 'traffic') for e in edges})
    if legend_count and 30+(legend_count-1)*205+200 > m['width']-30:
        errors.append('legend: exceeds canvas width; widen canvas or split relationship types into separate views')

    for item in boxes+nodes:
        name, parent = item['id'], item.get('parent')
        if provider != 'multi' and 'provider' in item and item['provider'] != provider:
            errors.append(f'{name}: provider differs from single-provider diagram; use provider=multi for multiple CSPs')
        if not _inside(_rect(item), page):
            errors.append(f'{name}: outside canvas')
        if parent and parent not in box_by:
            errors.append(f'{name}: unknown container {parent}')
        if parent in box_by:
            p = box_by[parent]
            if not _inside(_rect(item), _rect(p)):
                errors.append(f'{name}: outside parent {parent}')
            if item['y'] < p['y']+34:
                errors.append(f'{name}: overlaps parent header')
        seen = {name}
        while parent in box_by:
            if parent in seen:
                errors.append(f'{name}: parent cycle')
                break
            seen.add(parent)
            parent = box_by[parent].get('parent')

    for b in boxes:
        owner, lineage = provider_of(b), ancestors(b)
        fits(f"{b['id']}: container label", b['label'], b['w']-24-b.get('labelOffset', 0), 14, 1, 'widen container, reduce labelOffset or shorten label')
        if (owner == 'azure' and b['kind'] == 'vpc') or (owner in ('aws', 'gcp') and b['kind'] == 'vnet'):
            errors.append(f"{b['id']}: provider/container mismatch ({owner} / {b['kind']})")
        if b['kind'] == 'subnet':
            if owner == 'aws' and not any(a['kind'] == 'az' for a in lineage):
                errors.append(f"{b['id']}: AWS subnet needs an AZ ancestor")
            if owner in ('azure', 'gcp') and any(a['kind'] == 'az' for a in lineage):
                errors.append(f"{b['id']}: {owner} subnet is regional, not zonal")
        if b['kind'] == 'group' and not b.get('overlay'):
            warnings.append(f"{b['id']}: consider overlay=true for cross-boundary logical groups")

    for n in nodes:
        icon, owner = n.get('icon', 'generic'), provider_of(n)
        if icon not in ('generic', 'generic.user') and icon not in catalog:
            errors.append(f"{n['id']}: unknown icon {icon}")
        if icon not in ('generic', 'generic.user') and owner != 'multi' and not icon.startswith(owner+'.'):
            errors.append(f"{n['id']}: provider/icon mismatch")
        if n['w'] < 100 or n['h'] < 124:
            errors.append(f"{n['id']}: resource card needs >=100x124")
        # Keep the original messages consumed by existing regression tests.
        if len(wrapped(n['label'], n['w']-8, 13)) > 2:
            errors.append(f"{n['id']}: title exceeds 2 lines; widen card or shorten label")
        if len(wrapped(n.get('detail', ''), n['w']-8, 11)) > 2:
            errors.append(f"{n['id']}: detail exceeds 2 lines; widen card or shorten detail")
        lineage = ancestors(n)
        if icon in OUTSIDE_SUBNET and any(p['kind'] in ('subnet', 'az') for p in lineage):
            errors.append(f"{n['id']}: managed/global service must not be placed inside subnet/AZ; model its endpoint separately")
        if owner == 'aws' and n.get('zone') and any(p.get('zone') and n['zone'] != p['zone'] for p in lineage if p['kind'] in ('subnet', 'az')):
            errors.append(f"{n['id']}: zone differs from subnet/AZ")

    for index, a in enumerate(nodes):
        for b in nodes[index+1:]:
            if _overlap(_rect(a), _rect(b)):
                errors.append(f"Resource overlap: {a['id']} / {b['id']}")
        for b in boxes:
            if _overlap(_rect(a), header_rect(b)):
                errors.append(f"{a['id']}: overlaps container title {b['id']}")
    for e in edges:
        for key in ('source', 'target'):
            if e[key] not in node_ids:
                errors.append(f"{e['id']}: missing {key} node")
        if e['source'] == e['target']:
            errors.append(f"{e['id']}: self-loop is unsupported; describe the internal operation in a separate detail view")
        fits(f"{e['id']}: edge label", e.get('label', ''), 228, 11, 1, 'shorten label to fit a 240px box or move details to notes')
    return errors, warnings
