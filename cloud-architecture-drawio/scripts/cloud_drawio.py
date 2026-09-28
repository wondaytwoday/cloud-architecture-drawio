#!/usr/bin/env python3
"""Dependency-free, editable draw.io compiler. See references/model.md."""
import argparse
import base64
import hashlib
import json
import math
from pathlib import Path
import sys
import unicodedata
import urllib.parse
import xml.etree.ElementTree as ET
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cloud_routes
from model_validation import validate_structure

ROOT = Path(__file__).resolve().parents[1]
CAT = json.loads((ROOT / 'assets/icon-catalog.json').read_text())
KINDS = {'cloud', 'account', 'project', 'region', 'vpc', 'vnet', 'az', 'subnet', 'group'}
PALETTE = {
    'cloud': ('#FFFFFF', '#536477'), 'account': ('#FFFFFF', '#536477'),
    'project': ('#FFFFFF', '#536477'), 'region': ('#FFFFFF', '#8295A7'),
    'vpc': ('#FFFFFF', '#24823B'), 'vnet': ('#FFFFFF', '#0078D4'),
    'az': ('none', '#70A3C4'), 'subnet': ('#EFF6FB', '#C6DAE8'),
    'group': ('none', '#C87B28'),
}
EDGE = {'traffic': ('#4B6074', False), 'dns': ('#77728E', True),
        'association': ('#B85B72', True), 'replication': ('#875EAC', True),
        'egress': ('#537D80', True), 'management': ('#79828B', True)}


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
    return validate_structure(m, CAT, wrapped, header_rect)


def compress(s):
    c = zlib.compressobj(wbits=-15)
    return base64.b64encode(c.compress(urllib.parse.quote(s, safe="~()*!.'-").encode())+c.flush()).decode()


def icon_style(key):
    if key == 'generic.user':
        return 'shape=actor;fillColor=#EDF2F7;strokeColor=#536477;'
    if key == 'generic':
        return 'rounded=1;arcSize=15;fillColor=#EDF2F7;strokeColor=#536477;'
    i = CAT[key]; data = (ROOT/'assets'/i['file']).read_text()
    if i['kind'] == 'svg':
        return 'shape=image;imageAspect=1;aspect=fixed;image=data:image/svg+xml,'+base64.b64encode(data.encode()).decode()+';'
    # Inline original draw.io vector stencil so the file doesn't need an external library.
    return 'shape=stencil('+compress(data)+');fillColor='+i.get('color','#4285F4')+';strokeColor=none;'


def build(m, target):
    errors,warnings=validate(m)
    if errors: raise ValueError('\n'.join(errors))
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
        return cell(id,value,f'text;html=0;whiteSpace=wrap;overflow=hidden;align={align};verticalAlign=middle;fontSize={size};fontStyle={1 if bold else 0};',x,y,w,h,parent)
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
    routes,ports=cloud_routes.plan(m,header_rect)
    labels=cloud_routes.place_labels(m,routes,header_rect)
    quality=cloud_routes.metrics(routes)
    report={'version':2,'errors':[], 'warnings':warnings,'routes':routes,'labels':labels,'quality':quality,'model_sha256':hashlib.sha256(json.dumps(m,sort_keys=True).encode()).hexdigest()}
    if quality['crossingCount']:
        report['warnings'].append(f"{quality['crossingCount']} connector crossings: inspect jump markers or revise ports/lanes")
    for e in m['edges']:
        pts=routes[e['id']]
        color,dashed=EDGE[e.get('kind','traffic')]
        sa,fa=ports[(e['id'],'source')];sb,fb=ports[(e['id'],'target')]
        def fraction(side,f): return {'top':(f,0),'bottom':(f,1),'left':(0,f),'right':(1,f)}[side]
        ex,ey=fraction(sa,fa);ix,iy=fraction(sb,fb)
        style=f'edgeStyle=none;rounded=0;html=0;endArrow=block;endFill=1;strokeColor={color};strokeWidth=1.6;exitX={ex};exitY={ey};exitPerimeter=0;entryX={ix};entryY={iy};entryPerimeter=0;jumpStyle=arc;jumpSize=8;'
        if dashed: style+='dashed=1;dashPattern=5 4;'
        if e.get('kind')=='association': style+='endArrow=none;'
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
    kinds=list(dict.fromkeys(e.get('kind','traffic') for e in m['edges']))
    legend_names={'traffic':'Request / data','dns':'DNS resolution','association':'Policy association','replication':'Replication','egress':'Outbound','management':'Management'}
    for j,k in enumerate(kinds):
        color,dashed=EDGE[k]; lx=30+j*205
        cell('__legend_line_'+k,'',f'shape=line;strokeColor={color};strokeWidth=1.6;dashed={int(dashed)};',lx,y+12,30,1)
        cell('__legend_text_'+k,legend_names[k],f'text;html=0;fontSize=11;align=left;verticalAlign=middle;fontColor={color};',lx+40,y,160,24)
    text('__notes',' · '.join(m.get('notes',[])),30,y+25,width-60,36,11,'left')
    target=Path(target); target.parent.mkdir(parents=True,exist_ok=True)
    ET.indent(rootfile)
    ET.ElementTree(rootfile).write(target,encoding='utf-8',xml_declaration=True)
    target.with_suffix('.report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__); sub=p.add_subparsers(dest='cmd',required=True)
    for command in ('build','validate'):
        s=sub.add_parser(command); s.add_argument('model');
        if command=='build': s.add_argument('output')
    sub.add_parser('icons')
    a=p.parse_args()
    try:
        if a.cmd=='icons': print('\n'.join(sorted(CAT))); return
        m=json.loads(Path(a.model).read_text())
        if a.cmd=='validate':
            errors,warnings=validate(m); print(json.dumps({'errors':errors,'warnings':warnings},ensure_ascii=False,indent=2)); sys.exit(bool(errors))
        report=build(m,a.output); print(json.dumps({'output':a.output,'warnings':report['warnings']},ensure_ascii=False))
    except (ValueError,KeyError,TypeError) as e: p.exit(1,str(e)+'\n')


if __name__=='__main__': main()
