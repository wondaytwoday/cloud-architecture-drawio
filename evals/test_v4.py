"""Observable editing, workflow, budget and provenance contracts."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

BASE=Path(__file__).resolve().parents[1];SKILL=BASE/'cloud-architecture-drawio'
sys.path.insert(0,str(SKILL/'scripts'))
import cloud_drawio as c
import cloud_routes as r
import model_edit as edit
import model_pull as pull
import model_workflows as w


def simple():
    return {'provider':'aws','title':'Editing test','width':1000,'height':600,'containers':[],
            'nodes':[{'id':'a','icon':'generic','label':'A','x':100,'y':150,'w':156,'h':124},
                     {'id':'b','icon':'generic','label':'B','x':650,'y':150,'w':156,'h':124}],
            'edges':[{'id':'ab','source':'a','target':'b','sourcePort':'right','targetPort':'left'}]}


def cell(tree,ident):return next(x for x in tree.iter('mxCell') if x.get('id')==ident)

class V4(unittest.TestCase):
    def test_supported_style_and_bent_route_survive_pull_build_pull(self):
        m=simple()
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'edited.drawio';c.build(m,source)
            tree=ET.parse(source);edge=cell(tree,'ab');edge.set('style',edge.get('style')+'strokeColor=#FF0000;strokeWidth=3;')
            points=edge.find('mxGeometry/Array');points.clear()
            for x,y in [(300,212),(300,350),(600,350),(600,212)]:ET.SubElement(points,'mxPoint',x=str(x),y=str(y))
            points.set('as','points');tree.write(source)
            updated,summary=pull.pull(m,source)
            self.assertEqual(summary['ignored'],[]);self.assertEqual(summary['routes'],['ab'])
            rebuilt=Path(tmp)/'rebuilt.drawio';report=c.build(updated,rebuilt)
            self.assertEqual(report['routes']['ab'],[tuple(p) for p in updated['lockedRoutes']['ab']['points']])
            self.assertEqual(edit.style_map(cell(ET.parse(rebuilt),'ab').get('style'))['strokeColor'],'#FF0000')
            again,summary=pull.pull(updated,rebuilt);self.assertEqual(again,updated);self.assertEqual(summary['ignored'],[])

    def test_unsupported_edits_are_reported(self):
        m=simple()
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'edited.drawio';c.build(m,path);tree=ET.parse(path)
            edge=cell(tree,'ab');edge.set('style',edge.get('style')+'curved=1;')
            cell(tree,'__name_a').find('mxGeometry').set('x','18');tree.write(path)
            _,summary=pull.pull(m,path)
            self.assertTrue(any('curved' in x for x in summary['ignored']))
            self.assertTrue(any('__name_a' in x for x in summary['ignored']))

    def test_locked_path_colliding_with_new_resource_fails(self):
        m=simple();m['lockedRoutes']={'ab':{'source':'a','target':'b','points':[[256,212],[650,212]]}}
        m['nodes'].append({'id':'c','icon':'generic','label':'C','x':400,'y':150,'w':156,'h':124})
        with self.assertRaisesRegex(ValueError,'locked route hits'):c.compile_page(m,ET.Element('mxfile'),'test')

    def test_incremental_keeps_unchanged_edges_and_reroutes_moved_endpoint(self):
        m=simple()
        with tempfile.TemporaryDirectory() as tmp:
            previous=c.build(m,Path(tmp)/'old.drawio')
            current=c.build(m,Path(tmp)/'new.drawio',previous=previous)
            self.assertEqual(current['routes'],previous['routes']);self.assertEqual(current['incremental']['retained'],['ab'])
            m['nodes'][1]['y']+=100
            current=c.build(m,Path(tmp)/'moved.drawio',previous=previous)
            self.assertEqual(current['incremental']['rerouted'],['ab']);self.assertNotEqual(current['routes'],previous['routes'])

    def test_incremental_invalidated_by_new_obstacle(self):
        m=simple();previous=c.compile_page(m,ET.Element('mxfile'),'old')
        m['nodes'].append({'id':'c','icon':'generic','label':'C','x':400,'y':150,'w':156,'h':124})
        updated,summary=edit.reuse(m,previous,c.header_rect)
        self.assertEqual(summary['rerouted'],['ab']);self.assertFalse(updated['lockedRoutes'])

    def test_budget_stops_inside_first_search(self):
        work={'steps':0}
        with patch.object(r,'ROUTING_WORK_LIMIT',1):
            with self.assertRaises(r.BudgetError):r.plan(simple(),c.header_rect,work=work)
        self.assertEqual(work['steps'],1)

    def test_check_malformed_input_is_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'bad.json';p.write_text('{bad')
            done=subprocess.run([sys.executable,str(SKILL/'scripts/cloud_drawio.py'),'check',str(p),str(Path(tmp)/'out.drawio')],capture_output=True,text=True)
            self.assertEqual(done.returncode,1);self.assertFalse(json.loads(done.stdout)['ok']);self.assertNotIn('Traceback',done.stderr)

    def test_check_timeout_returns_structured_failure(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(c,'find_renderer',return_value=(('node','viewer',{}),None)),patch.object(c.subprocess,'run',side_effect=subprocess.TimeoutExpired('node',.01)):
            verdict,code=c.check(simple(),Path(tmp)/'out.drawio',timeout=.01)
            self.assertEqual(code,1);self.assertEqual(verdict['stage'],'render');self.assertIn('timed out',verdict['errors'][0])

    def test_junction_bus_is_explicit_and_editable(self):
        m=simple();m['nodes'].append({'id':'junction','icon':'generic.junction','label':'Branch','x':450,'y':206,'w':12,'h':12})
        m['nodes'].append({'id':'c','icon':'generic','label':'C','x':378,'y':360,'w':156,'h':124})
        m['edges']=[{'id':'trunk','source':'a','target':'junction','sourcePort':'right','targetPort':'left'},
                    {'id':'right','source':'junction','target':'b','sourcePort':'right','targetPort':'left'},
                    {'id':'down','source':'junction','target':'c','sourcePort':'bottom','targetPort':'top'}]
        self.assertEqual(c.validate(m)[0],[])
        tree=ET.Element('mxfile');report=c.compile_page(m,tree,'test')
        self.assertIn('ellipse;',cell(tree,'junction').get('style'));self.assertEqual(report['quality']['overlapLength'],0);self.assertEqual(report['quality']['continuationCount'],0)

    def test_views_preserve_overview_and_disclose_omissions(self):
        m=simple();m['edges'].append({'id':'ba','source':'b','target':'a','kind':'management'})
        models,manifest=w.views(m)
        self.assertEqual(models['overview']['edges'],m['edges'])
        self.assertEqual(manifest['views']['application']['omittedEdges'],['ba'])
        self.assertEqual(manifest['views']['operations']['includedEdges'],['ba'])
        with tempfile.TemporaryDirectory() as tmp:c.bundle(list(models.values()),Path(tmp)/'views.drawio')

    def test_repair_preserves_topology_and_source(self):
        m=simple();m['nodes'][1]['x']=286;before=copy.deepcopy(m)
        with self.assertRaises(ValueError):c.compile_page(m,ET.Element('mxfile'),'crowded')
        result,models=w.repair(m,limit=2)
        self.assertIsNotNone(result['best']);self.assertEqual(m,before)
        for model in models.values():self.assertEqual(model['edges'],m['edges'])
        self.assertTrue(all(c.validate(model)[0]==[] for model in models.values()))

    def test_diff_highlight_and_evidence(self):
        a=simple();b=copy.deepcopy(a);b['nodes'][1]['label']='Renamed'
        b['nodes'][0]['evidence']=[{'kind':'iac','source':'main.tf:12'}]
        b['edges'][0]['evidence']=[{'kind':'inferred','source':'design discussion','confirmed':False}]
        report=w.diff(a,b);self.assertEqual(report['counts']['modified'],3)
        highlighted=w.highlight(b,report);self.assertEqual(c.validate(highlighted)[0],[])
        evidence=w.evidence(b);self.assertEqual(evidence['errors'],[]);self.assertIn('ab',evidence['unconfirmed']);self.assertNotIn('a',evidence['unconfirmed'])
        b['edges'][0]['evidence'][0]['confirmed']='yes';self.assertTrue(w.evidence(b)['errors'])

    def test_doctor_returns_json_without_renderer(self):
        import doctor
        with patch.object(c,'find_renderer',return_value=(None,'test missing renderer')):
            result=doctor.inspect(smoke=True)
        self.assertFalse(result['ok']);self.assertFalse(result['smoke']['rendered'])

    def test_views_cli_writes_reopenable_bundle_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);w.write(p/'model.json',simple())
            command=[sys.executable,str(SKILL/'scripts/cloud_drawio.py'),'views',str(p/'model.json'),str(p/'views')]
            done=subprocess.run(command,capture_output=True,text=True)
            self.assertEqual(done.returncode,0,done.stderr)
            self.assertEqual(pull.page_count(p/'views/views.drawio'),2)
            manifest=w.read(p/'views/manifest.json');self.assertEqual(manifest['views']['overview']['omittedEdges'],[])
            before=(p/'views/views.drawio').read_bytes()
            done=subprocess.run(command,capture_output=True,text=True)
            self.assertEqual(done.returncode,1);self.assertEqual(before,(p/'views/views.drawio').read_bytes())

if __name__=='__main__':unittest.main()
