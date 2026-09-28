"""Behavioral regressions for actual diagrams and intentional invalid inputs."""
import copy
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
        return json.loads((TEMPLATES/(name+'.json')).read_text())

    def rejects(self,m,substring):
        self.assertTrue(any(substring in e for e in c.validate(m)[0]),c.validate(m))

    def test_templates_build_and_route_without_card_or_title_collisions(self):
        for name in ('aws-three-tier','azure-regional','gcp-regional'):
            with self.subTest(name=name),tempfile.TemporaryDirectory() as d:
                m=self.model(name); out=Path(d)/'diagram.drawio'; report=c.build(m,out)
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
        m=json.loads((BASE/'examples/aws-three-az.model.json').read_text())
        for reverse in (False,True):
            if reverse:m['containers'].reverse()
            with self.subTest(reverse=reverse),tempfile.TemporaryDirectory() as d:
                p=Path(d)/'diagram.drawio';c.build(m,p)
                order={cell.get('id'):i for i,cell in enumerate(ET.parse(p).findall('.//mxCell'))}
                for group in (b for b in m['containers'] if b.get('overlay')):
                    siblings=[b for b in m['containers'] if b.get('parent')==group.get('parent') and not b.get('overlay')]
                    self.assertTrue(all(order[b['id']]<order[group['id']] for b in siblings))


if __name__=='__main__':unittest.main(verbosity=2)
