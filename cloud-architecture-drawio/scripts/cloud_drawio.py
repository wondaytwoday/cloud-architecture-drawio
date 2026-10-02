#!/usr/bin/env python3
"""Dependency-free, editable draw.io compiler. See references/model.md."""
import argparse
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import unicodedata
import urllib.parse
import xml.etree.ElementTree as ET
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cloud_routes
import model_layout
from model_validation import EDGE_KINDS, legend_captions, validate_structure

ROOT = Path(__file__).resolve().parents[1]
# Where `check` looks for a persistent renderer: node_modules/playwright and the viewer.
CACHE = Path(os.environ.get('CLOUD_DRAWIO_CACHE') or Path.home()/'.cache/cloud-architecture-drawio')
CAT = json.loads((ROOT / 'assets/icon-catalog.json').read_text(encoding='utf-8'))
KINDS = {'cloud', 'account', 'project', 'region', 'vpc', 'vnet', 'az', 'subnet', 'group'}
PALETTE = {
    'cloud': ('#FFFFFF', '#536477'), 'account': ('#FFFFFF', '#536477'),
    'project': ('#FFFFFF', '#536477'), 'region': ('#FFFFFF', '#8295A7'),
    'vpc': ('#FFFFFF', '#24823B'), 'vnet': ('#FFFFFF', '#0078D4'),
    'az': ('none', '#70A3C4'), 'subnet': ('#EFF6FB', '#C6DAE8'),
    'group': ('none', '#C87B28'),
}
# Color and dash pattern per relationship; each dashed kind has its own rhythm.
EDGE = {'traffic': ('#4B6074', None), 'dns': ('#8C6A2F', '2 3'),
        'association': ('#B85B72', '4 3'), 'replication': ('#875EAC', '10 4'),
        'egress': ('#1F7F8C', '6 3 2 3'), 'management': ('#A06050', '8 3 2 3 2 3'),
        'event': ('#D81B60', '7 2'), 'connectivity': ('#3E2723', None)}
# Network links have no direction and a heavier line; events use an open arrow.
EDGE_EXTRA = {'association': 'endArrow=none;', 'connectivity': 'endArrow=none;strokeWidth=2.6;',
              'event': 'endArrow=open;endFill=0;'}


def rect(item):
    return tuple(item[k] for k in ('x', 'y', 'w', 'h'))


def overlap(a, b):
    return a[0] < b[0]+b[2] and b[0] < a[0]+a[2] and a[1] < b[1]+b[3] and b[1] < a[1]+a[3]


def inside(a, b, margin=0):
    return a[0] >= b[0]+margin and a[1] >= b[1]+margin and a[0]+a[2] <= b[0]+b[2]-margin and a[1]+a[3] <= b[1]+b[3]-margin


def header_rect(b):
    # Only the title is an obstacle, not an imaginary wall across the network.
    units=sum(1 if unicodedata.east_asian_width(c) in 'WF' else .58 for c in b['label'])
    width=min(b['w']-12,units*14+26)
    align=b.get('labelAlign','left')
    x=b['x']+(b['w']-width)/2 if align=='center' else b['x']+b['w']-width-6 if align=='right' else b['x']+6
    return x+b.get('labelOffset',0),b['y']+2,width,30


def line_hits(a, b, r):
    x, y, w, h = r
    if a[0] == b[0]:
        return x < a[0] < x+w and max(min(a[1], b[1]), y) < min(max(a[1], b[1]), y+h)
    if a[1] == b[1]:
        return y < a[1] < y+h and max(min(a[0], b[0]), x) < min(max(a[0], b[0]), x+w)
    raise ValueError('Non-orthogonal segment')


def wrapped(text, width, font):
    """Conservative width estimate; browser inspection remains mandatory."""
    def measure(s): return sum(font*(1 if unicodedata.east_asian_width(c) in 'WF' else .58) for c in s)
    lines=[]
    for paragraph in text.split('\n'):
        line=''
        for word in paragraph.split():
            trial=(line+' '+word).strip()
            if measure(trial)<=width: line=trial; continue
            if line: lines.append(line); line=''
            for char in word:
                if measure(line+char)>width and line: lines.append(line); line=''
                line+=char
        lines.append(line)
    return lines


def validate(m):
    """Check the model after resolving layout shorthands such as 'fit' and grid cells."""
    try: m=model_layout.normalize(m)
    except (ValueError,TypeError) as e: return [f'layout: {e}'],[]
    return validate_structure(m, CAT, wrapped, header_rect)


def compress(s):
    c = zlib.compressobj(wbits=-15)
    return base64.b64encode(c.compress(urllib.parse.quote(s, safe="~()*!.'-").encode())+c.flush()).decode()


def icon_style(key):
    if key == 'generic.user':
        return 'shape=actor;fillColor=#EDF2F7;strokeColor=#536477;'
    if key == 'generic':
        return 'rounded=1;arcSize=15;fillColor=#EDF2F7;strokeColor=#536477;'
    i = CAT[key]; data = (ROOT/'assets'/i['file']).read_text(encoding='utf-8')
    if i['kind'] == 'svg':
        return 'shape=image;imageAspect=1;aspect=fixed;image=data:image/svg+xml,'+base64.b64encode(data.encode()).decode()+';'
    # Variable-aspect stencils (gcp2) would stretch to the square icon box.
    data=re.sub(r'(<shape\b[^>]*\baspect=")variable"',r'\1fixed"',data,count=1)
    # Inline original draw.io vector stencil so the file doesn't need an external library.
    return 'shape=stencil('+compress(data)+');fillColor='+i.get('color','#4285F4')+';strokeColor='+i.get('stroke','none')+';'


def report_path(target):
    return Path(target).with_suffix('.report.json')


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def check_overwrite(target):
    """Refuse to replace a .drawio that changed since this compiler wrote it."""
    target=Path(target)
    if not target.exists(): return
    report=report_path(target)
    if not report.exists():
        raise ValueError(f'{target}: exists without {report.name}, so it may be a manual draw.io file; patch it directly, or pass --force to replace it')
    try: saved=json.loads(report.read_text(encoding='utf-8'))
    except (ValueError,OSError): saved=None
    if not isinstance(saved,dict):
        raise ValueError(f'{target}: {report.name} is unreadable, so manual edits cannot be ruled out; patch the .drawio directly, or pass --force to replace it')
    recorded=saved.get('drawio_sha256')
    # Reports from version 2 carry no file hash; they predate this check.
    if recorded and recorded!=sha256(target.read_bytes()):
        raise ValueError(f'{target}: changed after it was built (its hash differs from {report.name}), probably by a manual draw.io edit; patch it directly, or pass --force to discard those edits')


def write_outputs(files):
    """Stage every file beside its target, then move all of them into place.

    Symlinks are written through and file modes kept. A read-only directory
    holding writable files falls back to writing those files in place.
    """
    staged=[]
    try:
        for path,data in files:
            path=Path(os.path.realpath(path)); tmp=path.with_name(path.name+'.tmp')
            try: tmp.write_bytes(data)
            except OSError as e:
                tmp.unlink(missing_ok=True)
                if isinstance(e,PermissionError) and path.is_file() and os.access(path,os.W_OK):
                    staged.append((path,None,data)); continue
                raise OSError(e.errno,e.strerror,str(path)) from e
            if path.is_file(): shutil.copymode(path,tmp)
            staged.append((path,tmp,data))
        for path,tmp,data in staged:
            try:
                if tmp: os.replace(tmp,path)
                else: path.write_bytes(data)
            except OSError as e: raise OSError(e.errno,e.strerror,str(path)) from e
    finally:
        for _,tmp,_ in staged:
            if tmp: tmp.unlink(missing_ok=True)


def build(m, target, force=False):
    errors,warnings=validate(m)
    if errors: raise ValueError('\n'.join(errors))
    if not force: check_overwrite(target)
    source,m=m,model_layout.normalize(m)
    width,height=m['width'],m['height']; by={i['id']:i for i in m['containers']+m['nodes']}
    rootfile=ET.Element('mxfile',host='cloud-architecture-drawio',version='1.0')
    dia=ET.SubElement(rootfile,'diagram',id='architecture',name=m.get('title','Architecture'))
    model=ET.SubElement(dia,'mxGraphModel',grid='1',gridSize='10',page='1',pageScale='1',pageWidth=str(width),pageHeight=str(height),background='#FFFFFF',connect='1',arrows='1')
    root=ET.SubElement(model,'root'); ET.SubElement(root,'mxCell',id='0'); ET.SubElement(root,'mxCell',id='1',parent='0')
    def cell(id,value,style,x,y,w,h,parent='1'):
        c=ET.SubElement(root,'mxCell',id=id,value=value,style=style+'fontFamily=Arial;'+('' if 'fontColor=' in style else 'fontColor=#20354A;'),vertex='1',parent=parent)
        ET.SubElement(c,'mxGeometry',x=str(x),y=str(y),width=str(w),height=str(h),attrib={'as':'geometry'})
        return c
    def text(id,value,x,y,w,h,size=13,align='center',parent='1',bold=False):
        # spacing=0 gives the label its whole cell, so two wrapped lines are not clipped.
        return cell(id,value,f'text;html=0;whiteSpace=wrap;overflow=hidden;spacing=0;align={align};verticalAlign=middle;fontSize={size};fontStyle={1 if bold else 0};',x,y,w,h,parent)
    text('__title',m.get('title','Cloud architecture'),30,12,width-60,34,24,'left',bold=True)
    text('__subtitle',m.get('subtitle',''),30,48,width-60,24,12,'left')
    remaining=list(m['containers']); emitted=set()
    while remaining:
        # A later-added AZ's opaque subnet must not cover a membership overlay.
        ready=[b for b in remaining if not b.get('parent') or b['parent'] in emitted]
        b=min(ready,key=lambda b:bool(b.get('overlay')))
        fill,stroke=PALETTE[b['kind']]
        if b.get('public'): fill='#EEF8EA'; stroke='#9FC991'
        if b.get('overlay'): fill='none'
        parent=b.get('parent','1'); p=by.get(parent,{'x':0,'y':0})
        style=f'rounded=0;whiteSpace=wrap;html=0;align={b.get("labelAlign","left")};verticalAlign=top;spacingTop=8;spacingLeft={12+b.get("labelOffset",0)};fontSize=14;fontStyle=1;fillColor={fill};strokeColor={stroke};strokeWidth=1.5;container=1;collapsible=0;recursiveResize=0;'
        if b['kind'] in ('az','group','region'): style+='dashed=1;dashPattern=5 4;'
        cell(b['id'],b['label'],style,b['x']-p['x'],b['y']-p['y'],b['w'],b['h'],parent)
        remaining.remove(b); emitted.add(b['id'])
    routes,ports,labels,mode=cloud_routes.route_and_label(m,header_rect)
    quality=cloud_routes.metrics(routes)
    # Plain boxes stand in for products without a catalog icon; disclose them.
    fallbacks=[n['id'] for n in m['nodes'] if n.get('icon','generic')=='generic']
    report={'version':3,'errors':[], 'warnings':warnings,'routing':mode,'fallbackIcons':fallbacks,'routes':routes,'labels':labels,'quality':quality,'model_sha256':sha256(json.dumps(source,sort_keys=True).encode())}
    if quality['crossingCount']:
        report['warnings'].append(f"{quality['crossingCount']} connector crossings: inspect jump markers or revise ports/lanes")
    for join in quality['continuations']:
        report['warnings'].append(f"connectors {join['edges'][0]} and {join['edges'][1]} meet end to end on one line with a {join['gap']:g}px gap and may read as one; change a port or offset")
    for e in m['edges']:
        pts=routes[e['id']]
        color,dashes=EDGE[e.get('kind','traffic')]
        sa,fa=ports[(e['id'],'source')];sb,fb=ports[(e['id'],'target')]
        def fraction(side,f): return {'top':(f,0),'bottom':(f,1),'left':(0,f),'right':(1,f)}[side]
        ex,ey=fraction(sa,fa);ix,iy=fraction(sb,fb)
        style=f'edgeStyle=none;rounded=0;html=0;endArrow=block;endFill=1;strokeColor={color};strokeWidth=1.6;exitX={ex};exitY={ey};exitPerimeter=0;entryX={ix};entryY={iy};entryPerimeter=0;jumpStyle=arc;jumpSize=8;'
        if dashes: style+=f'dashed=1;dashPattern={dashes};'
        style+=EDGE_EXTRA.get(e.get('kind','traffic'),'')
        c=ET.SubElement(root,'mxCell',id=e['id'],style=style,edge='1',parent='1',source=e['source'],target=e['target'])
        geo=ET.SubElement(c,'mxGeometry',relative='1',attrib={'as':'geometry'})
        arr=ET.SubElement(geo,'Array',attrib={'as':'points'})
        for x,y in pts[1:-1]: ET.SubElement(arr,'mxPoint',x=str(x),y=str(y))
        if e['id'] in labels:
            label=labels[e['id']];x,y,w,h=label['rect']
            child=cell('__label_'+e['id'],e['label'],'text;html=0;whiteSpace=wrap;align=center;verticalAlign=middle;fontSize=11;fillColor=#FFFFFF;strokeColor=none;',label['relativeX'],0,w,h,e['id'])
            child.set('connectable','0')
            geom=child.find('mxGeometry');geom.set('relative','1')
            ET.SubElement(geom,'mxPoint',x=str(label['offset'][0]),y=str(label['offset'][1]),attrib={'as':'offset'})
    for n in m['nodes']:
        parent=n.get('parent','1'); p=by.get(parent,{'x':0,'y':0})
        cell(n['id'],'','group;fillColor=none;strokeColor=none;container=1;collapsible=0;',n['x']-p['x'],n['y']-p['y'],n['w'],n['h'],parent)
        cell('__icon_'+n['id'],'',icon_style(n.get('icon','generic')),(n['w']-48)/2,6,48,48,n['id'])
        text('__name_'+n['id'],'\n'.join(wrapped(n.get('label',''),n['w']-8,13)),4,59,n['w']-8,34,13,parent=n['id'],bold=True)
        text('__detail_'+n['id'],'\n'.join(wrapped(n.get('detail',''),n['w']-8,11)),4,95,n['w']-8,28,11,parent=n['id'])
    # Legend and assumptions are deliberately outside network boundaries.
    y=height-72
    used={e.get('kind','traffic') for e in m['edges']}; kinds=[k for k in EDGE_KINDS if k in used]
    captions=legend_captions(m)
    for j,k in enumerate(kinds):
        color,dashes=EDGE[k]; lx=30+j*205
        dash=f'dashed=1;dashPattern={dashes};' if dashes else 'dashed=0;'
        stroke=2.6 if k=='connectivity' else 1.6
        cell('__legend_line_'+k,'',f'shape=line;strokeColor={color};strokeWidth={stroke};{dash}',lx,y+12,30,1)
        cell('__legend_text_'+k,captions[k],f'text;html=0;whiteSpace=wrap;overflow=hidden;spacing=0;fontSize=11;align=left;verticalAlign=middle;fontColor={color};',lx+40,y,160,24)
    text('__notes',' · '.join(m.get('notes',[])),30,y+25,width-60,36,11,'left')
    target=Path(target); target.parent.mkdir(parents=True,exist_ok=True)
    ET.indent(rootfile)
    xml=ET.tostring(rootfile,encoding='utf-8',xml_declaration=True)+b'\n'
    report['drawio_sha256']=sha256(xml)
    write_outputs([(target,xml),(report_path(target),(json.dumps(report,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))])
    return report


def emit(value, **options):
    """Print JSON readably when stdout can encode it, otherwise ASCII-escaped."""
    text=json.dumps(value,ensure_ascii=False,**options)
    try: text.encode(sys.stdout.encoding or 'utf-8')
    except (UnicodeEncodeError,LookupError): text=json.dumps(value,ensure_ascii=True,**options)
    print(text)


# Resolves modules from the scripts folder, as render.cjs does, and checks that
# Playwright's browser is actually installed.
RENDERER_PROBE = """
let p; try { p = require('playwright'); } catch (e) { console.error('playwright is not installed for node'); process.exit(1); }
const exe = process.env.CHROME_PATH || p.chromium.executablePath();
if (!require('fs').existsSync(exe)) { console.error('the Playwright browser is not installed (' + exe + ')'); process.exit(1); }
"""


def find_renderer(viewer=None):
    """Return (node, viewer, environment) for render.cjs, or (None, reason)."""
    node=shutil.which('node')
    if not node: return None,'node is not installed'
    viewer=viewer or os.environ.get('DRAWIO_VIEWER') or str(CACHE/'viewer-static.min.js')
    if not Path(viewer).is_file(): return None,f'draw.io viewer bundle not found at {viewer}'
    env=dict(os.environ)
    env['NODE_PATH']=os.pathsep.join(p for p in (env.get('NODE_PATH'),str(CACHE/'node_modules')) if p)
    probe=subprocess.run([node,'-e',RENDERER_PROBE],cwd=ROOT/'scripts',env=env,capture_output=True,text=True)
    if probe.returncode: return None,(probe.stderr.strip().splitlines() or ['the renderer could not start'])[0]
    return (node,viewer,env),None


def check(m, output, force=False, viewer=None):
    """Validate, build and render-verify in one step. Returns (verdict, exit code).

    Exit 0 means every automated check passed (visual review still applies), 1 a
    failure, 2 a successful build that could not be render-verified here.
    """
    if Path(output).suffix.lower() in ('.png','.svg','.json'):
        return {'ok':False,'stage':'build','errors':[f'{output}: name the .drawio source here; the PNG, SVG and reports are written beside it']},1
    errors,warnings=validate(m)
    if errors: return {'ok':False,'stage':'validate','errors':errors,'warnings':warnings},1
    try: report=build(m,output,force)
    except ValueError as e: return {'ok':False,'stage':'build','errors':str(e).splitlines(),'warnings':warnings},1
    verdict={'output':str(output),'routing':report['routing'],'warnings':report['warnings'],'fallbackIcons':report['fallbackIcons'],
             'quality':{k:report['quality'][k] for k in ('crossingCount','overlapLength','bendCount','totalLength')}}
    unavailable=lambda reason:({**verdict,'ok':False,'stage':'render','rendered':False,
        'reason':f'{reason}; install the renderer as in references/rendering.md, or report visual verification as not completed'},2)
    found,reason=find_renderer(viewer)
    if not found: return unavailable(reason)
    node,viewer,env=found;png=Path(output).with_suffix('.png')
    done=subprocess.run([node,str(ROOT/'scripts/render.cjs'),str(output),str(png),viewer],env=env,capture_output=True,text=True)
    lines=[line for line in done.stderr.splitlines() if line.strip()]
    if done.returncode==3: return unavailable(lines[0] if lines else 'the browser could not be launched')
    try: rendered=json.loads(done.stdout)
    except ValueError: rendered=None
    verdict.update(stage='render',rendered=rendered is not None,png=str(png))
    if rendered is None:
        return {**verdict,'ok':False,'errors':lines[:3] or ['renderer failed']},1
    problems={k:rendered[k] for k in ('unknownIcons','offPage','brokenImages','textOverflow','pageErrors') if rendered.get(k)}
    if rendered['geometry']['mismatches']: problems['mismatches']=rendered['geometry']['mismatches']
    if rendered['editability'].get('error'): problems['editability']=rendered['editability']['error']
    verdict.update(ok=done.returncode==0 and not problems,problems=problems,warnings=verdict['warnings']+rendered.get('warnings',[]),
                   jumpMarkers=rendered['geometry']['jumpMarkers'])
    return verdict,(0 if verdict['ok'] else 1)


def main():
    p=argparse.ArgumentParser(description=__doc__); sub=p.add_subparsers(dest='cmd',required=True)
    for command in ('build','validate','check','normalize'):
        s=sub.add_parser(command); s.add_argument('model');
        if command in ('build','check'):
            s.add_argument('output')
            s.add_argument('--force',action='store_true',help='replace an output that changed after it was built')
        if command=='check':
            s.add_argument('--viewer',help='draw.io viewer-static.min.js (default: $DRAWIO_VIEWER, then the cache)')
    sub.add_parser('icons')
    a=p.parse_args()
    try:
        if a.cmd=='icons': print('\n'.join(sorted(CAT))); return
        m=json.loads(Path(a.model).read_text(encoding='utf-8-sig'))
        if a.cmd=='normalize':
            emit(model_layout.normalize(m),indent=2); return
        if a.cmd=='validate':
            errors,warnings=validate(m); emit({'errors':errors,'warnings':warnings},indent=2); sys.exit(bool(errors))
        if a.cmd=='check':
            verdict,code=check(m,a.output,a.force,a.viewer); emit(verdict,indent=2); sys.exit(code)
        report=build(m,a.output,a.force); emit({'output':a.output,'warnings':report['warnings']})
    except OSError as e:
        where=e.filename or (a.output if a.cmd in ('build','check') else getattr(a,'model',''))
        p.exit(1,f'{where}: {e.strerror or e}\n')
    except (ValueError,KeyError,TypeError) as e: p.exit(1,str(e)+'\n')


if __name__=='__main__': main()
