"""Independent geometric regressions for connector routing and native labels."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET


BASE = Path(__file__).resolve().parents[1]
SCRIPTS = BASE/'cloud-architecture-drawio/scripts'
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('routing_compiler', SCRIPTS/'cloud_drawio.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)
import cloud_routes as routing


def segments(points):
    return list(zip(points, points[1:]))


def padded(rect, gap):
    x, y, w, h = rect
    return x-gap, y-gap, w+gap*2, h+gap*2


def intersects_interior(segment, rect):
    """Independent oracle: positive segment length within an open rectangle."""
    (ax, ay), (bx, by) = segment
    x, y, w, h = rect
    if ax == bx:
        return x < ax < x+w and max(min(ay, by), y) < min(max(ay, by), y+h)
    if ay == by:
        return y < ay < y+h and max(min(ax, bx), x) < min(max(ax, bx), x+w)
    raise AssertionError(f'Diagonal connector segment: {segment}')


def rectangles_overlap(a, b):
    return max(a[0], b[0]) < min(a[0]+a[2], b[0]+b[2]) and max(a[1], b[1]) < min(a[1]+a[3], b[1]+b[3])


def shared_segment_length(first, second):
    """Independent oracle for positive collinear overlap, not crossings."""
    a, b = first
    d, e = second
    for fixed, variable in ((0, 1), (1, 0)):
        if a[fixed] == b[fixed] == d[fixed] == e[fixed]:
            return max(0, min(max(a[variable], b[variable]), max(d[variable], e[variable]))
                       - max(min(a[variable], b[variable]), min(d[variable], e[variable])))
    return 0


def point_along(points, fraction):
    total = sum(abs(a[0]-b[0])+abs(a[1]-b[1]) for a, b in segments(points))
    remaining = total*fraction
    for a, b in segments(points):
        distance = abs(a[0]-b[0])+abs(a[1]-b[1])
        if remaining <= distance:
            ratio = remaining/distance if distance else 0
            return a[0]+(b[0]-a[0])*ratio, a[1]+(b[1]-a[1])*ratio
        remaining -= distance
    return points[-1]


class RoutingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = {}
        cls.tmp = tempfile.TemporaryDirectory()
        for name in ('aws-three-tier', 'aws-three-tier-ko', 'aws-three-az', 'azure-regional', 'gcp-regional'):
            model = json.loads((BASE/'examples'/f'{name}.model.json').read_text())
            target = Path(cls.tmp.name)/f'{name}.drawio'
            report = c.build(model, target)
            cls.cases[name] = model, report, ET.parse(target)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_five_models_have_no_positive_collinear_overlap(self):
        for name, (_, report, _) in self.cases.items():
            routes = list(report['routes'].items())
            for index, (aid, first) in enumerate(routes):
                for bid, second in routes[index+1:]:
                    with self.subTest(model=name, edge_a=aid, edge_b=bid):
                        total = sum(shared_segment_length(a, b) for a in segments(first) for b in segments(second))
                        self.assertEqual(total, 0)

    def test_routes_keep_card_clearance_and_padded_headers_clear(self):
        for name, (model, report, _) in self.cases.items():
            by_edge = {edge['id']: edge for edge in model['edges']}
            gap = model.get('routing', {}).get('clearance', 8)
            for eid, points in report['routes'].items():
                edge = by_edge[eid]
                obstacles = [padded(tuple(n[k] for k in ('x', 'y', 'w', 'h')),
                                    0 if n['id'] in (edge['source'], edge['target']) else gap)
                             for n in model['nodes']]
                obstacles += [padded(c.header_rect(box), 4) for box in model['containers']]
                for segment in segments(points):
                    with self.subTest(model=name, edge=eid, segment=segment):
                        self.assertNotEqual(segment[0], segment[1], 'zero-length segment')
                        self.assertFalse(any(intersects_interior(segment, rect) for rect in obstacles))

    def test_edge_input_order_does_not_change_routes_ports_or_labels(self):
        for name, (model, report, _) in self.cases.items():
            reordered = copy.deepcopy(model)
            reordered['edges'].reverse()
            with self.subTest(model=name):
                routes, ports = routing.plan(reordered, c.header_rect)
                self.assertEqual(routes, report['routes'])
                self.assertEqual(ports, routing.select_ports(model))
                self.assertEqual(routing.place_labels(reordered, routes, c.header_rect), report['labels'])

    def test_high_degree_resources_have_distinct_attachment_coordinates(self):
        for name, (model, report, _) in self.cases.items():
            attached = {}
            for edge in model['edges']:
                points = report['routes'][edge['id']]
                attached.setdefault(edge['source'], []).append(tuple(points[0]))
                attached.setdefault(edge['target'], []).append(tuple(points[-1]))
            for resource, points in attached.items():
                with self.subTest(model=name, resource=resource):
                    self.assertEqual(len(points), len(set(points)), 'different edges share an attachment')

    def test_automatic_attachments_respect_reserved_explicit_offset(self):
        nodes = [{'id': 'hub', 'x': 400, 'y': 430, 'w': 156, 'h': 124}]
        edges = []
        for index, y in enumerate((180, 430, 680)):
            nodes.append({'id': f'target-{index}', 'x': 800, 'y': y, 'w': 156, 'h': 124})
            edges.append({'id': f'edge-{index}', 'source': 'hub', 'target': f'target-{index}',
                          'sourcePort': 'right', 'targetPort': 'left'})
        edges[0]['sourceOffset'] = .5
        ports = routing.select_ports({'nodes': nodes, 'edges': edges})
        anchors = [tuple(ports[(edge['id'], 'source')]) for edge in edges]
        self.assertEqual(ports[('edge-0', 'source')], ['right', .5])
        self.assertEqual(len(set(anchors)), 3, 'automatic offsets must not collide with explicit sourceOffset=.5')
        self.assertEqual(ports, routing.select_ports({'nodes': nodes, 'edges': list(reversed(edges))}))

    def test_duplicate_explicit_offsets_report_actionable_error(self):
        model = {'nodes': [{'id': 'hub', 'x': 100, 'y': 300, 'w': 156, 'h': 124},
                           {'id': 'a', 'x': 500, 'y': 100, 'w': 156, 'h': 124},
                           {'id': 'b', 'x': 500, 'y': 500, 'w': 156, 'h': 124}],
                 'edges': [{'id': 'a-edge', 'source': 'hub', 'target': 'a', 'sourcePort': 'right', 'sourceOffset': .5},
                           {'id': 'b-edge', 'source': 'hub', 'target': 'b', 'sourcePort': 'right', 'sourceOffset': .5}]}
        with self.assertRaisesRegex(ValueError, 'hub right:.*choose distinct offsets'):
            routing.select_ports(model)

    def test_labels_avoid_all_routes_resources_headers_and_other_labels(self):
        for name, (model, report, _) in self.cases.items():
            requested = {e['id'] for e in model['edges'] if e.get('label')}
            self.assertEqual(set(report['labels']), requested, f'{name}: dropped label')
            obstacles = [padded(tuple(n[k] for k in ('x', 'y', 'w', 'h')), 4) for n in model['nodes']]
            obstacles += [padded(c.header_rect(box), 4) for box in model['containers']]
            placed = []
            for eid, label in report['labels'].items():
                rect = label['rect']
                with self.subTest(model=name, label=eid):
                    self.assertFalse(any(rectangles_overlap(rect, obstacle) for obstacle in obstacles+placed))
                    for points in report['routes'].values():
                        self.assertFalse(any(intersects_interior(segment, padded(rect, 3)) for segment in segments(points)))
                placed.append(padded(rect, 4))

    def test_labels_are_edge_children_with_relative_xml_geometry(self):
        for name, (_, report, document) in self.cases.items():
            for eid, label in report['labels'].items():
                with self.subTest(model=name, label=eid):
                    cell = document.find(f'.//mxCell[@id="__label_{eid}"]')
                    self.assertIsNotNone(cell)
                    self.assertEqual(cell.get('parent'), eid)
                    self.assertEqual(cell.get('connectable'), '0')
                    geometry = cell.find('mxGeometry')
                    self.assertEqual(geometry.get('relative'), '1')
                    self.assertAlmostEqual(float(geometry.get('x')), label['relativeX'])
                    self.assertGreaterEqual(float(geometry.get('x')), -1)
                    self.assertLessEqual(float(geometry.get('x')), 1)
                    offset = geometry.find('mxPoint[@as="offset"]')
                    self.assertIsNotNone(offset)
                    anchor = point_along(report['routes'][eid], (float(geometry.get('x'))+1)/2)
                    self.assertAlmostEqual(anchor[0]+float(offset.get('x')), label['rect'][0])
                    self.assertAlmostEqual(anchor[1]+float(offset.get('y')), label['rect'][1])

    def test_metrics_distinguish_crossings_terminals_and_overlaps(self):
        cases = [
            ({'h': [(0, 10), (20, 10)], 'v': [(10, 0), (10, 20)]}, 1, 0),
            ({'h': [(0, 0), (20, 0)], 'v': [(20, 0), (20, 20)]}, 0, 0),
            ({'a': [(0, 0), (100, 0)], 'b': [(40, 0), (140, 0)]}, 0, 60),
            ({'a': [(0, 0), (100, 0)], 'b': [(0, 10), (100, 10)]}, 0, 0),
            ({'h': [(0, 10), (20, 10)], 'v': [(10, 0), (10, 10)]}, 1, 0),
        ]
        for routes, crossings, shared in cases:
            with self.subTest(routes=routes):
                result = routing.metrics(routes)
                self.assertEqual(result['crossingCount'], crossings)
                self.assertEqual(result['overlapLength'], shared)

    def test_crossing_fixture_has_one_proper_crossing_and_jump_styles(self):
        model = json.loads((BASE/'evals/fixtures/routing-crossings.model.json').read_text())
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'crossing.drawio'
            report = c.build(model, path)
            self.assertEqual(report['quality']['crossingCount'], 1)
            self.assertEqual(report['quality']['overlapLength'], 0)
            crossing = report['quality']['crossings'][0]['point']
            for route in report['routes'].values():
                self.assertNotIn(crossing, (route[0], route[-1]))
            document = ET.parse(path)
            for edge in model['edges']:
                style = document.find(f'.//mxCell[@id="{edge["id"]}"]').get('style')
                self.assertIn('jumpStyle=arc;', style)
                self.assertIn('jumpSize=8;', style)


if __name__ == '__main__':
    unittest.main(verbosity=2)
