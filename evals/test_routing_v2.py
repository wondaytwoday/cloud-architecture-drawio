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
            model = json.loads((BASE/'examples'/f'{name}.model.json').read_text(encoding='utf-8'))
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
                routes, ports, labels, mode = routing.route_and_label(reordered, c.header_rect)
                self.assertEqual(mode, report['routing'])
                self.assertEqual(routes, report['routes'])
                self.assertEqual(ports, routing.select_ports(model))
                self.assertEqual(labels, report['labels'])

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

    def test_metrics_report_a_route_that_meets_itself(self):
        hairpin = [(356, 312), (372, 312), (372, 250), (364, 250), (364, 312), (380, 312)]
        result = routing.metrics({'e': hairpin})
        self.assertEqual(result['overlapLength'], 8)
        self.assertEqual(result['overlaps'], [{'edges': ['e', 'e'], 'length': 8}])

    def test_near_coincident_explicit_offsets_are_rejected(self):
        model = {'nodes': [{'id': 'hub', 'x': 100, 'y': 300, 'w': 156, 'h': 124},
                           {'id': 'a', 'x': 500, 'y': 100, 'w': 156, 'h': 124},
                           {'id': 'b', 'x': 500, 'y': 500, 'w': 156, 'h': 124}],
                 'edges': [{'id': 'a-edge', 'source': 'hub', 'target': 'a', 'sourcePort': 'right', 'sourceOffset': .5},
                           {'id': 'b-edge', 'source': 'hub', 'target': 'b', 'sourcePort': 'right', 'sourceOffset': .51}]}
        with self.assertRaisesRegex(ValueError, r'hub right: explicit port offsets 0.5 and 0.51 are 1.2px apart'):
            routing.select_ports(model)
        model['edges'][1]['sourceOffset'] = .6
        routing.select_ports(model)

    def build_failure(self, nodes, edges, width=900, height=700):
        model = {'provider': 'aws', 'title': 'Failure path', 'width': width, 'height': height,
                 'containers': [], 'nodes': [dict(id=i, label=i, x=x, y=y, w=156, h=124) for i, x, y in nodes],
                 'edges': edges}
        self.assertEqual(c.validate(model)[0], [])
        with tempfile.TemporaryDirectory() as tmp:
            c.build(model, Path(tmp)/'failure.drawio')

    def test_build_failures_name_the_edge_and_a_remedy(self):
        cases = [
            # Facing cards closer than 2 x stub would need a route that doubles back.
            ([('a', 200, 250), ('b', 380, 250)], [{'id': 'close', 'source': 'a', 'target': 'b'}],
             r'close: facing card sides are 24px apart; connected sides need at least 2 x stub \(32px\)'),
            # A card 8px below the source blocks its 16px lead-in.
            ([('a', 200, 120), ('blocker', 200, 252), ('b', 600, 450)],
             [{'id': 'blocked', 'source': 'a', 'target': 'b', 'sourcePort': 'bottom'}],
             r"blocked: Connector source lead-in intersects card 'blocker': only 0px of its 16px is clear.*move them 16px further apart"),
            ([('a', 10, 300), ('b', 400, 300)], [{'id': 'side', 'source': 'b', 'target': 'a', 'targetPort': 'left'}],
             r'side: Connector target lead-in enters the 10px side margin'),
            ([('a', 300, 80), ('b', 300, 400)], [{'id': 'top', 'source': 'b', 'target': 'a', 'targetPort': 'top'}],
             r'top: Connector target lead-in enters the title band or legend footer'),
            ([('a', 200, 250), ('b', 396, 250)], [{'id': 'caption', 'source': 'a', 'target': 'b',
                                                   'label': 'HTTPS 443 · mutual TLS'}],
             r"caption: no clear label position for 'HTTPS 443 · mutual TLS'; a \d+x22px caption fits beside none of its segments \(longest 40px; a straight horizontal run needs about 164px\)"),
        ]
        for nodes, edges, message in cases:
            with self.subTest(edge=edges[0]['id']), self.assertRaisesRegex(ValueError, message):
                self.build_failure(nodes, edges)
        # 2 x stub is enough for a straight connector.
        self.build_failure([('a', 200, 250), ('b', 388, 250)], [{'id': 'close', 'source': 'a', 'target': 'b'}])

    def test_every_caption_failure_is_reported_at_once(self):
        model = {'provider': 'aws', 'title': 'Two tight captions', 'width': 900, 'height': 700, 'containers': [],
                 'nodes': [dict(id=i, label=i, x=x, y=y, w=156, h=124) for i, x, y in
                           (('a', 60, 120), ('b', 256, 120), ('c', 60, 400), ('d', 256, 400))],
                 'edges': [{'id': 'top', 'source': 'a', 'target': 'b', 'label': 'HTTPS 443 · mutual TLS'},
                           {'id': 'bottom', 'source': 'c', 'target': 'd', 'label': 'gRPC streaming · mTLS'}]}
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(routing.LabelError) as caught:
            c.build(model, Path(tmp)/'captions.drawio')
        self.assertEqual([line.split(':')[0] for line in str(caught.exception).splitlines()], ['top', 'bottom'])
        self.assertIn("blocked by card 'a', card 'b'", str(caught.exception))

    def two_cards(self, label, gap, stacked):
        a = {'id': 'a', 'label': 'a', 'x': 200, 'y': 150, 'w': 156, 'h': 124}
        b = dict(a, id='b', label='b', **({'y': 274+gap} if stacked else {'x': 356+gap}))
        return {'provider': 'aws', 'title': 'Two cards', 'width': 1000, 'height': 800, 'containers': [],
                'nodes': [a, b], 'edges': [{'id': 'e', 'source': 'a', 'target': 'b', 'label': label}]}

    def test_tight_captions_fit_exactly_where_the_rule_says(self):
        # Stacked cards need only 2 x stub; side-by-side cards need the caption box plus 8px.
        routing.route_and_label(self.two_cards('HTTPS', 32, True), c.header_rect)
        for label in ('HTTPS', 'SQL 5432', 'HTTPS 443 · mutual TLS'):
            box = sum(.58*11 for _ in label)+16
            with self.subTest(label=label):
                for gap in range(int(box+8)+1, int(box+8)+12):
                    routing.route_and_label(self.two_cards(label, gap, False), c.header_rect)
                with self.assertRaisesRegex(routing.LabelError, f'needs about {box+8:.0f}px'):
                    routing.route_and_label(self.two_cards(label, int(box+8)-2, False), c.header_rect)

    def test_caption_hint_only_asks_for_length_that_is_missing(self):
        sys.path.insert(0, str(BASE/'evals'))
        import bench_routing
        model = bench_routing.grid(1005, 6, 6, 110, True)
        routes, _ = routing.plan(model, c.header_rect, reserve=False, clear_borders=False, spread=False, stub_lanes=False)
        with self.assertRaises(routing.LabelError) as caught:
            routing.place_labels(model, routes, c.header_rect)
        for line in str(caught.exception).splitlines():
            longest = float(line.split('(longest ')[1].split('px')[0])
            if 'needs about' in line:
                self.assertLess(longest, float(line.split('needs about ')[1].split('px')[0]))

    def test_captions_prefer_their_own_segment_and_open_space(self):
        sys.path.insert(0, str(BASE/'evals'))
        import bench_routing
        for seed in (1025, 1098, 2021):
            model = bench_routing.grid(seed, 6, 6, 100, True) if seed < 2000 else bench_routing.grid(seed, 8, 8, 110, True)
            with self.subTest(seed=seed):
                routes, _, labels, _ = routing.route_and_label(model, c.header_rect)
                self.assertEqual(bench_routing.label_quality(routes, labels), (0, 0))

    def test_parallel_spreading_rescues_a_fan_out_through_the_fallback(self):
        sys.path.insert(0, str(BASE/'evals'))
        import bench_routing
        model = bench_routing.fanout(3000, 3, 60)
        routes, _ = routing.plan(model, c.header_rect, True, True, False, False)
        with self.assertRaises(routing.LabelError):
            routing.place_labels(model, routes, c.header_rect)
        with tempfile.TemporaryDirectory() as tmp:
            report = c.build(model, Path(tmp)/'fanout.drawio')
        self.assertTrue(report['routing']['spreadParallels'])

    def test_failure_report_comes_from_the_attempt_that_got_furthest(self):
        attempts = iter([routing.RouteError('route failed'), routing.LabelError(['a', 'b', 'c']), routing.LabelError(['only one'])]
                         + [routing.RouteError('late route failure')]*(len(routing.ROUTING_MODES)-3))
        def fake_plan(*args):
            raise next(attempts)
        original = routing.plan
        routing.plan = fake_plan
        try:
            with self.assertRaisesRegex(routing.LabelError, '^only one$'):
                routing.route_and_label({'edges': []}, c.header_rect)
        finally:
            routing.plan = original

    def test_work_limit_stops_the_fallback_and_says_why(self):
        sys.path.insert(0, str(BASE/'evals'))
        import bench_routing
        model = bench_routing.grid(1005, 6, 6, 110, True)
        limit = routing.ROUTING_WORK_LIMIT
        routing.ROUTING_WORK_LIMIT = 1
        try:
            with self.assertRaisesRegex(ValueError, r'stopped after 1 of \d+ routing modes: this diagram is large'):
                routing.route_and_label(model, c.header_rect)
        finally:
            routing.ROUTING_WORK_LIMIT = limit

    def test_lead_in_advice_is_the_exact_move_that_fixes_it(self):
        for y, move in ((244, 24), (248, 20), (252, 16), (260, 8)):
            with self.subTest(y=y), self.assertRaisesRegex(ValueError, f'move them {move}px further apart'):
                self.build_failure([('a', 200, 120), ('blocker', 200, y), ('b', 600, 450)],
                                   [{'id': 'e', 'source': 'a', 'target': 'b', 'sourcePort': 'bottom'}])
        self.build_failure([('a', 200, 120), ('blocker', 200, 268), ('b', 600, 450)],
                           [{'id': 'e', 'source': 'a', 'target': 'b', 'sourcePort': 'bottom'}])

    def test_routes_never_touch_their_own_lead_ins(self):
        # Three auto-port edges between diagonal neighbours 40px apart used to
        # loop back into their own arrowhead; the search now avoids that.
        model = {'provider': 'aws', 'title': 'Grid', 'width': 900, 'height': 558, 'containers': [],
                 'nodes': [{'id': 'app', 'label': 'App', 'x': 30, 'y': 264, 'w': 156, 'h': 124},
                           {'id': 'db', 'label': 'DB', 'x': 226, 'y': 100, 'w': 156, 'h': 124}],
                 'edges': [{'id': 'e0', 'source': 'app', 'target': 'db', 'label': 'TCP 5432'},
                           {'id': 'e1', 'source': 'app', 'target': 'db', 'kind': 'egress'},
                           {'id': 'e2', 'source': 'app', 'target': 'db', 'kind': 'replication'}]}
        with tempfile.TemporaryDirectory() as tmp:
            report = c.build(model, Path(tmp)/'grid.drawio')
        for eid, points in report['routes'].items():
            with self.subTest(edge=eid):
                self.assertEqual(routing.self_contact(points), (0, []))

    def test_connector_cannot_end_on_another_connector(self):
        model = {'provider': 'aws', 'title': 'T contact', 'width': 1300, 'height': 700, 'containers': [],
                 'nodes': [{'id': 'n2', 'label': 'Node 2', 'x': 822, 'y': 104, 'w': 200, 'h': 124},
                           {'id': 'n3', 'label': 'Node 3', 'x': 380, 'y': 132, 'w': 140, 'h': 140},
                           {'id': 'n4', 'label': 'Node 4', 'x': 430, 'y': 334, 'w': 156, 'h': 140}],
                 'edges': [{'id': 'e4', 'source': 'n3', 'target': 'n2', 'kind': 'egress', 'targetPort': 'top'},
                           {'id': 'e6', 'source': 'n4', 'target': 'n2', 'kind': 'egress'}]}
        # Plain sequential routing lays e4 along n2's border first, so e6's port
        # would sit on it; that is a build error, never a silent junction.
        with self.assertRaisesRegex(ValueError, r"e6: Connector target port at \(822, 166\) lies on connector 'e4'"):
            routing.plan(model, c.header_rect, reserve=False, clear_borders=False, spread=False)
        # Reserved lead-ins keep the port clear, so the model builds.
        with tempfile.TemporaryDirectory() as tmp:
            report = c.build(model, Path(tmp)/'tcontact.drawio')
        self.assertEqual(report['quality']['crossingCount'], 0)

    def test_crossing_fixture_has_one_proper_crossing_and_jump_styles(self):
        model = json.loads((BASE/'evals/fixtures/routing-crossings.model.json').read_text(encoding='utf-8'))
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
