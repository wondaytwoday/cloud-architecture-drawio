"""Layout shorthands: default card size, grid cells, fitted containers, auto canvas."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

BASE = Path(__file__).resolve().parents[1]
SCRIPTS = BASE/'cloud-architecture-drawio/scripts'
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('layout_compiler', SCRIPTS/'cloud_drawio.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)
import model_layout


def two_az():
    fit = {'x': 'fit', 'y': 'fit', 'w': 'fit', 'h': 'fit'}
    return {'provider': 'aws', 'title': 'Grid demo', 'width': 'auto', 'height': 'auto', 'grid': {'left': 80, 'top': 200},
            'containers': [dict(fit, id='cloud', kind='cloud', label='AWS Cloud'),
                           dict(fit, id='vpc', kind='vpc', label='VPC', parent='cloud'),
                           dict(fit, id='az-a', kind='az', label='AZ a', parent='vpc'),
                           dict(fit, id='az-b', kind='az', label='AZ b', parent='vpc', h='match:az-a'),
                           dict(fit, id='sn-a', kind='subnet', label='Private a', parent='az-a'),
                           dict(fit, id='sn-b', kind='subnet', label='Private b', parent='az-b'),
                           {'id': 'web-tier', 'kind': 'group', 'overlay': True, 'label': 'Web tier', 'parent': 'vpc',
                            'members': ['web-a', 'web-b'], **fit}],
            'nodes': [{'id': 'web-a', 'icon': 'aws.ec2', 'label': 'Web a', 'parent': 'sn-a', 'col': 0, 'row': 1},
                      {'id': 'web-b', 'icon': 'aws.ec2', 'label': 'Web b', 'parent': 'sn-b', 'col': 2, 'row': 1},
                      {'id': 'alb', 'icon': 'aws.alb', 'label': 'ALB', 'parent': 'vpc', 'col': 1, 'row': 0}],
            'edges': [{'id': 'e1', 'source': 'alb', 'target': 'web-a', 'label': 'HTTPS'},
                      {'id': 'e2', 'source': 'alb', 'target': 'web-b', 'label': 'HTTPS'}]}


class LayoutTests(unittest.TestCase):
    def test_absolute_models_pass_through_untouched(self):
        m = json.loads((BASE/'examples/aws-three-az.model.json').read_text(encoding='utf-8'))
        self.assertIs(model_layout.normalize(m), m)

    def test_grid_fit_match_and_auto_canvas_resolve_to_a_valid_model(self):
        source = two_az()
        original = copy.deepcopy(source)
        m = model_layout.normalize(source)
        self.assertEqual(source, original)
        boxes = {b['id']: b for b in m['containers']}
        nodes = {n['id']: n for n in m['nodes']}
        self.assertEqual((nodes['alb']['w'], nodes['alb']['h']), (156, 124))
        self.assertEqual(nodes['web-b']['x']-nodes['web-a']['x'], 2*model_layout.GRID['column'])
        # Each fitted box wraps its children with the documented padding.
        self.assertEqual(nodes['web-a']['y']-boxes['sn-a']['y'], model_layout.PAD['top'])
        self.assertEqual(boxes['sn-a']['x']+boxes['sn-a']['w']-nodes['web-a']['x']-156, model_layout.PAD['right'])
        self.assertEqual(boxes['az-b']['h'], boxes['az-a']['h'])
        # The overlay wraps its members, not every shape in the VPC.
        self.assertEqual(boxes['web-tier']['x'], nodes['web-a']['x']-model_layout.PAD['left'])
        self.assertGreaterEqual(min(b['x'] for b in m['containers']), model_layout.PAGE_SIDE)
        self.assertGreaterEqual(min(b['y'] for b in m['containers']), model_layout.TITLE_BAND)
        self.assertEqual(m['width'], max(s['x']+s['w'] for s in m['containers']+m['nodes'])+model_layout.PAGE_SIDE)
        self.assertEqual(c.validate(source), ([], []))
        with tempfile.TemporaryDirectory() as d:
            report = c.build(source, Path(d)/'grid.drawio')
        self.assertEqual(report['warnings'], [])

    def test_shorthand_mistakes_are_reported_as_layout_errors(self):
        cases = [
            (lambda m: m['containers'][3].update(h='match:nowhere'), "az-b.h: 'match:nowhere' names no container"),
            (lambda m: m['nodes'][1].update(parent='sn-a'), "sn-b: 'fit' needs at least one child"),
            (lambda m: m['containers'][2].update(h='match:az-b') or m['containers'][3].update(h='match:az-a'), 'refers back to itself'),
            (lambda m: m['nodes'][0].update(x=100), 'give either x or col, not both'),
            (lambda m: m['containers'][6].update(members=['ghost']), "web-tier: a fitted overlay group needs members naming its nodes; unknown ['ghost']"),
            (lambda m: m['containers'][0].update(w='wide'), "cloud.w: use a finite number, 'fit' or 'match:ID'"),
        ]
        for change, message in cases:
            with self.subTest(message=message):
                m = two_az()
                change(m)
                errors, _ = c.validate(m)
                self.assertTrue(any(message in e for e in errors), errors)
                self.assertTrue(all(e.startswith('layout: ') for e in errors))

    def test_a_fitted_overlay_centres_its_title_clear_of_its_first_member(self):
        m = model_layout.normalize(two_az())
        boxes = {b['id']: b for b in m['containers']}
        self.assertEqual(boxes['web-tier']['labelAlign'], 'center')
        self.assertNotEqual(c.header_rect(boxes['web-tier'])[0], c.header_rect(boxes['sn-a'])[0])
        # Titles that still meet are an error, not a silent overprint.
        source = two_az()
        source['containers'][6]['labelAlign'] = 'left'
        self.assertTrue(any('container titles overlap' in e for e in c.validate(source)[0]))

    def test_malformed_shorthands_are_one_line_layout_errors(self):
        cases = [
            (lambda m: m['nodes'][0].pop('row'), 'web-a.y: must be a finite number (or give row)'),
            (lambda m: m['nodes'][0].update(col=float('inf')), 'web-a: col must be a finite number'),
            (lambda m: m['containers'][0].pop('x'), 'cloud: fit width needs x'),
            (lambda m: m['containers'][2].pop('h'), "az-a.h: use a finite number, 'fit' or 'match:ID'"),
            (lambda m: m.update(grid={'colum': 400}), 'grid.colum: unknown key'),
            (lambda m: m.update(grid=5), 'grid: must be an object'),
        ]
        for change, message in cases:
            with self.subTest(message=message):
                m = two_az()
                change(m)
                errors, _ = c.validate(m)
                self.assertTrue(any(message in e for e in errors), errors)

    def test_a_valid_fixed_canvas_is_not_moved(self):
        m = {'provider': 'aws', 'title': 'Fixed', 'width': 400, 'height': 400, 'containers': [],
             'nodes': [{'id': 'a', 'icon': 'aws.ec2', 'label': 'A', 'x': 12, 'y': 100, 'w': 156},
                       {'id': 'b', 'icon': 'aws.ec2', 'label': 'B', 'x': 232, 'y': 100, 'w': 156, 'h': 124}],
             'edges': []}
        resolved, shift = model_layout.resolve(m)
        self.assertEqual(shift, (0, 0))
        self.assertEqual(resolved['nodes'][0]['x'], 12)
        self.assertEqual(c.validate(m), ([], []))

    def test_fit_and_auto_make_room_for_one_line_titles(self):
        fit = {'x': 'fit', 'y': 'fit', 'w': 'fit', 'h': 'fit'}
        m = {'provider': 'azure', 'title': 'Serverless order processing pipeline with retries', 'width': 'auto', 'height': 'auto',
             'containers': [dict(fit, id='vnet', kind='vnet', label='VNet'),
                            dict(fit, id='sn', kind='subnet', label='Private subnet 10.0.1.0/24 · application tier', parent='vnet')],
             'nodes': [{'id': 'a', 'icon': 'azure.vm', 'label': 'A', 'col': 0, 'row': 0, 'parent': 'sn'}],
             'edges': []}
        self.assertEqual(c.validate(m), ([], []))
        resolved = model_layout.normalize(m)
        sn = next(b for b in resolved['containers'] if b['id'] == 'sn')
        self.assertGreater(sn['w'], 156+model_layout.PAD['left']+model_layout.PAD['right'])

    def test_an_auto_canvas_leaves_room_for_a_top_port(self):
        m = {'provider': 'aws', 'title': 'Loop', 'width': 'auto', 'height': 'auto', 'containers': [],
             'nodes': [{'id': 'a', 'icon': 'aws.lambda', 'label': 'A', 'col': 0, 'row': 0},
                       {'id': 'b', 'icon': 'aws.sqs', 'label': 'B', 'col': 2, 'row': 0},
                       {'id': 'c', 'icon': 'aws.s3', 'label': 'C', 'col': 1, 'row': 0}],
             'edges': [{'id': 'e', 'source': 'a', 'target': 'b', 'sourcePort': 'top', 'targetPort': 'top', 'label': 'retry'},
                       {'id': 'f', 'source': 'a', 'target': 'c'}]}
        with tempfile.TemporaryDirectory() as d:
            report = c.build(m, Path(d)/'loop.drawio')
        self.assertEqual(report['warnings'], [])
        self.assertEqual(min(y for _, y in report['routes']['e']), model_layout.MARGIN_TOP)

    def test_resolve_reports_the_page_shift(self):
        m, (dx, dy) = model_layout.resolve(two_az())
        web = next(n for n in m['nodes'] if n['id'] == 'web-a')
        self.assertEqual((web['x']-dx, web['y']-dy), (two_az()['grid']['left'], two_az()['grid']['top']+model_layout.GRID['row']))
        self.assertEqual(model_layout.resolve(json.loads((BASE/'examples/aws-three-az.model.json').read_text(encoding='utf-8')))[1], (0, 0))

    def test_normalize_command_prints_the_absolute_model(self):
        import subprocess
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'grid.json'
            path.write_text(json.dumps(two_az()), encoding='utf-8')
            result = subprocess.run([sys.executable, str(SCRIPTS/'cloud_drawio.py'), 'normalize', str(path)],
                                    capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)
        printed = json.loads(result.stdout)
        self.assertEqual(printed, model_layout.normalize(two_az()))
        self.assertNotIn('grid', printed)


if __name__ == '__main__':
    unittest.main(verbosity=2)
