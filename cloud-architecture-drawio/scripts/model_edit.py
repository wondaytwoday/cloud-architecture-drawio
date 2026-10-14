"""Portable presentation overrides and explicit, validated connector paths."""
import copy
import math
import re
import xml.etree.ElementTree as ET

COLORS={'fillColor','strokeColor','fontColor','labelBackgroundColor','labelBorderColor'}
NUMBERS={'fontSize','fontStyle','strokeWidth','opacity','fillOpacity','strokeOpacity','dashed','rounded','arcSize'}
TEXT={'fontFamily','dashPattern'}
STYLE_KEYS=COLORS|NUMBERS|TEXT


def style_map(value):
    return dict(p.split('=',1) for p in value.split(';') if '=' in p)


def validate(m):
    errors=[]
    presentation=m.get('presentation',{})
    if not isinstance(presentation,dict):return ['presentation must map cell IDs to style properties']
    for cid,styles in presentation.items():
        if not isinstance(styles,dict):errors.append(f'{cid}: presentation must be an object');continue
        for k,v in styles.items():
            value=str(v)
            valid=k in STYLE_KEYS and ';' not in value and '=' not in value and '\n' not in value
            if k in COLORS:valid=valid and bool(re.fullmatch(r'#[0-9a-fA-F]{3,8}|none|default',value))
            if k in NUMBERS:
                try:valid=valid and math.isfinite(float(v)) and 0<=float(v)<=1000
                except (ValueError,TypeError):valid=False
            if k in TEXT:valid=valid and bool(re.fullmatch(r'[\w ,.-]{1,100}',value))
            if not valid:errors.append(f'{cid}: unsupported presentation {k}={value!r}')
    locks=m.get('lockedRoutes',{})
    if not isinstance(locks,dict):return errors+['lockedRoutes must map edge IDs to routes']
    edges={e.get('id'):e for e in m.get('edges',[]) if isinstance(e,dict)}
    for eid,lock in locks.items():
        if eid not in edges or not isinstance(lock,dict):errors.append(f'{eid}: unknown or invalid locked route');continue
        pts=lock.get('points')
        if not isinstance(pts,list) or len(pts)<2 or any(not isinstance(p,(list,tuple)) or len(p)!=2 or any(not isinstance(v,(float,int)) or isinstance(v,bool) or not math.isfinite(v) for v in p) for p in pts):
            errors.append(f'{eid}: locked route needs at least two finite coordinate pairs');continue
        if lock.get('mode','manual') not in ('manual','retained'):errors.append(f'{eid}: invalid route mode')
        for end in ('source','target'):
            if lock.get(end)!=edges[eid].get(end):errors.append(f'{eid}: locked {end} no longer matches; reroute explicitly')
        if any(a==b or (a[0]!=b[0] and a[1]!=b[1]) for a,b in zip(pts,pts[1:])):errors.append(f'{eid}: locked route must have nonzero orthogonal segments')
    return errors


def apply(root,m):
    cells={c.get('id'):c for c in root.findall('mxCell')}
    for cid,props in m.get('presentation',{}).items():
        if cid not in cells:raise ValueError(f'{cid}: presentation refers to a missing cell')
        c=cells[cid];c.set('style',c.get('style','')+''.join(f'{k}={v};' for k,v in sorted(props.items())))


def point_port(node,p):
    x,y,w,h=(node[k] for k in ('x','y','w','h'))
    for side,at,wanted,span,start,coord in [('top',p[1],y,w,x,p[0]),('bottom',p[1],y+h,w,x,p[0]),('left',p[0],x,h,y,p[1]),('right',p[0],x+w,h,y,p[1])]:
        f=(coord-start)/span
        if abs(at-wanted)<.01 and .1-1e-8<=f<=.9+1e-8:return side,f
    raise ValueError('fixed endpoint no longer lies on its card side (10%..90%); reroute explicitly')


def route_model(m):
    """Pin attachment points before automatic port allocation."""
    import cloud_routes as r
    if not m.get('lockedRoutes'):return m
    out=copy.deepcopy(m);nodes=r.endpoints(out)
    for e in out['edges']:
        lock=out['lockedRoutes'].get(e['id'])
        if not lock:continue
        for end,p in [('source',lock['points'][0]),('target',lock['points'][-1])]:
            try:side,f=point_port(nodes[e[end]],p)
            except ValueError as exc:raise ValueError(f"{e['id']}: {exc}") from exc
            e[end+'Port']=side;e[end+'Offset']=f
    return out


def capture(source,model,drawn,summary):
    """Compare against compiler cells, preserving supported edits and disclosing all others."""
    import cloud_drawio as c
    import model_pull as pull
    baseline=ET.Element('mxfile');c.compile_page(source,baseline,'baseline')
    for wrapper in drawn.iter():
        if wrapper.tag in pull.WRAPPERS:
            for key in wrapper.attrib.keys()-{'id','label'}:
                summary['ignored'].append(f"{wrapper.get('id')}: wrapper property {key} is not preserved")
    original={cid:cell for cid,_,cell in pull.cells(baseline.find('diagram/mxGraphModel'))}
    actual={cid:cell for cid,_,cell in pull.cells(drawn)}
    summary.update(styles=[],routes=[],rerouted=[])
    styles=copy.deepcopy(model.get('presentation',{}));locks=copy.deepcopy(model.get('lockedRoutes',{}))
    by={i['id']:i for k in ('nodes','containers') for i in model.get(k,[])}
    for cid in sorted(actual.keys()-original.keys()):
        if cid.startswith('__'): summary['unmodelled'].append(cid)
    def canonical(el):
        if el is None:return None
        def number(v):
            try:return float(v)
            except ValueError:return v
        return el.tag,sorted((k,number(v)) for k,v in el.attrib.items()),[canonical(ch) for ch in el]
    geometry=lambda cell: canonical(cell.find('mxGeometry'))
    for cid,old in original.items():
        new=actual.get(cid)
        if new is None:
            if cid.startswith('__') and not cid.startswith('__label_'):summary['ignored'].append(f'{cid}: generated child was deleted')
            continue
        for key in new.attrib.keys()-{'id','value','parent','source','target','style','vertex','edge'}:
            if old.get(key)!=new.get(key):summary['ignored'].append(f'{cid}: unsupported cell attribute {key}')
        if cid.startswith('__') and old.get('parent')!=new.get('parent'):summary['ignored'].append(f'{cid}: generated child parent changed')
        for key in ('vertex','edge'):
            if old.get(key)!=new.get(key):summary['ignored'].append(f'{cid}: changed cell type {key}')
        named=lambda el: {v for v in el.get('style','').split(';') if v and '=' not in v}
        if named(old)!=named(new):summary['ignored'].append(f'{cid}: named base style changed')
        if cid in by:
            og,ng=old.find('mxGeometry'),new.find('mxGeometry')
            if ng is not None and (list(ng) or any(ng.get(k)!=og.get(k) for k in ng.attrib.keys()-{'x','y','width','height','as'})):
                summary['ignored'].append(f'{cid}: unsupported extra shape geometry')
        a,b=style_map(old.get('style','')),style_map(new.get('style',''))
        for key in sorted(a.keys()|b.keys()):
            if a.get(key)==b.get(key):continue
            if key in STYLE_KEYS and key in b:
                styles.setdefault(cid,{})[key]=b[key];summary['styles'].append(f'{cid}.{key}')
            elif key not in ('exitX','exitY','entryX','entryY','exitPerimeter','entryPerimeter'):
                summary['ignored'].append(f'{cid}: unsupported style change {key}')
        if old.get('edge')=='1':
            oldgeo=geometry(old);newgeo=geometry(new)
            terminals=any(old.get(k)!=new.get(k) for k in ('source','target'))
            ports=any(a.get(k)!=b.get(k) for k in ('exitX','exitY','entryX','entryY'))
            if oldgeo==newgeo and not ports:
                if terminals: summary['rerouted'].append(cid)
                continue
            if any(new.get(k) not in by for k in ('source','target')):continue
            try:
                if new.get('parent')!='1' or b.get('curved','0')!='0' or b.get('edgeStyle','none') not in ('none',''):
                    raise ValueError('automatic/curved routing or nested edge parent cannot be preserved')
                shapes,_,_,_=pull.drawing(drawn)
                pts=[]
                for end,px,py in [('source','exitX','exitY'),('target','entryX','entryY')]:
                    box=shapes[new.get(end)];fx,fy=float(b[px]),float(b[py])
                    pts.append([box['x']+fx*box['w'],box['y']+fy*box['h']])
                middle=[[float(p.get('x')),float(p.get('y'))] for p in new.findall('mxGeometry/Array[@as="points"]/mxPoint')]
                route=[pts[0]]+middle+[pts[1]]
                lock={'points':route,'source':new.get('source'),'target':new.get('target'),'mode':'manual'}
                probe={'edges':[{'id':cid,'source':lock['source'],'target':lock['target']}],'lockedRoutes':{cid:lock}}
                errors=validate(probe)
                if errors:raise ValueError('; '.join(errors))
                locks[cid]=lock;summary['routes'].append(cid)
            except (ValueError,KeyError,TypeError) as exc:
                summary['ignored'].append(f'{cid}: route not preserved: {exc}')
        elif cid.startswith('__') and geometry(old)!=geometry(new):
            summary['ignored'].append(f'{cid}: manually moved/resized generated child is not preserved')
    if styles:model['presentation']=styles
    if locks:
        # Locks use the absolute drawing frame. Pin geometry to avoid an auto-canvas shift.
        shapes,_,_,_=pull.drawing(drawn)
        import model_layout
        model=pull.absolute(model,shapes,model_layout.normalize(model));model['lockedRoutes']=locks
        summary['layout']='absolute'
    errors=validate(model)
    if errors:summary['ignored'].extend(errors)
    return model


def reuse(m,previous,header_rect):
    """Retain valid old routes; report exactly which ones became ineligible."""
    import model_layout,cloud_routes as r
    model=copy.deepcopy(model_layout.normalize(m));old=previous.get('snapshot',{})
    oldnodes={n['id']:n for k in ('nodes','containers') for n in old.get(k,[])}
    nodes=r.endpoints(model);oldedges={e['id']:e for e in old.get('edges',[])}
    summary={'retained':[],'rerouted':[]};locks=model.setdefault('lockedRoutes',{})
    for e in sorted(model['edges'],key=lambda e:e['id']):
        eid=e['id']
        if eid in locks:continue
        pts=previous.get('routes',{}).get(eid)
        eligible=pts is not None and oldedges.get(eid)==e
        eligible=eligible and all(oldnodes.get(e[k])==nodes.get(e[k]) for k in ('source','target'))
        if eligible:
            obstacles=[r.pad(r.rect(n),0 if n['id'] in (e['source'],e['target']) else model.get('routing',{}).get('clearance',8)) for n in model['nodes']]
            obstacles += [r.pad(header_rect(b),4) for b in model['containers']]
            eligible=not any(r.hits(a,b,o) for a,b in zip(pts,pts[1:]) for o in obstacles)
        if eligible:
            locks[eid]={'points':pts,'source':e['source'],'target':e['target'],'mode':'retained'};summary['retained'].append(eid)
        else:summary['rerouted'].append(eid)
    return model,summary
