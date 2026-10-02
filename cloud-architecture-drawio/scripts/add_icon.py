#!/usr/bin/env python3
"""Search the pinned draw.io icon libraries and add an icon to the catalog.

    python3 scripts/add_icon.py search aws4 dynamodb
    python3 scripts/add_icon.py add aws.dynamodb --from aws4:dynamodb --color '#C925D1' --placement managed
    python3 scripts/add_icon.py add azure.cosmos --from azure2:databases/Azure_Cosmos_DB.svg --placement managed

Libraries come from one jgraph/drawio commit, so every catalog entry has an
immutable source. Downloads are cached in $CLOUD_DRAWIO_CACHE (default
~/.cache/cloud-architecture-drawio). Stencils are written in the same normalized
form as the bundled ones; SVGs are kept byte for byte after a safety check.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT/'assets/icon-catalog.json'
COMMIT = '82af434539c3449d99275b91a91b6b99998a7d58'
CACHE = Path(os.environ.get('CLOUD_DRAWIO_CACHE') or Path.home()/'.cache/cloud-architecture-drawio')/f'drawio-{COMMIT[:8]}'
RAW = f'https://raw.githubusercontent.com/jgraph/drawio/{COMMIT}/src/main/webapp'
BLOB = f'https://github.com/jgraph/drawio/blob/{COMMIT}/src/main/webapp'
# Stencil libraries and the catalog prefix their icons belong to.
STENCILS = {'aws4': 'aws', 'gcp2': 'gcp', 'networks': 'generic'}
SVG_LIBRARY, SVG_PREFIX = 'azure2', 'azure'
PLACEMENTS = ('any', 'managed', 'policy', 'network', 'subnet')
UNSAFE_SVG = ('<script', '<foreignobject', 'href="http', "href='http", 'url(http', 'javascript:')


def fetch(relative):
    """Return a cached library file, downloading it from the pinned commit once."""
    target = CACHE/relative
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(f'{RAW}/{relative}', timeout=60) as response:
            data = response.read()
        tmp = target.with_name(target.name+'.tmp')
        tmp.write_bytes(data)
        os.replace(tmp, target)
    return target.read_bytes()


def stencil_library(name):
    return ET.fromstring(fetch(f'stencils/{name}.xml'))


def azure_index():
    """Category/File.svg names of the azure2 SVG library at the pinned commit."""
    index = CACHE/'azure2/index.txt'
    if not index.exists():
        api = f'https://api.github.com/repos/jgraph/drawio/contents/src/main/webapp/img/lib/azure2?ref={COMMIT}'
        with urllib.request.urlopen(api, timeout=60) as response:
            categories = [entry['name'] for entry in json.load(response) if entry['type'] == 'dir']
        names = []
        for category in categories:
            with urllib.request.urlopen(f'{api.split("?")[0]}/{category}?ref={COMMIT}', timeout=60) as response:
                names += [f"{category}/{entry['name']}" for entry in json.load(response) if entry['name'].endswith('.svg')]
        index.parent.mkdir(parents=True, exist_ok=True)
        index.write_text('\n'.join(sorted(names))+'\n', encoding='utf-8')
    return [line for line in index.read_text(encoding='utf-8').splitlines() if line]


def search(library, text):
    text = text.lower()
    if library == SVG_LIBRARY:
        return [name for name in azure_index() if text in name.lower()]
    if library not in STENCILS:
        raise ValueError(f'unknown library {library!r}; use {", ".join([*STENCILS, SVG_LIBRARY])}')
    return [shape.get('name') for shape in stencil_library(library).iter('shape') if text in shape.get('name', '').lower()]


def extract(library, name):
    """Return (kind, bytes, source URL) for one icon of a pinned library."""
    if library == SVG_LIBRARY:
        if name not in azure_index():
            raise ValueError(f'{name!r} is not in {library}; try: add_icon.py search {library} {Path(name).stem[:8]}')
        data = fetch(f'img/lib/azure2/{name}')
        text = data.decode('utf-8').lower()
        unsafe = [token for token in UNSAFE_SVG if token in text]
        if unsafe:
            raise ValueError(f'{name}: refusing an SVG with {", ".join(unsafe)}')
        return 'svg', data, f'{RAW}/img/lib/azure2/{name}'
    shape = next((s for s in stencil_library(library).iter('shape') if s.get('name') == name), None)
    if shape is None:
        close = search(library, name.split()[0])[:5]
        raise ValueError(f'no stencil {name!r} in {library}' + (f'; close names: {close}' if close else ''))
    # The bundled stencils use exactly this normalization.
    shape = ET.fromstring(ET.tostring(shape))
    ET.indent(shape, space='    ')
    return 'stencil', (ET.tostring(shape, encoding='unicode')+'\n').encode('utf-8'), f'{BLOB}/stencils/{library}.xml'


def add(key, source, color=None, stroke=None, placement='any', force=False, catalog_path=CATALOG):
    library, _, name = source.partition(':')
    prefix = SVG_PREFIX if library == SVG_LIBRARY else STENCILS.get(library)
    if not prefix or not name:
        raise ValueError('--from must be LIBRARY:NAME, e.g. aws4:dynamodb or azure2:databases/Azure_Cosmos_DB.svg')
    if not re.fullmatch(rf'{prefix}\.[a-z0-9-]+', key):
        raise ValueError(f'{key!r}: icons from {library} need a key like {prefix}.service-name')
    if placement not in PLACEMENTS:
        raise ValueError(f'placement must be one of {", ".join(PLACEMENTS)}')
    catalog = json.loads(catalog_path.read_text(encoding='utf-8'))
    if key in catalog and not force:
        raise ValueError(f'{key} is already in the catalog; pass --force to replace it')
    kind, data, url = extract(library, name)
    entry = {'file': f"icons/{key.replace('.', '-')}.{'svg' if kind == 'svg' else 'xml'}", 'kind': kind}
    if kind == 'stencil':
        if not color or not re.fullmatch(r'#[0-9A-Fa-f]{6}', color):
            raise ValueError('stencils are monochrome; pass --color #RRGGBB (the provider category colour)')
        entry['color'] = color.upper()
        if stroke:
            entry['stroke'] = stroke.upper()
    entry['name'] = Path(name).stem if kind == 'svg' else name
    entry['source'] = url
    entry['sha256'] = hashlib.sha256(data).hexdigest()
    if placement != 'any':
        entry['placement'] = placement
    target = catalog_path.parent/entry['file']
    target.write_bytes(data)
    catalog[key] = entry
    catalog_path.write_text(json.dumps(catalog, indent=2)+'\n', encoding='utf-8')
    return entry


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('search', help='list icon names containing TEXT')
    s.add_argument('library', choices=[*STENCILS, SVG_LIBRARY])
    s.add_argument('text')
    a = sub.add_parser('add', help='copy one icon into assets/icons and the catalog')
    a.add_argument('key', help='catalog key, e.g. aws.dynamodb')
    a.add_argument('--from', dest='source', required=True, help='LIBRARY:NAME from search')
    a.add_argument('--color', help='stencil fill colour #RRGGBB')
    a.add_argument('--stroke', help='stencil stroke colour, for outlined generic glyphs')
    a.add_argument('--placement', default='any', choices=PLACEMENTS,
                   help='managed: service outside subnets/AZs; policy: association only; network: VPC-level; subnet: needs a subnet')
    a.add_argument('--force', action='store_true')
    args = parser.parse_args()
    try:
        if args.cmd == 'search':
            print('\n'.join(search(args.library, args.text)) or 'no match')
        else:
            print(json.dumps({args.key: add(args.key, args.source, args.color, args.stroke, args.placement, args.force)}, indent=2))
    except (ValueError, OSError) as exc:
        parser.exit(1, f'{exc}\n')


if __name__ == '__main__':
    main()
