"""CLI behaviour, locale independence, asset integrity, release zip and real rendering."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

BASE = Path(__file__).resolve().parents[1]
SKILL = BASE/'cloud-architecture-drawio'
CLI = [sys.executable, str(SKILL/'scripts/cloud_drawio.py')]
RENDER = SKILL/'scripts/render.cjs'
sys.path.insert(0, str(BASE/'tools'))
import build_dist


def cli(*args, env=None):
    return subprocess.run(CLI+[str(a) for a in args], capture_output=True, text=True, encoding='utf-8', env=env)


class CliTests(unittest.TestCase):
    def test_bad_paths_and_json_fail_with_one_line_and_no_traceback(self):
        with tempfile.TemporaryDirectory() as d:
            bad = Path(d)/'bad.json'
            bad.write_text('{not json', encoding='utf-8')
            template = SKILL/'assets/templates/aws-three-tier.json'
            for args in (('validate', Path(d)/'missing.json'), ('validate', bad), ('build', template, '/dev/null/out.drawio')):
                with self.subTest(args=args):
                    result = cli(*args)
                    self.assertEqual(result.returncode, 1)
                    self.assertNotIn('Traceback', result.stderr)
                    self.assertEqual(len(result.stderr.strip().splitlines()), 1, result.stderr)

    def test_validate_exit_codes_and_byte_order_mark(self):
        model = json.loads((SKILL/'assets/templates/azure-regional.json').read_text(encoding='utf-8'))
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'bom.json'
            path.write_bytes(b'\xef\xbb\xbf'+json.dumps(model, ensure_ascii=False).encode('utf-8'))
            result = cli('validate', path)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), {'errors': [], 'warnings': []})
            model['nodes'][0]['icon'] = 'azure.nope'
            path.write_text(json.dumps(model), encoding='utf-8')
            result = cli('validate', path)
            self.assertEqual(result.returncode, 1)
            self.assertTrue(json.loads(result.stdout)['errors'])

    def test_force_flag_replaces_an_edited_build(self):
        template = SKILL/'assets/templates/gcp-regional.json'
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)/'gcp.drawio'
            self.assertEqual(cli('build', template, out).returncode, 0)
            out.write_bytes(out.read_bytes().replace(b'Cloud SQL', b'Cloud SQL (edited)'))
            result = cli('build', template, out)
            self.assertEqual(result.returncode, 1)
            self.assertIn('--force', result.stderr)
            self.assertEqual(cli('build', template, out, '--force').returncode, 0)

    def test_unreadable_report_keeps_the_overwrite_guard(self):
        template = SKILL/'assets/templates/gcp-regional.json'
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)/'gcp.drawio'
            for broken in (b'{"version": 3, "drawio_sha', b'', b'[]', b'null', b'<<<<<<< HEAD'):
                with self.subTest(report=broken):
                    self.assertEqual(cli('build', template, out, '--force').returncode, 0)
                    out.with_suffix('.report.json').write_bytes(broken)
                    result = cli('build', template, out)
                    self.assertEqual(result.returncode, 1)
                    self.assertIn('is unreadable', result.stderr)
                    self.assertNotIn('Traceback', result.stderr)

    def test_writes_go_through_symlinks_keep_modes_and_leave_no_temp_files(self):
        template = SKILL/'assets/templates/gcp-regional.json'
        with tempfile.TemporaryDirectory() as d:
            shared = Path(d)/'shared'
            shared.mkdir()
            self.assertEqual(cli('build', template, shared/'out.drawio').returncode, 0)
            (shared/'out.drawio').chmod(0o664)
            (Path(d)/'link.drawio').symlink_to('shared/out.drawio')
            (Path(d)/'link.report.json').symlink_to('shared/out.report.json')
            self.assertEqual(cli('build', template, Path(d)/'link.drawio').returncode, 0)
            self.assertTrue((Path(d)/'link.drawio').is_symlink())
            self.assertEqual((shared/'out.drawio').stat().st_mode & 0o777, 0o664)
            (Path(d)/'dir.drawio').mkdir()
            result = cli('build', template, Path(d)/'dir.drawio', '--force')
            self.assertEqual(result.returncode, 1)
            self.assertIn('dir.drawio:', result.stderr)
            self.assertEqual(sorted(p.name for p in Path(d).rglob('*.tmp')), [])

    def test_output_survives_a_locale_that_cannot_encode_it(self):
        env = dict(os.environ, PYTHONUTF8='0', LC_ALL='en_US.ISO8859-1', LANG='en_US.ISO8859-1')
        probe = subprocess.run([sys.executable, '-c', 'import sys;print(sys.stdout.encoding)'], capture_output=True, text=True, env=env)
        if probe.returncode or 'utf' in probe.stdout.lower():
            self.skipTest('no Latin-1 locale on this system')
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)/'구성도.drawio'
            result = subprocess.run(CLI+['build', str(SKILL/'assets/templates/gcp-regional.json'), str(out)], capture_output=True, env=env)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['output'], str(out))

    def test_check_without_a_renderer_says_verification_is_incomplete(self):
        with tempfile.TemporaryDirectory() as d:
            env = {k: v for k, v in os.environ.items() if k not in ('DRAWIO_VIEWER',)}
            env['CLOUD_DRAWIO_CACHE'] = str(Path(d)/'empty-cache')
            result = cli('check', SKILL/'assets/templates/gcp-regional.json', Path(d)/'gcp.drawio', env=env)
            self.assertEqual(result.returncode, 2, result.stderr)
            verdict = json.loads(result.stdout)
            self.assertEqual((verdict['ok'], verdict['rendered'], verdict['stage']), (False, False, 'render'))
            self.assertIn('visual verification as not completed', verdict['reason'])
            self.assertTrue((Path(d)/'gcp.drawio').exists())
            model = json.loads((SKILL/'assets/templates/gcp-regional.json').read_text(encoding='utf-8'))
            model['nodes'][0]['w'] = 90
            (Path(d)/'bad.json').write_text(json.dumps(model), encoding='utf-8')
            result = cli('check', Path(d)/'bad.json', Path(d)/'bad.drawio', env=env)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(json.loads(result.stdout)['stage'], 'validate')

    def test_check_refuses_to_write_the_source_over_a_preview_name(self):
        with tempfile.TemporaryDirectory() as d:
            for name in ('arch.png', 'arch.svg', 'arch.json'):
                with self.subTest(name=name):
                    result = cli('check', SKILL/'assets/templates/gcp-regional.json', Path(d)/name)
                    self.assertEqual(result.returncode, 1)
                    self.assertIn('name the .drawio source here', json.loads(result.stdout)['errors'][0])
                    self.assertFalse((Path(d)/name).exists())

    def test_korean_model_builds_under_a_legacy_korean_locale(self):
        env = dict(os.environ, PYTHONUTF8='0', LC_ALL='ko_KR.eucKR', LANG='ko_KR.eucKR')
        probe = subprocess.run([sys.executable, '-c', 'import locale;print(locale.getpreferredencoding(False))'],
                               capture_output=True, text=True, env=env)
        if probe.returncode or 'utf' in probe.stdout.lower():
            self.skipTest('no non-UTF-8 Korean locale on this system')
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)/'aws-three-tier-ko.drawio'
            result = subprocess.run(CLI+['build', str(BASE/'examples/aws-three-tier-ko.model.json'), str(out)],
                                    capture_output=True, env=env)
            self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8', 'replace'))
            self.assertEqual(out.read_bytes(), (BASE/'examples/aws-three-tier-ko.drawio').read_bytes())


class AssetTests(unittest.TestCase):
    def test_icon_catalog_entries_match_pinned_safe_files(self):
        catalog = json.loads((SKILL/'assets/icon-catalog.json').read_text(encoding='utf-8'))
        pinned = re.compile(r'^https://(github\.com/jgraph/drawio/blob|raw\.githubusercontent\.com/jgraph/drawio)/[0-9a-f]{40}/')
        for key, entry in catalog.items():
            with self.subTest(icon=key):
                self.assertRegex(key, r'^(aws|azure|gcp)\.[a-z0-9-]+$')
                self.assertIn(entry['kind'], ('svg', 'stencil'))
                self.assertTrue(entry['name'].strip())
                self.assertRegex(entry['source'], pinned)
                data = (SKILL/'assets'/entry['file']).read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(), entry['sha256'])
                if entry['kind'] == 'svg':
                    text = data.decode('utf-8').lower()
                    for banned in ('<script', '<foreignobject', 'href="http', "href='http", 'url(http'):
                        self.assertNotIn(banned, text)
                else:
                    self.assertRegex(entry.get('color', ''), r'^#[0-9A-Fa-f]{6}$')
        on_disk = {f'icons/{p.name}' for p in (SKILL/'assets/icons').iterdir() if p.suffix in ('.svg', '.xml')}
        self.assertEqual({entry['file'] for entry in catalog.values()}, on_disk)

    def test_release_zip_matches_the_skill_folder(self):
        self.assertEqual(build_dist.differences(), [], 'rebuild it with: python3 tools/build_dist.py')

    def test_release_zip_is_reproducible_and_skips_untracked_files(self):
        probe = SKILL/'.env.release-probe'
        source = SKILL/'SKILL.md'
        stat = source.stat()
        try:
            probe.write_text('API_KEY=secret\n', encoding='utf-8')
            with tempfile.TemporaryDirectory() as d:
                first = build_dist.build(Path(d)/'first.zip')
                os.utime(source, (stat.st_atime, stat.st_mtime+3600))
                second = build_dist.build(Path(d)/'second.zip')
                self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertNotIn(probe, build_dist.skill_files())
        finally:
            probe.unlink(missing_ok=True)
            os.utime(source, (stat.st_atime, stat.st_mtime))


def _renderer():
    """Node, Playwright and a local draw.io viewer, or None when unavailable."""
    node = shutil.which('node')
    viewer = os.environ.get('DRAWIO_VIEWER') or str(BASE/'.cache/viewer-static.min.js')
    if not node or not Path(viewer).is_file():
        return None
    if subprocess.run([node, '-e', 'require("playwright")'], capture_output=True).returncode:
        return None
    return node, viewer


RENDERER = _renderer()


@unittest.skipUnless(RENDERER, 'needs node, playwright (NODE_PATH) and DRAWIO_VIEWER or .cache/viewer-static.min.js')
class RenderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def build(self, model, name):
        sys.path.insert(0, str(SKILL/'scripts'))
        import cloud_drawio
        path = self.dir/f'{name}.drawio'
        cloud_drawio.build(model, path)
        return path

    def render(self, drawio, *extra, output=None):
        node, viewer = RENDERER
        output = output or drawio.with_suffix('.png')
        result = subprocess.run([node, str(RENDER), str(drawio), str(output), viewer, *extra], capture_output=True, text=True)
        report = output.with_name(Path(output).stem+'.render.json')
        return result, (json.loads(report.read_text(encoding='utf-8')) if report.exists() and not result.stderr else None)

    def fixture(self):
        return json.loads((BASE/'evals/fixtures/routing-crossings.model.json').read_text(encoding='utf-8'))

    def test_crossing_renders_with_its_jump_arc(self):
        result, report = self.render(self.build(self.fixture(), 'cross'))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(report['geometry']['jumpMarkers'], 1)
        self.assertEqual(report['geometry']['missingJumps'], 0)
        self.assertEqual(report['textOverflow'], [])
        self.assertTrue((self.dir/'cross.svg').read_text(encoding='utf-8').count('fill="#FFFFFF"'))

    def test_crossing_without_jump_arc_fails(self):
        path = self.build(self.fixture(), 'cross')
        report = json.loads(path.with_suffix('.report.json').read_text(encoding='utf-8'))
        path.write_text(path.read_text(encoding='utf-8').replace('jumpStyle=arc;', ''), encoding='utf-8')
        report.pop('drawio_sha256')
        path.with_suffix('.report.json').write_text(json.dumps(report), encoding='utf-8')
        result, rendered = self.render(path)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(rendered['geometry']['missingJumps'], 1)

    def test_clipped_card_title_fails(self):
        model = json.loads((SKILL/'assets/templates/aws-three-tier.json').read_text(encoding='utf-8'))
        next(n for n in model['nodes'] if n['id'] == 'res-app-a')['label'] = 'PRODUCTION DATABASE WRITER NODE'
        result, rendered = self.render(self.build(model, 'caps'))
        self.assertEqual(result.returncode, 1)
        self.assertEqual([item['id'] for item in rendered['textOverflow']], ['__name_res-app-a'])

    def native(self, cells, width=500, height=300):
        body = ''.join(cells)
        path = self.dir/'native.drawio'
        path.write_text(f'<mxfile><diagram id="p" name="p"><mxGraphModel pageWidth="{width}" pageHeight="{height}"><root>'
                        f'<mxCell id="0"/><mxCell id="1" parent="0"/>{body}</root></mxGraphModel></diagram></mxfile>', encoding='utf-8')
        return path

    def vertex(self, cell_id, style, x, y, value=''):
        return (f'<mxCell id="{cell_id}" value="{value}" style="{style}" vertex="1" parent="1">'
                f'<mxGeometry x="{x}" y="{y}" width="120" height="60" as="geometry"/></mxCell>')

    def test_native_page_checks_icons_page_bounds_and_free_arrows(self):
        path = self.native([self.vertex('ok', 'rounded=1;', 40, 40, 'Service'),
                            self.vertex('lambda', 'shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.lambda;', 200, 40),
                            self.vertex('outside', 'rounded=1;', 560, 40, 'Database'),
                            '<mxCell id="arrow" style="endArrow=classic;" edge="1" parent="1"><mxGeometry relative="1" as="geometry">'
                            '<mxPoint x="60" y="200" as="sourcePoint"/><mxPoint x="160" y="220" as="targetPoint"/></mxGeometry></mxCell>'])
        result, rendered = self.render(path, '--no-report')
        self.assertEqual(result.returncode, 1)
        self.assertEqual(rendered['unknownIcons'], ['lambda'])
        self.assertEqual(rendered['offPage'], ['outside'])
        self.assertIn('editability not checked', rendered['warnings'][0])
        path = self.native([self.vertex('ok', 'rounded=1;', 40, 40, 'Service'),
                            '<mxCell id="arrow" style="endArrow=classic;" edge="1" parent="1"><mxGeometry relative="1" as="geometry">'
                            '<mxPoint x="60" y="200" as="sourcePoint"/><mxPoint x="160" y="220" as="targetPoint"/></mxGeometry></mxCell>'])
        result, rendered = self.render(path, '--no-report', output=self.dir/'NATIVE.PNG')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_free_arrow_in_a_patched_build_is_not_an_editability_failure(self):
        path = self.build(self.fixture(), 'cross')
        text = path.read_text(encoding='utf-8').replace('</root>', '<mxCell id="note-arrow" style="endArrow=classic;" edge="1" parent="1">'
                                                         '<mxGeometry relative="1" as="geometry"><mxPoint x="600" y="300" as="sourcePoint"/>'
                                                         '<mxPoint x="540" y="420" as="targetPoint"/></mxGeometry></mxCell></root>')
        path.write_text(text, encoding='utf-8')
        result, rendered = self.render(path, '--no-report')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(rendered['editability']['allEdgesConnected'])

    def test_legend_caption_that_wraps_fails(self):
        model = self.fixture()
        model['edges'][1]['kind'] = 'dns'
        model['legend'] = {'traffic': 'REQUEST AND RESPONSE DATA'}
        result, rendered = self.render(self.build(model, 'legend'))
        self.assertEqual(result.returncode, 1)
        self.assertEqual([item['id'] for item in rendered['textOverflow']], ['__legend_text_traffic'])

    def test_check_builds_renders_and_judges_in_one_step(self):
        node, viewer = RENDERER
        env = dict(os.environ, DRAWIO_VIEWER=viewer)
        result = cli('check', BASE/'examples/aws-three-az.model.json', self.dir/'az.drawio', env=env)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        verdict = json.loads(result.stdout)
        self.assertTrue(verdict['ok'] and verdict['rendered'])
        self.assertEqual(verdict['problems'], {})
        self.assertTrue((self.dir/'az.png').exists())
        model = json.loads((SKILL/'assets/templates/aws-three-tier.json').read_text(encoding='utf-8'))
        next(n for n in model['nodes'] if n['id'] == 'res-app-a')['label'] = 'PRODUCTION DATABASE WRITER NODE'
        (self.dir/'caps.json').write_text(json.dumps(model), encoding='utf-8')
        result = cli('check', self.dir/'caps.json', self.dir/'caps.drawio', env=env)
        self.assertEqual(result.returncode, 1)
        self.assertEqual([item['id'] for item in json.loads(result.stdout)['problems']['textOverflow']], ['__name_res-app-a'])

    def test_check_reports_a_missing_browser_as_unverified_not_failed(self):
        node, viewer = RENDERER
        env = dict(os.environ, DRAWIO_VIEWER=viewer, PLAYWRIGHT_BROWSERS_PATH=str(self.dir/'no-browsers'))
        env.pop('CHROME_PATH', None)
        result = cli('check', SKILL/'assets/templates/gcp-regional.json', self.dir/'gcp.drawio', env=env)
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn('Playwright browser is not installed', json.loads(result.stdout)['reason'])

    def test_option_without_value_is_rejected(self):
        result, _ = self.render(self.build(self.fixture(), 'cross'), '--report')
        self.assertEqual(result.returncode, 1)
        self.assertIn('--report needs a value', result.stderr)

    def test_missing_or_stale_report_and_bad_output_name_fail_fast(self):
        path = self.build(self.fixture(), 'cross')
        result, _ = self.render(path, output=self.dir/'cross.jpg')
        self.assertIn('output must be a .png file', result.stderr)
        path.write_text(path.read_text(encoding='utf-8').replace('Connector crossing verification', 'Connector crossing (edited)'), encoding='utf-8')
        result, _ = self.render(path)
        self.assertEqual(result.returncode, 1)
        self.assertIn('stale report', result.stderr)
        result, rendered = self.render(path, '--no-report')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(rendered['geometry']['checkedRoutes'], 0)
        path.with_suffix('.report.json').unlink()
        result, _ = self.render(path)
        self.assertIn('compiler report not found', result.stderr)


if __name__ == '__main__':
    unittest.main(verbosity=2)
