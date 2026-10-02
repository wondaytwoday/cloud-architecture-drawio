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

    def changes(self, summary):
        return {k: v for k, v in summary.items() if v and k != 'layout'}

    def drawn(self, path):
        return model_pull.drawing(model_pull.page_model(path))[0]

    def assert_rebuilds_as_drawn(self, pulled, path):
        """The pulled model resolves to exactly the geometry in the edited file."""
        drawn, resolved = self.drawn(path), c.model_layout.normalize(pulled)
        wrong = [i['id'] for k in ('containers', 'nodes') for i in resolved[k] if model_pull.off(drawn[i['id']], i)]
        self.assertEqual(wrong, [])

    def test_an_untouched_build_pulls_back_to_the_same_model(self):
        names = sorted(p.stem for p in (SKILL/'assets/templates').glob('*.json'))
        korean = template('aws-three-tier')
        # The compiler breaks long words between characters; that is not an edit.
        korean['nodes'][3].update(label='주문처리데이터베이스기본인스턴스', detail='db-0123456789abcdef0123456789')
        gallery = json.loads((BASE/'evals/fixtures/icon-gallery.model.json').read_text(encoding='utf-8'))
        for name, model in [(n, template(n)) for n in names]+[('long words', korean), ('gallery', gallery)]:
            with self.subTest(name=name):
                pulled, summary = model_pull.pull(model, self.edit(model, lambda root: None))
                self.assertEqual(pulled, model)
                self.assertEqual(self.changes(summary), {})
                self.assertEqual(summary['layout'], 'kept')

    def test_moved_cards_rebuild_where_they_were_dropped(self):
        model = template('gcp-cloud-run')
        base = c.model_layout.normalize(model)
        for node in base['nodes']:
            for dx, dy in ((10, 0), (0, -10)):
                with self.subTest(node=node['id'], move=(dx, dy)):
                    def change(root):
                        geo = cell(root, node['id']).find('mxGeometry')
                        geo.set('x', str(float(geo.get('x'))+dx))
                        geo.set('y', str(float(geo.get('y'))+dy))
                    path = self.edit(model, change)
                    pulled, summary = model_pull.pull(model, path)
                    self.assertEqual(summary['moved'], [node['id']])
                    self.assert_rebuilds_as_drawn(pulled, path)

    def test_moves_resizes_relabels_and_hand_drawn_shapes_are_reported(self):
        model = template('gcp-cloud-run')
        mover = next(n for n in model['nodes'] if 'col' in n and n.get('parent'))
        caption = next(e for e in model['edges'] if e.get('label'))
        box = next(b for b in model['containers'] if b['id'] == mover['parent'])

        def change(root):
            geo = cell(root, mover['id']).find('mxGeometry')
            geo.set('x', str(float(geo.get('x'))+40))
            geo.set('width', '180')
            cell(root, '__name_'+mover['id']).set('value', 'Renamed service')
            cell(root, '__label_'+caption['id']).set('value', 'gRPC')
            cell(root, box['id']).set('value', 'Renamed boundary')
            note = ET.SubElement(root.find('.//root'), 'mxCell', id='hand-note', value='todo', vertex='1', parent='1')
            ET.SubElement(note, 'mxGeometry', x='10', y='10', width='40', height='20', **{'as': 'geometry'})

        path = self.edit(model, change)
        pulled, summary = model_pull.pull(model, path)
        moved = next(n for n in pulled['nodes'] if n['id'] == mover['id'])
        self.assertEqual((summary['moved'], summary['resized']), ([mover['id']], [mover['id']]))
        self.assertEqual((moved['w'], moved['label']), (180, 'Renamed service'))
        self.assertNotIn('col', moved)
        self.assertEqual(next(e for e in pulled['edges'] if e['id'] == caption['id'])['label'], 'gRPC')
        self.assertEqual(next(b for b in pulled['containers'] if b['id'] == box['id'])['label'], 'Renamed boundary')
        self.assertEqual(summary['unmodelled'], ['hand-note'])
        # Untouched shapes keep their shorthands.
        self.assertTrue(any('col' in n for n in pulled['nodes']))
        self.assertTrue(any(b.get('w') == 'fit' for b in pulled['containers']))
        self.assert_rebuilds_as_drawn(pulled, path)
        self.assertEqual(c.validate(pulled)[0], [])

    def test_moving_the_top_card_of_an_auto_canvas_falls_back_to_drawn_geometry(self):
        model = template('aws-egress')

        def change(root):
            geo = cell(root, 'internet').find('mxGeometry')
            geo.set('y', str(float(geo.get('y'))+10))

        path = self.edit(model, change)
        pulled, summary = model_pull.pull(model, path)
        self.assertEqual(summary['layout'], 'absolute')
        self.assertFalse(c.model_layout.uses_shorthand(pulled))
        self.assert_rebuilds_as_drawn(pulled, path)
        self.assertEqual(c.validate(pulled)[0], [])

    def test_connector_ends_captions_and_page_texts_are_pulled(self):
        model = template('aws-egress')

        def change(root):
            cell(root, 'nat-igw-a').set('value', 'HTTPS 443')
            cell(root, 'out-a').set('target', 'internet')
            cell(root, 'out-b').set('target', 'hand-drawn')
            root.find('.//root').remove(cell(root, '__label_s3'))
            cell(root, '__title').set('value', 'Egress (edited)')
            cell(root, '__notes').set('value', 'First note · Second note')
            cell(root, '__legend_text_egress').set('value', 'Outbound internet')

        pulled, summary = model_pull.pull(model, self.edit(model, change))
        edges = {e['id']: e for e in pulled['edges']}
        self.assertEqual(edges['nat-igw-a']['label'], 'HTTPS 443')
        self.assertEqual(edges['out-a']['target'], 'internet')
        self.assertNotIn('targetPort', edges['out-a'])
        self.assertEqual(edges['out-b']['target'], 'nat-b')
        self.assertNotIn('label', edges['s3'])
        self.assertEqual((pulled['title'], pulled['notes'], pulled['legend']), ('Egress (edited)', ['First note', 'Second note'], {'egress': 'Outbound internet'}))
        self.assertEqual(summary['reconnected'], ['out-a.target'])
        self.assertEqual(summary['ignored'], ["out-b.target: attached to unmodelled cell 'hand-drawn'"])
        self.assertEqual(sorted(summary['relabelled']), ['legend.egress', 'nat-igw-a.label', 'notes', 's3.label', 'title'])

    def test_an_edit_inside_wrapped_text_keeps_the_rest_of_the_text(self):
        model = template('aws-three-tier')
        model['nodes'][3]['label'] = '주문처리데이터베이스기본인스턴스'
        ident = model['nodes'][3]['id']

        def change(root):
            name = cell(root, '__name_'+ident)
            name.set('value', name.get('value').replace('주문', '결제'))

        pulled, summary = model_pull.pull(model, self.edit(model, change))
        self.assertEqual(pulled['nodes'][3]['label'], '결제처리데이터베이스기본인스턴스')
        self.assertEqual(summary['relabelled'], [f'{ident}.label'])

    def test_cells_wrapped_for_links_or_data_are_read(self):
        model = template('aws-three-tier')

        def wrap(root):
            parent = root.find('.//root')
            inner = cell(root, 'res-app-a')
            index = list(parent).index(inner)
            parent.remove(inner)
            outer = ET.Element('UserObject', label='', link='https://example.com/runbook', id='res-app-a')
            del inner.attrib['id']
            outer.append(inner)
            parent.insert(index, outer)

        pulled, summary = model_pull.pull(model, self.edit(model, wrap))
        self.assertEqual(pulled, model)
        self.assertEqual(self.changes(summary), {})

    def test_a_fitted_box_that_loses_its_only_card_keeps_its_drawn_size(self):
        model = template('aws-egress')

        def change(root):
            moved = cell(root, 'app-a')
            moved.set('parent', 'public-a')
            geo = moved.find('mxGeometry')
            geo.set('x', '230')
            geo.set('y', '56')
            box = cell(root, 'public-a').find('mxGeometry')
            box.set('width', str(float(box.get('width'))+220))

        path = self.edit(model, change)
        pulled, summary = model_pull.pull(model, path)
        self.assertEqual(summary['reparented'], ['app-a'])
        self.assertIn('private-a', summary['pinned'])
        self.assert_rebuilds_as_drawn(pulled, path)

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

        path = self.edit(model, compress)
        pulled, summary = model_pull.pull(model, path)
        self.assertEqual(summary['moved'], [card['id']])
        self.assert_rebuilds_as_drawn(pulled, path)

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

    def test_pages_and_files_that_cannot_be_pulled_fail_with_one_line(self):
        with tempfile.TemporaryDirectory() as d:
            both = Path(d)/'both.drawio'
            c.bundle([template('aws-three-tier'), template('aws-egress')], both)
            for page, message in ((0, 'page 0 requested'), (-1, 'page -1 requested'), (3, 'page 3 requested')):
                with self.assertRaisesRegex(ValueError, message):
                    model_pull.pull(template('aws-egress'), both, page)
            with self.assertRaisesRegex(ValueError, 'page 2 matches this model better than page 1; pass --page 2'):
                model_pull.pull(template('aws-egress'), both)
            with self.assertRaisesRegex(ValueError, 'holds no draw.io diagram'):
                model_pull.pull(template('aws-three-tier'), BASE/'examples/aws-three-tier.png')

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
            # An embedded preview edited in draw.io can be pulled like the .drawio.
            for preview in ('gcp.drawio.png', 'gcp.drawio.svg'):
                pulled, summary = model_pull.pull(template('gcp-regional'), Path(d)/preview)
                self.assertEqual(pulled, template('gcp-regional'))

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
