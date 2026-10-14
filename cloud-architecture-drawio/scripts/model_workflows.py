"""Bounded layout proposals, derived views, semantic diffs and evidence inventories."""
import copy
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import model_layout


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path,value):
    import cloud_drawio as c
    c.write_outputs([(path,(json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode())])


def evidence(m):
    rows=[];errors=[]
    for category,items in [('model',[dict(m,id='$model')])]+[(k,m.get(k,[])) for k in ('containers','nodes','edges')]:
        for item in items:
            records=item.get('evidence',[]);assumptions=item.get('assumptions',[])
            if not isinstance(records,list):errors.append(f"{item['id']}: evidence must be a list");records=[]
            for record in records:
                if not isinstance(record,dict) or record.get('kind') not in ('user','iac','observed','inferred') or not isinstance(record.get('source'),str) or not record.get('source'):
                    errors.append(f"{item['id']}: evidence needs kind (user/iac/observed/inferred) and source")
                elif 'confirmed' in record and not isinstance(record['confirmed'],bool):errors.append(f"{item['id']}: confirmed must be boolean")
            if not isinstance(assumptions,list) or any(not isinstance(a,str) for a in assumptions):errors.append(f"{item['id']}: assumptions must be a list of strings")
            rows.append({'id':item['id'],'category':category,'evidence':records,'assumptions':assumptions,
                         'unconfirmed':not records or any(isinstance(r,dict) and r.get('kind')=='inferred' and not r.get('confirmed',False) for r in records)})
    return {'items':rows,'errors':errors,'unconfirmed':[r['id'] for r in rows if r['unconfirmed']],
            'note':'Provenance is supplied by the author; this report does not verify deployment or runtime traffic.'}


def diff(before,after):
    a,b=model_layout.normalize(before),model_layout.normalize(after)
    changes=[]
    for category in ('containers','nodes','edges'):
        aa={i['id']:i for i in a.get(category,[])};bb={i['id']:i for i in b.get(category,[])}
        for ident in sorted(aa.keys()|bb.keys()):
            if ident not in aa:changes.append({'category':category,'id':ident,'change':'added','after':bb[ident]})
            elif ident not in bb:changes.append({'category':category,'id':ident,'change':'removed','before':aa[ident]})
            else:
                fields={k:{'before':aa[ident].get(k),'after':bb[ident].get(k)} for k in sorted(aa[ident].keys()|bb[ident].keys()) if aa[ident].get(k)!=bb[ident].get(k)}
                if fields:changes.append({'category':category,'id':ident,'change':'modified','fields':fields})
    page={k:{'before':a.get(k),'after':b.get(k)} for k in sorted(a.keys()|b.keys()) if k not in ('containers','nodes','edges') and a.get(k)!=b.get(k)}
    return {'changes':changes,'page':page,'counts':{k:sum(x['change']==k for x in changes) for k in ('added','removed','modified')}}


def highlight(m,report):
    out=copy.deepcopy(m);styles=out.setdefault('presentation',{})
    for change in report['changes']:
        if change['change']=='removed':continue
        styles.setdefault(change['id'],{}).update(strokeColor='#159447' if change['change']=='added' else '#D97706',strokeWidth=3)
    out.setdefault('notes',[]).append('Diff: green = added; orange = modified. Removed items are listed in the diff report.')
    return out


VIEW_KINDS={'network':{'dns','egress','connectivity'},'application':{'traffic','event'},'operations':{'management','replication','association'}}


def views(m):
    """One complete overview plus purpose-filtered edges; retain original geometry."""
    import cloud_drawio as c
    base=model_layout.normalize(m);out={'overview':copy.deepcopy(base)};manifest={}
    for name,kinds in VIEW_KINDS.items():
        model=copy.deepcopy(base);model['edges']=[e for e in model['edges'] if e.get('kind','traffic') in kinds]
        if not model['edges']:continue
        selected={e[k] for e in model['edges'] for k in ('source','target')}
        parent={x['id']:x.get('parent') for k in ('nodes','containers') for x in model[k]}
        queue=list(selected)
        while queue:
            p=parent.get(queue.pop())
            if p and p not in selected:selected.add(p);queue.append(p)
        model['nodes']=[n for n in model['nodes'] if n['id'] in selected]
        model['containers']=[b for b in model['containers'] if b['id'] in selected]
        for b in model['containers']:
            if 'members' in b:b['members']=[i for i in b['members'] if i in selected]
        edgeids={e['id'] for e in model['edges']}
        model['lockedRoutes']={eid:v for eid,v in model.get('lockedRoutes',{}).items() if eid in edgeids}
        # Compile once without style overrides to determine which generated cells exist.
        styles=model.pop('presentation',{})
        tree=ET.Element('mxfile');c.compile_page(model,tree,name)
        ids={el.get('id') for el in tree.iter('mxCell')}
        model['presentation']={cid:v for cid,v in styles.items() if cid in ids}
        model['title']=base.get('title','Architecture')+' · '+name
        out[name]=model
    for name,model in out.items():
        errors,_=c.validate(model)
        if errors:raise ValueError(f'{name}: '+ '; '.join(errors))
        shown={e['id'] for e in model['edges']}
        manifest[name]={'includedEdges':sorted(shown),'omittedEdges':sorted({e['id'] for e in base['edges']}-shown)}
    return out,{'views':manifest,'note':'Overview preserves every relationship. Purpose views filter by edge kind; inspect omissions before sharing.'}


def repair(m,limit=6):
    """Test bounded geometric expansions, preserving topology and resource card size."""
    import cloud_drawio as c
    import cloud_routes as r
    if m.get('lockedRoutes'):return {'candidates':[],'reason':'Explicit routes are locked. Keep them or explicitly remove selected locks before requesting layout proposals.'},{}
    base=model_layout.normalize(m);candidates=[];models={}
    factors=[(1.25,1),(1,1.25),(1.25,1.25),(1.5,1.25),(1.25,1.5),(1.5,1.5)][:limit]
    oldlimit=r.ROUTING_WORK_LIMIT
    try:
        r.ROUTING_WORK_LIMIT=min(oldlimit,20000)
        for index,(fx,fy) in enumerate(factors,1):
            model=copy.deepcopy(base);ident=f'expand-{index}'
            for kind in ('containers','nodes'):
                for item in model[kind]:
                    item['x']=30+(item['x']-30)*fx;item['y']=90+(item['y']-90)*fy
                    if kind=='containers':item['w']*=fx;item['h']*=fy
            model['width']=int(base['width']*fx+1);model['height']=int(base['height']*fy+1)
            errors,warnings=c.validate(model);quality=None
            if not errors:
                try:quality=c.compile_page(model,ET.Element('mxfile'),ident)['quality']
                except ValueError as exc:errors=str(exc).splitlines()
            candidates.append({'id':ident,'changes':{'horizontalScale':fx,'verticalScale':fy},'ok':not errors,'errors':errors,'warnings':warnings,'quality':quality})
            if not errors:models[ident]=model
    finally:r.ROUTING_WORK_LIMIT=oldlimit
    valid=[v for v in candidates if v['ok']]
    best=min(valid,key=lambda v:(v['quality']['crossingCount'],v['quality']['totalLength']))['id'] if valid else None
    return {'candidates':candidates,'best':best,'note':'Bounded spacing proposals only; no topology or labels removed. Render and inspect an applied candidate.'},models


def configure(sub):
    p=sub.add_parser('repair',help='propose bounded layout expansions; optionally write one')
    p.add_argument('model');p.add_argument('--apply',help='candidate ID or best');p.add_argument('--output')
    p=sub.add_parser('views',help='write overview and purpose views plus a bundle')
    p.add_argument('model');p.add_argument('directory')
    p=sub.add_parser('diff',help='compare model IDs, topology, geometry and presentation')
    p.add_argument('before');p.add_argument('after');p.add_argument('--output');p.add_argument('--highlight')
    p=sub.add_parser('evidence',help='inventory provenance and unresolved assumptions')
    p.add_argument('model');p.add_argument('--output');p.add_argument('--strict',action='store_true')


def dispatch(a):
    import cloud_drawio as c
    if a.cmd=='diff':
        after=read(a.after);result=diff(read(a.before),after)
        if a.highlight:write(a.highlight,highlight(after,result))
    elif a.cmd=='evidence':
        result=evidence(read(a.model))
    elif a.cmd=='repair':
        result,models=repair(read(a.model))
        if a.apply:
            selected=result.get('best') if a.apply=='best' else a.apply
            if selected not in models:raise ValueError('no successful candidate selected')
            if not a.output:raise ValueError('--apply requires --output for the revised model')
            if Path(a.output).resolve()==Path(a.model).resolve():raise ValueError('write the proposal to a new file; retain the source')
            write(a.output,models[selected]);result['applied']=selected
    elif a.cmd=='views':
        models,result=views(read(a.model));folder=Path(a.directory)
        if folder.exists() and any(folder.iterdir()):raise ValueError('views directory must be empty; preserve existing work')
        folder.mkdir(parents=True,exist_ok=True)
        c.bundle(list(models.values()),folder/'views.drawio')
        for name,model in models.items():write(folder/(name+'.json'),model)
        write(folder/'manifest.json',result)
    else:return False
    if a.cmd in ('diff','evidence') and a.output:write(a.output,result)
    c.emit(result,indent=2)
    if a.cmd=='evidence' and (result['errors'] or a.strict and result['unconfirmed']):raise SystemExit(1)
    return True
