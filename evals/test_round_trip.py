"""Editing loop: pull manual draw.io edits back, bundle pages, embed the source in previews."""
import base64
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import urllib.parse
import xml.etree.ElementTree as ET
import zlib

BASE = Path(__file__).resolve().parents[1]
SKILL = BASE/'cloud-architecture-drawio'
sys.path.insert(0, str(SKILL/'scripts'))
sys.path.insert(0, str(BASE/'evals'))
import cloud_drawio as c
import model_pull
from test_cli_and_assets import RENDER, RENDERER, cli


def template(name):
    return json.loads((SKILL/f'assets/templates/{name}.json').read_text(encoding='utf-8'))


def cell(root, ident):
    return next(e for e in root.iter('mxCell') if e.get('id') == ident)


class PullTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def edit(self, model, change):
        path = self.dir/'diagram.drawio'
        c.build(model, path, force=True)
        tree = ET.parse(path)
        change(tree.getroot())
        tree.write(path, encoding='utf-8')
        return path

    def test_an_untouched_build_pulls_back_to_the_same_model(self):
        for name in ('aws-three-tier', 'gcp-cloud-run'):
            with self.subTest(name=name):
                model = template(name)
                path = self.edit(model, lambda root: None)
                pulled, summary = model_pull.pull(model, path)
                self.assertEqual(pulled, model)
                self.assertEqual(sum(map(len, summary.values())), 0, summary)

    def test_moves_reparents_relabels_and_hand_drawn_shapes_are_reported(self):
        model = template('gcp-cloud-run')
        nodes = {n['id']: n for n in c.model_layout.normalize(model)['nodes']}
        mover = next(n for n in model['nodes'] if 'col' in n)
        caption = next(e for e in model['edges'] if e.get('label'))
        target = nodes[mover['id']]

        def change(root):
            geo = cell(root, mover['id']).find('mxGeometry')
            geo.set('x', str(float(geo.get('x'))+40))
            geo.set('width', '180')
            cell(root, '__name_'+mover['id']).set('value', 'Renamed service')
            cell(root, '__label_'+caption['id']).set('value', 'gRPC')
            box = next(b for b in model['containers'] if b.get('label'))
            cell(root, box['id']).set('value', 'Renamed boundary')
            parent = root.find('.//root')
            note = ET.SubElement(parent, 'mxCell', id='hand-note', value='todo', vertex='1', parent='1')
            ET.SubElement(note, 'mxGeometry', x='10', y='10', width='40', height='20', **{'as': 'geometry'})

        pulled, summary = model_pull.pull(model, self.edit(model, change))
        moved = next(n for n in pulled['nodes'] if n['id'] == mover['id'])
        self.assertEqual(summary['moved'], [mover['id']])
        self.assertEqual(summary['resized'], [mover['id']])
        self.assertEqual((moved['x'], moved['w'], moved['label']), (target['x']+40, 180, 'Renamed service'))
        self.assertNotIn('col', moved)
        self.assertIn(f"{caption['id']}.label", summary['relabelled'])
        self.assertEqual(next(e for e in pulled['edges'] if e['id'] == caption['id'])['label'], 'gRPC')
        self.assertEqual(summary['unmodelled'], ['hand-note'])
        box = next(b for b in pulled['containers'] if b.get('label'))
        self.assertIn(box['id'], summary['relabelled'])
        self.assertEqual(box['label'], 'Renamed boundary')
        # Shapes that were left alone keep their grid cells and fitted sizes.
        untouched = [n for n in pulled['nodes'] if n['id'] != mover['id'] and 'col' in n]
        self.assertTrue(untouched)
        self.assertTrue(any(b.get('w') == 'fit' for b in pulled['containers']))
        self.assertEqual(c.validate(pulled)[0], [])

    def test_a_compressed_page_saved_by_draw_io_is_read(self):
        model = template('azure-hub-spoke')
        card = c.model_layout.normalize(model)['nodes'][0]

        def compress(root):
            geo = cell(root, card['id']).find('mxGeometry')
            geo.set('y', str(float(geo.get('y'))+12))
            diagram = root.find('diagram')
            graph = diagram.find('mxGraphModel')
            text = urllib.parse.quote(ET.tostring(graph, encoding='unicode'), safe='')
            packer = zlib.compressobj(9, zlib.DEFLATED, -15)
            diagram.remove(graph)
            diagram.text = base64.b64encode(packer.compress(text.encode('utf-8'))+packer.flush()).decode('ascii')

        pulled, summary = model_pull.pull(model, self.edit(model, compress))
        self.assertEqual(summary['moved'], [card['id']])
        self.assertEqual(next(n for n in pulled['nodes'] if n['id'] == card['id'])['y'], card['y']+12)

    def test_dropping_a_card_into_another_subnet_reparents_it(self):
        model = template('aws-three-tier')
        resolved = c.model_layout.normalize(model)
        subnets = [b for b in resolved['containers'] if b['kind'] == 'subnet']
        card = next(n for n in resolved['nodes'] if n.get('parent') == subnets[0]['id'])
        other = subnets[1]

        def change(root):
            moved = cell(root, card['id'])
            moved.set('parent', other['id'])
            geo = moved.find('mxGeometry')
            geo.set('x', '24')
            geo.set('y', '56')

        pulled, summary = model_pull.pull(model, self.edit(model, change))
        self.assertEqual(summary['reparented'], [card['id']])
        self.assertEqual(next(n for n in pulled['nodes'] if n['id'] == card['id'])['parent'], other['id'])

    def test_cli_writes_the_model_and_fails_when_the_edit_breaks_it(self):
        model = template('aws-three-tier')
        source = self.dir/'model.json'
        source.write_text(json.dumps(model), encoding='utf-8')
        card = c.model_layout.normalize(model)['nodes'][0]

        def change(root):
            geo = cell(root, card['id']).find('mxGeometry')
            geo.set('x', '-500')

        path = self.edit(model, change)
        result = cli('pull', path, source, '--output', self.dir/'pulled.json')
        self.assertEqual(result.returncode, 1, result.stderr)
        summary = json.loads(result.stderr)
        self.assertEqual(summary['moved'], [card['id']])
        self.assertTrue(summary['errors'])
        self.assertTrue((self.dir/'pulled.json').exists())
        result = cli('pull', path, source, '--page', 2)
        self.assertEqual(result.returncode, 1)
        self.assertIn('page 2 requested', result.stderr)


class BundleTests(unittest.TestCase):
    def test_pages_share_one_file_and_each_keeps_its_own_report(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)/'both.drawio'
            report = c.bundle([template('aws-three-tier'), template('aws-egress')], out)
            diagrams = ET.parse(out).getroot().findall('diagram')
            self.assertEqual([p.get('id') for p in diagrams], ['page-1', 'page-2'])
            self.assertEqual(len(report['pages']), 2)
            saved = json.loads(out.with_suffix('.report.json').read_text(encoding='utf-8'))
            self.assertEqual(saved['pages'], json.loads(json.dumps(report['pages'])))
            self.assertEqual(len(report['pages'][1]['routes']), len(template('aws-egress')['edges']))
            pulled, summary = model_pull.pull(template('aws-egress'), out, page=2)
            self.assertEqual(pulled, template('aws-egress'))
            bad = template('aws-egress')
            bad['nodes'][0]['icon'] = 'aws.nope'
            with self.assertRaisesRegex(ValueError, 'page 2: '):
                c.bundle([template('aws-three-tier'), bad], Path(d)/'bad.drawio')


@unittest.skipUnless(RENDERER, 'needs node, playwright (NODE_PATH) and DRAWIO_VIEWER or .cache/viewer-static.min.js')
class EmbedTests(unittest.TestCase):
    def render(self, drawio, output, *extra):
        node, viewer = RENDERER
        result = subprocess.run([node, str(RENDER), str(drawio), str(output), viewer, *extra], capture_output=True, text=True)
        report = output.with_name(output.stem+'.render.json')
        return result, json.loads(report.read_text(encoding='utf-8'))

    def test_embedded_previews_carry_the_exact_diagram(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d)/'gcp.drawio'
            c.build(template('gcp-regional'), src)
            result, rendered = self.render(src, Path(d)/'gcp.drawio.png', '--embed')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(rendered['embedded'], {'png': True, 'svg': True})
            xml = src.read_text(encoding='utf-8')
            png = (Path(d)/'gcp.drawio.png').read_bytes()
            self.assertIn(b'tEXtmxfile\0', png)
            self.assertEqual(ET.parse(Path(d)/'gcp.drawio.svg').getroot().get('content'), xml)
            plain, rendered = self.render(src, Path(d)/'plain.png')
            self.assertNotIn('embedded', rendered)
            self.assertNotIn(b'mxfile', (Path(d)/'plain.png').read_bytes())

    def test_second_page_of_a_bundle_renders_against_its_own_report(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)/'both.drawio'
            c.bundle([template('aws-three-tier'), template('aws-egress')], out)
            result, rendered = self.render(out, Path(d)/'page2.png', '--page', '2', '--report', str(out.with_suffix('.report.json')))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(rendered['geometry']['checkedRoutes'], len(template('aws-egress')['edges']))
            self.assertEqual(rendered['geometry']['mismatches'], [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
