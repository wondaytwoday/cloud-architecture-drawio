"""Structural, text-fit and selected CSP checks for the draw.io model.

This is deliberately not a network reachability or deployment validator.  The
compiler supplies its text wrapping and header geometry so validation uses the
same presentation assumptions as rendering.
"""
import difflib
import math
import re


PROVIDERS = {'aws', 'azure', 'gcp', 'multi'}
# Azure services that must have a subnet to themselves.
DEDICATED_SUBNETS = {'azure.appgateway': 'an Application Gateway', 'azure.firewall': 'an Azure Firewall (AzureFirewallSubnet)',
                     'azure.bastion': 'Azure Bastion (AzureBastionSubnet)', 'azure.vpn-gateway': 'a VPN gateway (GatewaySubnet)'}
# Drawn by the compiler itself rather than from the catalog.
BUILTIN_ICONS = ('generic', 'generic.user')
CSPS = ('aws', 'azure', 'gcp')
KINDS = {'cloud', 'account', 'project', 'region', 'vpc', 'vnet', 'az', 'subnet', 'group'}
NETWORK_KINDS = {'vpc', 'vnet', 'az', 'subnet'}
# Also the routing order and the legend order.
EDGE_KINDS = ('traffic', 'egress', 'replication', 'dns', 'association', 'management', 'event', 'connectivity')
# Boundaries a connector may start or end on: peering, attachments, VPN links.
ENDPOINT_KINDS = {'vpc', 'vnet', 'subnet', 'region', 'cloud', 'account', 'project'}
PORTS = {'auto', 'top', 'bottom', 'left', 'right'}
# Page bands reserved for the title/subtitle and for the legend/notes footer.
MARGIN_SIDE, MARGIN_TOP, MARGIN_BOTTOM = 10, 80, 90
LEGEND_TEXT_WIDTH = 160
# Edge caption text budget; the placed caption box adds 16px of padding.
EDGE_LABEL_TEXT_WIDTH = 228
LEGEND_NAMES = {
    'en': {'traffic': 'Request / data', 'egress': 'Outbound', 'replication': 'Replication',
           'dns': 'DNS resolution', 'association': 'Policy association', 'management': 'Management',
           'event': 'Event / message', 'connectivity': 'Network link'},
    'ko': {'traffic': '요청 / 데이터', 'egress': '아웃바운드', 'replication': '복제',
           'dns': 'DNS 조회', 'association': '정책 연결', 'management': '관리',
           'event': '이벤트 / 메시지', 'connectivity': '네트워크 연결'},
}

# Placement rules come from each catalog entry's `placement`:
#   managed  the service itself, never inside a subnet/AZ (its private endpoint is
#            a separate node); do not mark services with subnet-hosted modes
#   policy   associated with the resource it protects; it hosts nothing
#   network  attached to a VPC/network or region, not to one subnet or zone
#   subnet   takes an address in the subnet that hosts it
PLACEMENTS = ('any', 'managed', 'policy', 'network', 'subnet')

TOP_KEYS = {'provider', 'title', 'subtitle', 'width', 'height', 'routing', 'containers',
            'nodes', 'edges', 'notes', 'locale', 'legend'}
ITEM_KEYS = {
    'containers': {'id', 'kind', 'label', 'x', 'y', 'w', 'h', 'parent', 'provider', 'zone',
                   'public', 'overlay', 'labelAlign', 'labelOffset'},
    'nodes': {'id', 'label', 'x', 'y', 'w', 'h', 'icon', 'detail', 'parent', 'provider', 'zone'},
    'edges': {'id', 'source', 'target', 'label', 'kind', 'sourcePort', 'targetPort',
              'sourceOffset', 'targetOffset', 'priority'},
}
ROUTING_KEYS = {'clearance', 'stub'}
# Free-form metadata that the compiler keeps in the source but does not read.
METADATA_KEYS = {'evidence', 'assumptions', 'members', 'meta'}
ALIASES = {
    'containers': {'type': 'kind', 'name': 'label'},
    'nodes': {'type': 'icon', 'name': 'label', 'description': 'detail'},
    'edges': {'from': 'source', 'to': 'target', 'type': 'kind', 'name': 'label'},
}
# Characters that XML 1.0 cannot store, including lone UTF-16 surrogates.
ILLEGAL_TEXT = re.compile('[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff￾￿]')


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


def legend_captions(m):
    """Legend caption per edge kind: model overrides, then the locale's defaults."""
    names = dict(LEGEND_NAMES[m.get('locale', 'en')])
    names.update(m.get('legend', {}))
    return names


def _unknown_keys(where, item, known, aliases, errors, warnings):
    """Typos are errors because the compiler would silently use a default instead."""
    for key in item:
        if key in known or key in METADATA_KEYS or key.startswith(('x-', 'x_')):
            continue
        close = difflib.get_close_matches(key, sorted(known), n=1, cutoff=0.75)
        guess = aliases.get(key) or (close[0] if close else None)
        if guess and guess not in item:
            errors.append(f'{where}: unknown key {key!r}; did you mean {guess!r}?')
        elif guess:
            warnings.append(f'{where}: unknown key {key!r} is ignored (did you mean {guess!r}?)')
        else:
            warnings.append(f'{where}: unknown key {key!r} is ignored; keep metadata in evidence, assumptions, members, meta or an x- key')


def _illegal_text(m, errors):
    """Check only the fields the compiler writes; metadata never reaches the file."""
    fields = [(m.get(key), key) for key in ('title', 'subtitle')]
    if isinstance(m.get('notes'), list):
        fields += [(note, f'notes[{index}]') for index, note in enumerate(m['notes'])]
    if isinstance(m.get('legend'), dict):
        fields += [(caption, f'legend.{kind}') for kind, caption in m['legend'].items()]
    for name, keys in ITEM_KEYS.items():
        if isinstance(m.get(name), list):
            fields += [(item.get(key), f'{name}[{index}].{key}') for index, item in enumerate(m[name])
                       if isinstance(item, dict) for key in sorted(keys)]
    for value, path in fields:
        found = ILLEGAL_TEXT.search(value) if isinstance(value, str) else None
        if found:
            errors.append(f'{path}: contains U+{ord(found.group()):04X}, which a .drawio file cannot store; remove it or use \\n for a line break')


def validate_structure(m, catalog, wrapped, header_rect):
    """Return ``(errors, warnings)`` without mutating a JSON-compatible model.

    ``catalog`` is the compiler's icon mapping; ``wrapped(text, width, font)``
    returns lines; ``header_rect(container)`` returns an absolute x/y/w/h tuple.
    Invalid primitive types stop validation before geometry or ancestry checks.
    """
    errors, warnings = [], []
    if not isinstance(m, dict):
        return ['Model must be a JSON object'], []

    # Misspelled keys never block the primitive checks, so report them alongside.
    key_errors = []
    _unknown_keys('model', m, TOP_KEYS, {}, key_errors, warnings)
    if isinstance(m.get('routing'), dict):
        _unknown_keys('routing', m['routing'], ROUTING_KEYS, {}, key_errors, warnings)
    _illegal_text(m, errors)

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
    locale = m.get('locale', 'en')
    if not isinstance(locale, str) or locale not in LEGEND_NAMES:
        errors.append(f"locale: must be one of {', '.join(sorted(LEGEND_NAMES))}; use legend for other languages")
    legend = m.get('legend', {})
    if not isinstance(legend, dict):
        errors.append('legend: must be an object mapping edge kinds to captions')
    else:
        for kind, caption in legend.items():
            if kind not in EDGE_KINDS:
                errors.append(f"legend.{kind}: unknown edge kind; use {', '.join(EDGE_KINDS)}")
            elif not isinstance(caption, str) or not caption.strip():
                errors.append(f'legend.{kind}: caption must be a nonempty string')

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
            _unknown_keys(label, item, ITEM_KEYS[name], ALIASES[name], key_errors, warnings)
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
                if item.get('overlay') is True and item.get('kind') != 'group':
                    errors.append(f"{label}: overlay is supported only on kind=group; a {item.get('kind')} is network placement, not membership, so use an overlay group for cross-boundary memberships")
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
        return errors+key_errors, warnings
    errors.extend(key_errors)
    boxes, nodes, edges = (collections[k] for k in ('containers', 'nodes', 'edges'))
    ids = [item['id'] for item in boxes+nodes+edges]
    if len(set(ids)) != len(ids):
        return ['Duplicate IDs']+errors, warnings
    box_by = {b['id']: b for b in boxes}
    node_ids = {n['id'] for n in nodes}
    nodes_by = {n['id']: n for n in nodes}
    solid = [b for b in boxes if not b.get('overlay')]
    width, height = m['width'], m['height']
    page = (0, 0, width, height)
    usable = (MARGIN_SIDE, MARGIN_TOP, width-2*MARGIN_SIDE, height-MARGIN_TOP-MARGIN_BOTTOM)

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
            if candidate.get('provider') in CSPS:
                return candidate['provider']
        return provider

    def fits(label, text, width, font, max_lines, remedy):
        if width <= 0 or len(wrapped(text, width, font)) > max_lines:
            errors.append(f'{label}: exceeds {max_lines} line(s) at {font}px; {remedy}')

    fits('title', m.get('title', 'Cloud architecture'), width-60, 24, 1, 'widen canvas or shorten title')
    fits('subtitle', m.get('subtitle', ''), width-60, 12, 1, 'widen canvas or shorten subtitle')
    fits('notes', ' · '.join(m.get('notes', [])), width-60, 11, 2, 'shorten notes or move details to accompanying documentation')
    if height < MARGIN_TOP+MARGIN_BOTTOM-4:
        errors.append('height: reserve space for the page title and 90px footer')
    kinds = sorted({e.get('kind', 'traffic') for e in edges}, key=EDGE_KINDS.index)
    if kinds and 30+(len(kinds)-1)*205+200 > width-30:
        errors.append('legend: exceeds canvas width; widen canvas or split relationship types into separate views')
    captions = legend_captions(m)
    for kind in kinds:
        fits(f'legend.{kind}', captions[kind], LEGEND_TEXT_WIDTH, 11, 1, f'shorten the caption to fit {LEGEND_TEXT_WIDTH}px')

    misplaced = set()
    for item in boxes+nodes:
        name, parent = item['id'], item.get('parent')
        if provider != 'multi' and 'provider' in item and item['provider'] != provider:
            errors.append(f'{name}: provider differs from single-provider diagram; use provider=multi for multiple CSPs')
        if not _inside(_rect(item), page):
            errors.append(f'{name}: outside canvas')
        elif not _inside(_rect(item), usable):
            x, y, w, h = _rect(item)
            bands = [band for band, hit in (
                ('title band (top 80px)', y < MARGIN_TOP),
                ('legend/notes footer (bottom 90px)', y+h > height-MARGIN_BOTTOM),
                ('side margin (10px)', x < MARGIN_SIDE or x+w > width-MARGIN_SIDE)) if hit]
            errors.append(f"{name}: enters the reserved {' and '.join(bands)}; keep shapes within x {MARGIN_SIDE}..{width-MARGIN_SIDE}, y {MARGIN_TOP}..{height-MARGIN_BOTTOM}")
        if parent and parent not in box_by:
            errors.append(f'{name}: unknown container {parent}')
            misplaced.add(name)
        if parent in box_by:
            p = box_by[parent]
            if not _inside(_rect(item), _rect(p)):
                x, y, w, h = _rect(item)
                beyond = [(side, amount) for side, amount in (('left', p['x']-x), ('top', p['y']-y),
                          ('right', x+w-p['x']-p['w']), ('bottom', y+h-p['y']-p['h'])) if amount > 0]
                errors.append(f"{name}: outside parent {parent} ({', '.join(f'{side} edge {amount:g}px beyond' for side, amount in beyond)})")
                misplaced.add(name)
            if item['y'] < p['y']+34:
                errors.append(f"{name}: overlaps parent header (starts {item['y']-p['y']:g}px below {parent}'s top; needs 34px)")
        seen = {name}
        while parent in box_by:
            if parent in seen:
                errors.append(f'{name}: parent cycle')
                misplaced.add(name)
                break
            seen.add(parent)
            parent = box_by[parent].get('parent')

    # Geometry and the declared hierarchy must agree: draw.io nests cells under
    # their declared parent, and the CSP rules below read that hierarchy.
    def enclosing(item):
        """Non-overlay containers that fully contain the item, innermost first."""
        lineage = {a['id'] for a in ancestors(item)}
        found = [b for b in solid if b['id'] != item['id'] and _inside(_rect(item), _rect(b))]
        return sorted(found, key=lambda b: (b['w']*b['h'], b['id'] not in lineage))

    for item in solid+nodes:
        if item['id'] in misplaced:
            continue
        inner = enclosing(item)
        actual = inner[0] if inner else None
        declared = next((a for a in ancestors(item) if not a.get('overlay')), None)
        if actual is not None and actual is not declared and (declared is None or _rect(actual) != _rect(declared)):
            where = f"{declared['kind']} {declared['id']}" if declared else 'the page'
            errors.append(f"{item['id']}: drawn inside {actual['kind']} {actual['id']} but its nearest declared parent is {where}; set parent to {actual['id']!r} or move it")
    for n in nodes:
        for b in solid:
            if _overlap(_rect(n), _rect(b)) and not _inside(_rect(n), _rect(b)):
                errors.append(f"{n['id']}: straddles the border of {b['kind']} {b['id']}; move it fully inside or outside")
    for index, a in enumerate(solid):
        for b in solid[index+1:]:
            ra, rb = _rect(a), _rect(b)
            if _overlap(ra, rb) and not _inside(ra, rb) and not _inside(rb, ra):
                errors.append(f"Container overlap: {a['id']} / {b['id']} cross each other's borders; nest one inside the other or separate them")

    # In a multi-provider diagram, infer an unmarked network boundary's provider
    # from the product icons it holds so the provider rules still apply.
    node_ids_set = {id(n) for n in nodes}

    def declared_provider(item):
        """Explicit or inherited provider, else a product icon's provider, else multi."""
        own = provider_of(item)
        if own != 'multi' or id(item) not in node_ids_set:
            return own
        prefix = item.get('icon', 'generic').split('.')[0]
        return prefix if prefix in CSPS else 'multi'

    inferred = {}
    if provider == 'multi':
        # Only network boundaries are inferred; a region, account or cloud box
        # may legitimately frame several providers' networks.
        for b in boxes:
            if b['kind'] not in NETWORK_KINDS or provider_of(b) != 'multi':
                continue
            found = sorted({declared_provider(x) for x in boxes+nodes if b in ancestors(x)} & set(CSPS))
            if len(found) == 1:
                inferred[b['id']] = found[0]
            elif found:
                errors.append(f"{b['id']}: {b['kind']} holds resources of several providers ({', '.join(found)}); give each provider its own boundary")
            else:
                warnings.append(f"{b['id']}: set provider on this {b['kind']} so provider-specific rules apply")
        for item in boxes+nodes:
            mine = item.get('provider')
            clash = next((a for a in ancestors(item) if not a.get('overlay') and a.get('provider') in CSPS and a['provider'] != mine), None)
            if mine in CSPS and clash:
                errors.append(f"{item['id']}: provider {mine} conflicts with {clash['id']} ({clash['provider']})")

    def owner_of(item):
        owner = provider_of(item)
        if owner != 'multi':
            return owner
        for candidate in [item]+ancestors(item):
            if candidate['id'] in inferred:
                return inferred[candidate['id']]
        return declared_provider(item)

    for b in boxes:
        owner, lineage = owner_of(b), ancestors(b)
        solid_lineage = [a for a in lineage if not a.get('overlay')]
        fits(f"{b['id']}: container label", b['label'], b['w']-24-b.get('labelOffset', 0), 14, 1, 'widen container, reduce labelOffset or shorten label')
        if (owner == 'azure' and b['kind'] == 'vpc') or (owner in ('aws', 'gcp') and b['kind'] == 'vnet'):
            errors.append(f"{b['id']}: provider/container mismatch ({owner} / {b['kind']})")
        if b['kind'] in ('vpc', 'vnet') and any(a['kind'] in ('subnet', 'az') for a in solid_lineage):
            errors.append(f"{b['id']}: a {b['kind']} cannot sit inside a subnet or AZ")
        if b['kind'] in ('vpc', 'vnet') and any(a['kind'] in ('vpc', 'vnet') for a in solid_lineage):
            errors.append(f"{b['id']}: a {b['kind']} cannot sit inside another VPC/VNet; draw peered networks side by side")
        if b['kind'] in ('subnet', 'az') and any(a['kind'] == 'subnet' for a in solid_lineage):
            errors.append(f"{b['id']}: a {b['kind']} cannot sit inside a subnet")
        if b['kind'] == 'subnet':
            if owner == 'aws' and not any(a['kind'] == 'az' for a in lineage):
                errors.append(f"{b['id']}: AWS subnet needs an AZ ancestor")
            if owner in ('azure', 'gcp') and any(a['kind'] == 'az' for a in lineage):
                errors.append(f"{b['id']}: {owner} subnet is regional, not zonal")
            network = 'vnet' if owner == 'azure' else 'vpc'
            if owner in CSPS and not any(a['kind'] == network for a in lineage):
                errors.append(f"{b['id']}: {owner} subnet needs a {network} ancestor")
            zone_box = next((a for a in lineage if a['kind'] == 'az' and a.get('zone')), None)
            if b.get('zone') and zone_box and zone_box['zone'] != b['zone']:
                errors.append(f"{b['id']}: zone differs from AZ {zone_box['id']}")
        if b['kind'] == 'group' and not b.get('overlay'):
            warnings.append(f"{b['id']}: consider overlay=true for cross-boundary logical groups")

    def subnet_of(n):
        return next((a for a in ancestors(n) if a['kind'] == 'subnet'), None)

    def subnets_of(n):
        return [a for a in ancestors(n) if a['kind'] == 'subnet']

    for n in nodes:
        icon, owner = n.get('icon', 'generic'), owner_of(n)
        if icon not in BUILTIN_ICONS and icon not in catalog:
            close = difflib.get_close_matches(icon, sorted(catalog), n=1, cutoff=0.6)
            hint = f'; did you mean {close[0]!r}?' if close else '; list keys with `cloud_drawio.py icons` or see references/assets.md'
            errors.append(f"{n['id']}: unknown icon {icon}{hint}")
        # generic.* glyphs are provider-neutral and fit any diagram.
        if not icon.startswith('generic') and owner != 'multi' and not icon.startswith(owner+'.'):
            errors.append(f"{n['id']}: provider/icon mismatch")
        if n['w'] < 100 or n['h'] < 124:
            errors.append(f"{n['id']}: resource card needs >=100x124")
        # Keep the original messages consumed by existing regression tests.
        if len(wrapped(n['label'], n['w']-8, 13)) > 2:
            errors.append(f"{n['id']}: title exceeds 2 lines; widen card or shorten label")
        if len(wrapped(n.get('detail', ''), n['w']-8, 11)) > 2:
            errors.append(f"{n['id']}: detail exceeds 2 lines; widen card or shorten detail")
        # A wrongly declared parent must not hide a placement drawn on the page.
        lineage = ancestors(n)
        lineage += [b for b in enclosing(n) if b not in lineage]
        zonal = any(p['kind'] in ('subnet', 'az') for p in lineage)
        placement = catalog.get(icon, {}).get('placement', 'any')
        if placement == 'managed' and zonal:
            errors.append(f"{n['id']}: managed/global service must not be placed inside subnet/AZ; model its endpoint separately")
        if placement == 'policy' and zonal:
            errors.append(f"{n['id']}: {icon} is a policy association, not a host; place it outside subnets/AZs and draw an association edge to the protected service")
        if placement == 'network' and zonal:
            errors.append(f"{n['id']}: {icon} attaches to the VPC/network, not to a subnet or AZ; place it outside subnets/AZs")
        if placement == 'subnet' and not any(p['kind'] == 'subnet' for p in lineage):
            errors.append(f"{n['id']}: {icon} takes an address in a subnet; place it inside the subnet that hosts it")
        if owner == 'aws' and n.get('zone') and any(p.get('zone') and n['zone'] != p['zone'] for p in lineage if p['kind'] in ('subnet', 'az')):
            errors.append(f"{n['id']}: zone differs from subnet/AZ")

    # Azure gateways and firewalls each need a subnet of their own; Application
    # Gateway's must not be GatewaySubnet.
    dedicated = {}
    for n in nodes:
        if n.get('icon') in DEDICATED_SUBNETS and subnet_of(n):
            dedicated.setdefault(subnet_of(n)['id'], n['icon'])
    for n in nodes:
        home = next((s for s in subnets_of(n) if s['id'] in dedicated), None)
        if home and n.get('icon') != dedicated[home['id']]:
            errors.append(f"{n['id']}: subnet {home['id']} hosts {DEDICATED_SUBNETS[dedicated[home['id']]]} and must be dedicated to it; move this resource to another subnet")
    gateway_subnets = {sid for sid, icon in dedicated.items() if icon == 'azure.appgateway'}
    for sid in sorted(gateway_subnets):
        if re.search(r'\bGatewaySubnet\b', box_by[sid]['label']):
            errors.append(f"{sid}: GatewaySubnet is reserved for VPN/ExpressRoute gateways; give the Application Gateway subnet another name")

    # Two titles in one place print over each other.
    for index, a in enumerate(boxes):
        for b in boxes[index+1:]:
            if _overlap(header_rect(a), header_rect(b)):
                errors.append(f"{a['id']} / {b['id']}: container titles overlap; set labelAlign or labelOffset on one, or move it")
    for index, a in enumerate(nodes):
        for b in nodes[index+1:]:
            if _overlap(_rect(a), _rect(b)):
                errors.append(f"Resource overlap: {a['id']} / {b['id']}")
        for b in boxes:
            if _overlap(_rect(a), header_rect(b)):
                errors.append(f"{a['id']}: overlaps container title {b['id']}")
    def inside(outer, inner):
        return outer in ancestors(inner)

    for e in edges:
        for key in ('source', 'target'):
            box = box_by.get(e[key])
            if box is not None and (box['kind'] not in ENDPOINT_KINDS or box.get('overlay')):
                errors.append(f"{e['id']}: {key} {e[key]} is a {box['kind']}; connectors end on nodes or on {', '.join(sorted(ENDPOINT_KINDS))} boundaries")
            elif box is None and e[key] not in node_ids:
                errors.append(f"{e['id']}: missing {key} node")
        ends = [box_by.get(e['source']) or nodes_by.get(e['source']), box_by.get(e['target']) or nodes_by.get(e['target'])]
        if all(ends) and e['source'] != e['target'] and (inside(ends[0], ends[1]) or inside(ends[1], ends[0])):
            errors.append(f"{e['id']}: connects a boundary to something inside it; attach it to a node or to a sibling boundary")
        if e['source'] == e['target']:
            errors.append(f"{e['id']}: self-loop is unsupported; describe the internal operation in a separate detail view")
        fits(f"{e['id']}: edge label", e.get('label', ''), EDGE_LABEL_TEXT_WIDTH, 11, 1, f'shorten label to about {EDGE_LABEL_TEXT_WIDTH}px of text (a {EDGE_LABEL_TEXT_WIDTH+16}px caption box) or move details to notes')
    return errors, warnings
