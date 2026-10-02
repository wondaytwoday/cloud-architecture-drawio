"""Behavioral regressions for actual diagrams and intentional invalid inputs."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

BASE=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('compiler',BASE/'cloud-architecture-drawio/scripts/cloud_drawio.py')
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
TEMPLATES=BASE/'cloud-architecture-drawio/assets/templates'


class CompilerTests(unittest.TestCase):
    def model(self,name='aws-three-tier'):
        return json.loads((TEMPLATES/(name+'.json')).read_text(encoding='utf-8'))

    def rejects(self,m,substring):
        self.assertTrue(any(substring in e for e in c.validate(m)[0]),c.validate(m))

    def test_templates_build_and_route_without_card_or_title_collisions(self):
        names=sorted(p.stem for p in TEMPLATES.glob('*.json'))
        self.assertGreaterEqual(len(names),3)
        for name in names:
            with self.subTest(name=name),tempfile.TemporaryDirectory() as d:
                source=self.model(name); out=Path(d)/'diagram.drawio'; report=c.build(source,out)
                m=c.model_layout.normalize(source)
                self.assertEqual(report['warnings'],[])
                obstacles=[c.rect(n) for n in m['nodes']]+[c.header_rect(b) for b in m['containers']]
                for pts in report['routes'].values():
                    for a,b in zip(pts,pts[1:]):
                        self.assertFalse(any(c.line_hits(a,b,r) for r in obstacles))
                doc=ET.parse(out); cells={v.get('id'):v for v in doc.findall('.//mxCell')}
                self.assertEqual(len(doc.findall('.//mxCell')),len(cells))
                for e in m['edges']:
                    self.assertEqual(cells[e['id']].get('source'),e['source'])
                    self.assertEqual(cells[e['id']].get('target'),e['target'])
                for n in m['nodes']:
                    geo=cells[n['id']].find('mxGeometry')
                    p=next((b for b in m['containers'] if b['id']==n.get('parent')),{'x':0,'y':0})
                    self.assertEqual(float(geo.get('x'))+p['x'],n['x'])
                before=out.read_bytes();c.build(m,out);self.assertEqual(before,out.read_bytes())

    def test_missing_icon_and_target(self):
        m=self.model();m['nodes'][0]['icon']='aws.imaginary';self.rejects(m,'unknown icon')
        m=self.model();m['edges'][0]['target']='absent';self.rejects(m,'missing target')

    def test_aws_subnet_scope(self):
        m=self.model();next(b for b in m['containers'] if b['id']=='web-a')['parent']='vpc'
        self.rejects(m,'AWS subnet needs an AZ')

    def test_regional_subnet_cannot_be_zonal(self):
        for name in ('gcp-regional','azure-regional'):
            m=self.model(name);next(b for b in m['containers'] if b['id']=='network')['kind']='az'
            self.rejects(m,'regional, not zonal')

    def test_managed_service_does_not_move_into_endpoint_subnet(self):
        m=self.model('azure-regional');n=next(n for n in m['nodes'] if n['id']=='database');n['parent']='data';n['x']=800
        self.rejects(m,'managed/global service')

    def test_overlap_and_long_korean_label(self):
        m=self.model();m['nodes'][1].update({k:m['nodes'][0][k] for k in ('x','y','w','h')});self.rejects(m,'Resource overlap')
        m=self.model();m['nodes'][0]['label']='매우 긴 한국어 아키텍처 리소스 이름이 충분한 공간 없이 표시되어서는 안 됩니다';self.rejects(m,'exceeds 2 lines')

    def test_english_wrap_preserves_words(self):
        self.assertEqual(c.wrapped('Cloud Load Balancing',148,13),['Cloud Load','Balancing'])

    def test_cycle_and_duplicate(self):
        m=self.model();m['containers'][0]['parent']='vpc';self.rejects(m,'parent cycle')
        m=self.model();m['nodes'][0]['id']=m['nodes'][1]['id'];self.rejects(m,'Duplicate IDs')

    def test_group_header_obstacle(self):
        m=self.model();n=next(n for n in m['nodes'] if n['id']=='internal-lb');n['y']=1198;n['x']=800
        self.rejects(m,'overlaps container title')

    def test_escaping_and_stable_resource_ids(self):
        m=self.model();m['title']='A & B <test>';m['nodes'][0]['label']='A & B <node>'
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'diagram.drawio';c.build(m,p);doc=ET.parse(p)
            self.assertEqual(doc.find('.//mxCell[@id="__title"]').get('value'),m['title'])
            self.assertIsNotNone(doc.find('.//mxCell[@id="'+m['nodes'][0]['id']+'"]'))

    def test_added_az_background_cannot_cover_membership_overlay(self):
        m=json.loads((BASE/'examples/aws-three-az.model.json').read_text(encoding='utf-8'))
        for reverse in (False,True):
            if reverse:m['containers'].reverse()
            with self.subTest(reverse=reverse),tempfile.TemporaryDirectory() as d:
                p=Path(d)/'diagram.drawio';c.build(m,p)
                order={cell.get('id'):i for i,cell in enumerate(ET.parse(p).findall('.//mxCell'))}
                for group in (b for b in m['containers'] if b.get('overlay')):
                    siblings=[b for b in m['containers'] if b.get('parent')==group.get('parent') and not b.get('overlay')]
                    self.assertTrue(all(order[b['id']]<order[group['id']] for b in siblings))


    def legend(self,path):
        cells=ET.parse(path).findall('.//mxCell')
        return [(cell.get('id')[len('__legend_text_'):],cell.get('value')) for cell in cells if cell.get('id','').startswith('__legend_text_')]

    def test_legend_is_localized_and_ordered_by_relationship_kind(self):
        m=json.loads((BASE/'examples/aws-three-tier-ko.model.json').read_text(encoding='utf-8'))
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'ko.drawio';c.build(m,p)
            self.assertEqual(self.legend(p),[('traffic','요청 / 데이터'),('replication','복제'),('dns','DNS 조회'),('association','정책 연결')])
            m['edges'].reverse();m['legend']={'dns':'DNS 질의'};q=Path(d)/'ko2.drawio';c.build(m,q)
            self.assertEqual(self.legend(q),[('traffic','요청 / 데이터'),('replication','복제'),('dns','DNS 질의'),('association','정책 연결')])

    def test_relationship_kinds_have_distinct_dash_patterns_and_colors(self):
        dashes=[v[1] for v in c.EDGE.values() if v[1]]
        self.assertEqual(len(dashes),len(set(dashes)))
        def lab(hex_color):
            rgb=[int(hex_color[i:i+2],16)/255 for i in (1,3,5)]
            r,g,b=[(v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4) for v in rgb]
            xyz=[(r*.4124+g*.3576+b*.1805)/.95047,r*.2126+g*.7152+b*.0722,(r*.0193+g*.1192+b*.9505)/1.08883]
            f=[v**(1/3) if v>.008856 else 7.787*v+16/116 for v in xyz]
            return 116*f[1]-16,500*(f[0]-f[1]),200*(f[1]-f[2])
        colors=[lab(v[0]) for v in c.EDGE.values()]
        for i,a in enumerate(colors):
            for b in colors[i+1:]:
                self.assertGreater(sum((x-y)**2 for x,y in zip(a,b))**.5,20)

    def test_two_line_card_text_gets_its_whole_cell(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'diagram.drawio';c.build(self.model(),p)
            for cell in ET.parse(p).findall('.//mxCell'):
                if cell.get('id','').startswith(('__name_','__detail_')):
                    self.assertIn('spacing=0;',cell.get('style'))

    def test_legend_captions_are_measurable_and_icons_keep_their_shape(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'gcp.drawio';c.build(self.model('gcp-regional'),p)
            cells={cell.get('id'):cell for cell in ET.parse(p).findall('.//mxCell')}
            legend=[cell for cid,cell in cells.items() if cid.startswith('__legend_text_')]
            self.assertTrue(legend)
            for cell in legend:self.assertIn('whiteSpace=wrap;overflow=hidden;spacing=0;',cell.get('style'))
        # gcp2 stencils declare a variable aspect; the compiler pins it so the
        # 172x153 Compute Engine glyph is not squeezed into the square icon box.
        import urllib.parse,zlib,base64
        style=c.icon_style('gcp.compute');payload=style[len('shape=stencil('):style.index(');')]
        xml=urllib.parse.unquote(zlib.decompress(base64.b64decode(payload),-15).decode())
        self.assertTrue(xml.startswith('<shape aspect="fixed"'))

    def test_report_lists_plain_box_fallbacks(self):
        with tempfile.TemporaryDirectory() as d:
            report=c.build(self.model('gcp-regional'),Path(d)/'gcp.drawio')
        self.assertEqual(report['fallbackIcons'],['psc'])

    def test_report_records_the_file_it_describes(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'diagram.drawio';report=c.build(self.model(),p)
            self.assertEqual(report['version'],3)
            self.assertEqual(report['drawio_sha256'],hashlib.sha256(p.read_bytes()).hexdigest())
            saved=json.loads(p.with_suffix('.report.json').read_text(encoding='utf-8'))
            self.assertEqual(saved['drawio_sha256'],report['drawio_sha256'])
            self.assertEqual(sorted(x.name for x in Path(d).iterdir()),['diagram.drawio','diagram.report.json'])

    def test_rebuild_refuses_to_discard_manual_edits(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'diagram.drawio';m=self.model();c.build(m,p)
            p.write_text(p.read_text(encoding='utf-8').replace('Amazon CloudFront','CloudFront (edited)'),encoding='utf-8')
            edited=p.read_bytes()
            with self.assertRaisesRegex(ValueError,'changed after it was built.*--force'):
                c.build(m,p)
            self.assertEqual(p.read_bytes(),edited)
            c.build(m,p,force=True)
            self.assertNotEqual(p.read_bytes(),edited)
            p.with_suffix('.report.json').unlink()
            with self.assertRaisesRegex(ValueError,'exists without diagram.report.json'):
                c.build(m,p)

    def test_shipped_examples_match_a_fresh_build(self):
        """Golden check: examples/ must be what the current compiler produces."""
        names=sorted(p.name[:-len('.model.json')] for p in (BASE/'examples').glob('*.model.json'))
        self.assertGreaterEqual(len(names),12)
        for name in names:
            with self.subTest(name=name),tempfile.TemporaryDirectory() as d:
                m=json.loads((BASE/'examples'/f'{name}.model.json').read_text(encoding='utf-8'))
                p=Path(d)/f'{name}.drawio';c.build(m,p)
                self.assertEqual(p.read_bytes(),(BASE/'examples'/f'{name}.drawio').read_bytes())
                self.assertEqual(p.with_suffix('.report.json').read_bytes(),(BASE/'examples'/f'{name}.report.json').read_bytes())


if __name__=='__main__':unittest.main(verbosity=2)
