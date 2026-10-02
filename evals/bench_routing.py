#!/usr/bin/env python3
"""Routing benchmark: build success and layout quality over a fixed corpus.

Run one compiler version per process and compare the JSON summaries:

    python3 evals/bench_routing.py --out new.json
    python3 evals/bench_routing.py --scripts /path/to/old/scripts --out old.json
    python3 evals/bench_routing.py --compare old.json new.json

The corpus is deterministic: the shipped examples with layout shorthands
resolved, the same examples with every port set to auto, random grids with and
without captions at several lane widths, labeled 1-to-N fan-outs, and grids
wrapped in subnet boundaries. Metrics are
computed here, independently of the compiler's own report.
"""
import argparse
import copy
import importlib.util
import json
from pathlib import Path
import random
import statistics
import sys
import time

BASE = Path(__file__).resolve().parents[1]
CARD_W, CARD_H = 156, 124
LABELS = ['HTTPS 443', 'TCP 5432', 'gRPC', 'Replication', 'DNS', 'HTTPS']


def load(scripts):
    sys.path.insert(0, str(scripts))
    spec = importlib.util.spec_from_file_location('bench_compiler', Path(scripts)/'cloud_drawio.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    import cloud_routes
    return module, cloud_routes


def absolute(m):
    """Resolve layout shorthands with this checkout's resolver, so any compiler version can run the case."""
    spec = importlib.util.spec_from_file_location('corpus_layout', BASE/'cloud-architecture-drawio/scripts/model_layout.py')
    layout = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(layout)
    return layout.normalize(m)


def card(i, x, y):
    return {'id': f'n{i}', 'label': f'Service {i}', 'icon': 'generic', 'x': x, 'y': y, 'w': CARD_W, 'h': CARD_H}


def grid(seed, nodes, edges, gap, labeled, subnets=False):
    rnd = random.Random(seed)
    cols = max(2, round((nodes*1.6)**.5))
    rows = (nodes+cols)//cols+1
    cells = rnd.sample([(r, c) for r in range(rows) for c in range(cols)], nodes)
    left, top = 60, 210 if subnets else 160
    ns = [card(i, left+c*(CARD_W+gap), top+r*(CARD_H+gap)) for i, (r, c) in enumerate(cells)]
    width = left*2+cols*(CARD_W+gap)
    height = top+rows*(CARD_H+gap)+120
    pairs = set()
    while len(pairs) < edges:
        a, b = rnd.sample(range(nodes), 2)
        if (b, a) not in pairs:
            pairs.add((a, b))
    es = []
    for k, (a, b) in enumerate(sorted(pairs)):
        e = {'id': f'e{k}', 'source': f'n{a}', 'target': f'n{b}', 'kind': rnd.choice(['traffic']*4+['dns', 'replication', 'egress'])}
        if labeled and rnd.random() < .7:
            e['label'] = rnd.choice(LABELS)
        es.append(e)
    m = {'provider': 'gcp' if subnets else 'aws', 'title': f'grid {seed}', 'width': width, 'height': height,
         'containers': [], 'nodes': ns, 'edges': es}
    if subnets:
        m['containers'] = [{'id': 'project', 'kind': 'project', 'label': 'Project', 'x': 20, 'y': 90, 'w': width-40, 'h': height-200},
                           {'id': 'vpc', 'kind': 'vpc', 'label': 'VPC', 'x': 30, 'y': 126, 'w': width-60, 'h': height-246, 'parent': 'project'}]
        for c in range(cols):
            inside = [n for n in ns if n['x'] == left+c*(CARD_W+gap)]
            if not inside:
                continue
            x = left+c*(CARD_W+gap)-12
            m['containers'].append({'id': f'sn{c}', 'kind': 'subnet', 'label': f'Subnet {c}', 'parent': 'vpc',
                                    'x': x, 'y': top-46, 'w': CARD_W+24, 'h': rows*(CARD_H+gap)-gap+60})
            for n in inside:
                n['parent'] = f'sn{c}'
        for n in ns:
            n['parent'] = n.get('parent', 'vpc')
    return m


def fanout(seed, targets, gap):
    rnd = random.Random(seed)
    span = targets*CARD_W+(targets-1)*gap
    width = max(600, span+160)
    hub = {'id': 'hub', 'label': 'Load balancer', 'icon': 'generic', 'x': (width-CARD_W)//2, 'y': 160, 'w': CARD_W, 'h': CARD_H}
    ns = [hub]+[card(i, 80+i*(CARD_W+gap), 160+CARD_H+rnd.choice([120, 160, 200])) for i in range(targets)]
    es = [{'id': f'e{i}', 'source': 'hub', 'target': f'n{i}', 'label': 'HTTPS 443'} for i in range(targets)]
    return {'provider': 'aws', 'title': f'fanout {targets}', 'width': width, 'height': 160+CARD_H+200+CARD_H+150,
            'containers': [], 'nodes': ns, 'edges': es}


def corpus():
    cases = []
    examples = sorted((BASE/'examples').glob('*.model.json'))
    for path in examples:
        m = absolute(json.loads(path.read_text(encoding='utf-8')))
        cases.append(('examples', path.stem, m))
        auto = copy.deepcopy(m)
        for e in auto['edges']:
            for key in ('sourcePort', 'targetPort', 'sourceOffset', 'targetOffset'):
                e.pop(key, None)
        cases.append(('examples-auto-ports', path.stem, auto))
    for gap in (74, 144):
        cases += [(f'small-unlabeled-gap{gap}', s, grid(s, 5, 4, gap, False)) for s in range(150)]
    for gap in (74, 100, 144):
        cases += [(f'labeled-gap{gap}', s, grid(1000+s, 6, 6, gap, True)) for s in range(100)]
    for nodes, edges in ((8, 8), (10, 12), (12, 16)):
        cases += [(f'dense-{nodes}x{edges}', s, grid(2000+s, nodes, edges, 110, True)) for s in range(60)]
    for targets in (2, 3, 4, 5):
        cases += [(f'fanout-{targets}', s, fanout(3000+s, targets, rnd_gap)) for s, rnd_gap in enumerate((60, 90, 120, 160))]
    cases += [('subnets', s, grid(4000+s, 8, 9, 110, True, subnets=True)) for s in range(60)]
    return cases


def borders(m):
    for c in m['containers']:
        if c.get('overlay'):
            continue
        x, y, w, h = c['x'], c['y'], c['w'], c['h']
        yield ((x, y), (x+w, y)); yield ((x, y+h), (x+w, y+h)); yield ((x, y), (x, y+h)); yield ((x+w, y), (x+w, y+h))


def hug_length(m, routes, within=4, minimum=20):
    """Route length running parallel to a container border within a few pixels."""
    total = 0
    for pts in routes.values():
        for a, b in zip(pts, pts[1:]):
            for c, d in borders(m):
                axis = 1 if a[1] == b[1] and c[1] == d[1] else 0 if a[0] == b[0] and c[0] == d[0] else None
                if axis is None or abs(a[axis]-c[axis]) > within:
                    continue
                other = 1-axis
                run = min(max(a[other], b[other]), max(c[other], d[other]))-max(min(a[other], b[other]), min(c[other], d[other]))
                if run >= minimum:
                    total += run
    return total


def jogs(routes, limit=12):
    """Interior segments shorter than limit px: staircases beside aligned cards."""
    return sum(1 for pts in routes.values() for a, b in list(zip(pts, pts[1:]))[1:-1]
               if abs(a[0]-b[0])+abs(a[1]-b[1]) <= limit)


def joins(routes, limit=24, offset=10):
    """Segment pairs of two connectors on (nearly) one line whose ends are under
    limit px apart, so the two connectors read as one line."""
    def gap(a, b, c, d):
        for axis in (0, 1):
            other = 1-axis
            if a[other] == b[other] and c[other] == d[other] and abs(a[other]-c[other]) < offset:
                return max(min(a[axis], b[axis]), min(c[axis], d[axis]))-min(max(a[axis], b[axis]), max(c[axis], d[axis]))
        return None
    items = list(routes.values())
    count = 0
    for i, ap in enumerate(items):
        for bp in items[i+1:]:
            count += sum(1 for a, b in zip(ap, ap[1:]) for c, d in zip(bp, bp[1:])
                         if 0 < (gap(a, b, c, d) or 0) < limit)
    return count


def label_quality(routes, labels, overhang_limit=4, near=6):
    """Captions hanging past the end of their segment, and captions closer than
    `near` px to another connector, where they may read as that line's label."""
    overhang = crowded = 0
    for eid, label in labels.items():
        x, y, w, h = label['rect']
        ax, ay = x-label['offset'][0], y-label['offset'][1]
        pts = routes[eid]
        for a, b in zip(pts, pts[1:]):
            if min(a[0], b[0])-.01 <= ax <= max(a[0], b[0])+.01 and min(a[1], b[1])-.01 <= ay <= max(a[1], b[1])+.01:
                lo, hi, start, end = (x, x+w, min(a[0], b[0]), max(a[0], b[0])) if a[1] == b[1] else (y, y+h, min(a[1], b[1]), max(a[1], b[1]))
                overhang += start-lo > overhang_limit or hi-end > overhang_limit
                break

        def gap(a, b):
            dx = max(x-max(a[0], b[0]), min(a[0], b[0])-x-w, 0)
            dy = max(y-max(a[1], b[1]), min(a[1], b[1])-y-h, 0)
            return (dx*dx+dy*dy)**.5
        crowded += min((gap(a, b) for other, line in routes.items() if other != eid for a, b in zip(line, line[1:])), default=1e9) <= near
    return overhang, crowded


def run(scripts):
    compiler, routing = load(scripts)
    results = []
    for group, name, m in corpus():
        errors, _ = compiler.validate(m)
        if errors:
            results.append({'group': group, 'name': name, 'status': 'invalid', 'detail': errors[0]})
            continue
        started = time.perf_counter()
        mode = None
        if hasattr(routing, 'route_and_label'):
            try:
                routes, _, labels, mode = routing.route_and_label(m, compiler.header_rect)
                status = 'ok'
            except ValueError as exc:
                # Classify by the stage that fails without the label stage.
                try:
                    routes, _ = routing.plan(m, compiler.header_rect)
                    status = 'label-fail'
                except ValueError:
                    results.append({'group': group, 'name': name, 'status': 'route-fail', 'detail': str(exc)[:160],
                                    'seconds': time.perf_counter()-started})
                    continue
        else:
            try:
                routes, _ = routing.plan(m, compiler.header_rect)
            except ValueError as exc:
                results.append({'group': group, 'name': name, 'status': 'route-fail', 'detail': str(exc)[:160],
                                'seconds': time.perf_counter()-started})
                continue
            try:
                labels = routing.place_labels(m, routes, compiler.header_rect)
                status = 'ok'
            except ValueError:
                status = 'label-fail'
        q = routing.metrics(routes)
        overhang, crowded = label_quality(routes, labels) if status == 'ok' else (0, 0)
        results.append({'group': group, 'name': name, 'status': status, 'mode': mode, 'seconds': time.perf_counter()-started,
                        'crossings': q['crossingCount'], 'bends': q['bendCount'], 'length': q['totalLength'],
                        'hug': hug_length(m, routes), 'jogs': jogs(routes), 'overhang': overhang, 'crowded': crowded,
                        'joins': joins(routes)})
    return results


def summarize(results):
    groups = {}
    for r in results:
        groups.setdefault(r['group'], []).append(r)
    out = {}
    for group, items in groups.items():
        valid = [r for r in items if r['status'] != 'invalid']
        ok = [r for r in valid if r['status'] == 'ok']
        out[group] = {'cases': len(valid), 'invalid': len(items)-len(valid), 'ok': len(ok),
                      'route_fail': sum(r['status'] == 'route-fail' for r in valid),
                      'label_fail': sum(r['status'] == 'label-fail' for r in valid),
                      'seconds_median': round(statistics.median([r['seconds'] for r in valid]), 3) if valid else None}
    return out


def compare(old_path, new_path):
    old, new = (json.loads(Path(p).read_text(encoding='utf-8')) for p in (old_path, new_path))
    index = {(r['group'], str(r['name'])): r for r in old['results']}
    print(f"{'group':28} {'ok old→new':>12} {'route-fail':>12} {'label-fail':>12}  common-ok: crossings, bends, length, hug, jogs, overhang, crowded, joins (old→new)")
    for group in sorted(new['summary']):
        o, n = old['summary'].get(group, {}), new['summary'][group]
        common = [(index[(r['group'], str(r['name']))], r) for r in new['results']
                  if r['group'] == group and r['status'] == 'ok' and index.get((r['group'], str(r['name'])), {}).get('status') == 'ok']
        sums = {k: (sum(a.get(k, 0) for a, _ in common), sum(b.get(k, 0) for _, b in common)) for k in ('crossings', 'bends', 'length', 'hug', 'jogs', 'overhang', 'crowded', 'joins')}
        regressed = sum(1 for r in new['results'] if r['group'] == group and r['status'] != 'ok'
                        and index.get((r['group'], str(r['name'])), {}).get('status') == 'ok')
        print(f"{group:28} {o.get('ok','-'):>5}→{n['ok']:<5} {o.get('route_fail','-'):>5}→{n['route_fail']:<5} {o.get('label_fail','-'):>5}→{n['label_fail']:<5}"
              f"  n={len(common)} " + ', '.join(f'{a:g}→{b:g}' for a, b in sums.values()) + (f'  newly failing={regressed}' if regressed else ''))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--scripts', default=str(BASE/'cloud-architecture-drawio/scripts'))
    parser.add_argument('--out')
    parser.add_argument('--compare', nargs=2, metavar=('OLD', 'NEW'))
    args = parser.parse_args()
    if args.compare:
        compare(*args.compare)
        return
    results = run(args.scripts)
    report = {'scripts': args.scripts, 'summary': summarize(results), 'results': results}
    text = json.dumps(report, indent=1)
    if args.out:
        Path(args.out).write_text(text+'\n', encoding='utf-8')
    for group, s in report['summary'].items():
        print(group, s)


if __name__ == '__main__':
    main()
