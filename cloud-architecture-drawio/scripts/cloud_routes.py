"""Deterministic orthogonal routing, global label placement and geometric QA."""
from collections import defaultdict
from functools import lru_cache
import heapq
import math
import unicodedata

SIDES={'right':(1,0),'left':(-1,0),'bottom':(0,1),'top':(0,-1)}


def rect(n): return tuple(n[k] for k in ('x','y','w','h'))
def pad(r,n): return r[0]-n,r[1]-n,r[2]+2*n,r[3]+2*n
def length(a,b): return abs(a[0]-b[0])+abs(a[1]-b[1])
def overlap(a,b): return a[0]<b[0]+b[2] and b[0]<a[0]+a[2] and a[1]<b[1]+b[3] and b[1]<a[1]+a[3]


def hits(a,b,r):
    x,y,w,h=r
    if a[0]==b[0]: return x<a[0]<x+w and max(min(a[1],b[1]),y)<min(max(a[1],b[1]),y+h)
    if a[1]==b[1]: return y<a[1]<y+h and max(min(a[0],b[0]),x)<min(max(a[0],b[0]),x+w)
    raise ValueError('Non-orthogonal segment')


def simplify(points):
    out=[]
    for p in points:
        p=tuple(p)
        if out and p==out[-1]: continue
        if len(out)>1 and ((out[-2][0]==out[-1][0]==p[0]) or (out[-2][1]==out[-1][1]==p[1])): out.pop()
        out.append(p)
    return out


def relation(a,b,c,d):
    """Return collinear overlap length and perpendicular intersection (including T contacts)."""
    ah=a[1]==b[1]; ch=c[1]==d[1]
    if ah==ch:
        if (a[1] if ah else a[0])!=(c[1] if ch else c[0]): return 0,None
        axis=0 if ah else 1
        return max(0,min(max(a[axis],b[axis]),max(c[axis],d[axis]))-max(min(a[axis],b[axis]),min(c[axis],d[axis]))),None
    if not ah: return relation(c,d,a,b)
    p=(c[0],a[1])
    if min(a[0],b[0])<=p[0]<=max(a[0],b[0]) and min(c[1],d[1])<=p[1]<=max(c[1],d[1]): return 0,p
    return 0,None


def metrics(routes):
    crossings=[]; overlaps=[]; bends=0; total=0
    items=list(routes.items())
    for i,(aid,ap) in enumerate(items):
        bends+=max(0,len(ap)-2);total+=sum(length(a,b) for a,b in zip(ap,ap[1:]))
        for bid,bp in items[i+1:]:
            points=set(); shared=0
            for a,b in zip(ap,ap[1:]):
                for c,d in zip(bp,bp[1:]):
                    amount,point=relation(a,b,c,d);shared+=amount
                    if point and not(point in (tuple(ap[0]),tuple(ap[-1])) and point in (tuple(bp[0]),tuple(bp[-1]))):points.add(point)
            if shared:overlaps.append({'edges':[aid,bid],'length':round(shared,2)})
            for p in sorted(points):crossings.append({'edges':[aid,bid],'point':p})
    return {'crossingCount':len(crossings),'overlapLength':round(sum(v['length'] for v in overlaps),2),'bendCount':bends,'totalLength':round(total,2),'crossings':crossings,'overlaps':overlaps}


def anchor(node,side,fraction):
    x,y,w,h=rect(node)
    return {'top':(x+w*fraction,y),'bottom':(x+w*fraction,y+h),'left':(x,y+h*fraction),'right':(x+w,y+h*fraction)}[side]


def select_ports(m):
    nodes={n['id']:n for n in m['nodes']}; ports={}; groups=defaultdict(list)
    for e in m['edges']:
        a,b=nodes[e['source']],nodes[e['target']]
        dx=(b['x']+b['w']/2)-(a['x']+a['w']/2);dy=(b['y']+b['h']/2)-(a['y']+a['h']/2)
        sa,sb=(('right','left') if dx>=0 else ('left','right')) if abs(dx)>abs(dy) else (('bottom','top') if dy>=0 else ('top','bottom'))
        for end,default,other in [('source',sa,b),('target',sb,a)]:
            side=e.get(end+'Port',default)
            if side=='auto':side=default
            ports[(e['id'],end)]=[side,None]
            other_end='target' if end=='source' else 'source'
            other_side=e.get(other_end+'Port',sb if end=='source' else sa)
            if other_side=='auto':other_side=sb if end=='source' else sa
            other_point=anchor(other,other_side,e.get(other_end+'Offset',.5))
            order=other_point[0] if side in ('top','bottom') else other_point[1]
            tie=-other_point[0] if side=='right' else other_point[0] if side=='left' else -other_point[1] if side=='bottom' else other_point[1]
            if end=='target':tie=-tie
            groups[(e[end],side)].append((order,tie,e['id'],end,e.get(end+'Offset')))
    for (nid,side),entries in groups.items():
        entries.sort();count=len(entries);n=nodes[nid];size=n['w'] if side in ('top','bottom') else n['h']
        spacing=min(20,.6*size/max(1,count-1))
        reserved=[entry[4] for entry in entries if entry[4] is not None]
        if len(set(reserved))!=len(reserved):
            raise ValueError(f'{nid} {side}: explicit port offsets coincide; choose distinct offsets')
        gap=min(10/size,.8/(count+1))
        for j,(_,_,eid,end,explicit) in enumerate(entries):
            fraction=explicit
            if fraction is None:
                preferred=.5+(j-(count-1)/2)*spacing/size
                candidates={preferred,.1,.9}
                candidates.update(preferred+direction*k*gap for direction in (-1,1) for k in range(1,count+2))
                candidates.update(value+direction*gap for value in reserved for direction in (-1,1))
                available=[f for f in candidates if .1<=f<=.9 and all(abs(f-r)>=gap-1e-9 for r in reserved)]
                if not available:
                    raise ValueError(f'{nid} {side}: too many connections for clear ports; enlarge card or use another side')
                fraction=min(available,key=lambda f:(abs(f-preferred),f))
                reserved.append(fraction)
            ports[(eid,end)][1]=fraction
    return ports


def solve(start,goal,sa,sb,obstacles,width,height,segments,clearance=8,stub=16):
    """Directed lead-ins, obstacle padding, exact overlap rejection and crossing cost."""
    vx,vy=SIDES[sa];wx,wy=SIDES[sb]
    begin=(start[0]+vx*stub,start[1]+vy*stub);end=(goal[0]+wx*stub,goal[1]+wy*stub)
    for a,b in [(start,begin),(end,goal)]:
        if any(hits(a,b,r) for r in obstacles):raise ValueError('Connector lead-in intersects a card or title; increase gap or choose another port')
        if any(relation(a,b,c,d)[0]>0 for c,d in segments):raise ValueError('Connector lead-ins overlap; use distinct port offsets')
    # Event-based grid includes obstacle boundaries, not every pixel of a huge canvas.
    xs={10,width-10,begin[0],end[0]};ys={80,height-90,begin[1],end[1]}
    for x,y,w,h in obstacles:
        xs.update((x-10,x,x+w,x+w+10));ys.update((y-10,y,y+h,y+h+10))
    for a,b in segments:
        xs.update((a[0]-10,a[0],a[0]+10,b[0]-10,b[0],b[0]+10))
        ys.update((a[1]-10,a[1],a[1]+10,b[1]-10,b[1],b[1]+10))
    xs=sorted(x for x in xs if 10<=x<=width-10 and (x in (begin[0],end[0]) or all(abs(x-v)>=10 for v in (begin[0],end[0]))))
    ys=sorted(y for y in ys if 80<=y<=height-90 and (y in (begin[1],end[1]) or all(abs(y-v)>=10 for v in (begin[1],end[1]))))
    if begin[0] not in xs or end[0] not in xs or begin[1] not in ys or end[1] not in ys:raise ValueError('Connector enters title/footer margin')
    sx,sy=xs.index(begin[0]),ys.index(begin[1]);gx,gy=xs.index(end[0]),ys.index(end[1])
    dirs=list(SIDES.values());first=dirs.index((vx,vy));last=dirs.index((-wx,-wy))
    initial=(sx,sy,first);costs={initial:0};parents={};heap=[(length(begin,end),0,*initial)];finish=None
    @lru_cache(None)
    def penalty(x,y,nx,ny):
        p,q=(xs[x],ys[y]),(xs[nx],ys[ny])
        if any(hits(p,q,r) for r in obstacles):return None
        cost=0;cross=set()
        for a,b in segments:
            amount,point=relation(p,q,a,b)
            if amount>0:return None
            if point in (a,b):return None
            if point:cross.add(point)
            # Prefer visible separation between parallel lines.
            if p[1]==q[1]==a[1]==b[1]:continue
            if p[1]==q[1] and a[1]==b[1] and abs(p[1]-a[1])<10:
                if max(min(p[0],q[0]),min(a[0],b[0]))<min(max(p[0],q[0]),max(a[0],b[0])):cost+=length(p,q)*3
            if p[0]==q[0] and a[0]==b[0] and 0<abs(p[0]-a[0])<10:
                if max(min(p[1],q[1]),min(a[1],b[1]))<min(max(p[1],q[1]),max(a[1],b[1])):cost+=length(p,q)*3
        return cost+len(cross)*180
    while heap:
        _,cost,x,y,d=heapq.heappop(heap);state=(x,y,d)
        if cost!=costs[state]:continue
        if (x,y)==(gx,gy):finish=state;break
        for nd,(dx,dy) in enumerate(dirs):
            if dirs[nd]==(-dirs[d][0],-dirs[d][1]):continue
            nx,ny=x+dx,y+dy
            if not(0<=nx<len(xs) and 0<=ny<len(ys)):continue
            extra=penalty(x,y,nx,ny)
            if extra is None:continue
            if (nx,ny)==(gx,gy) and dirs[nd]==(wx,wy):continue
            new=cost+length((xs[x],ys[y]),(xs[nx],ys[ny]))+extra+(26 if nd!=d else 0)
            if (nx,ny)==(gx,gy) and nd!=last:new+=26
            ns=(nx,ny,nd)
            if new<costs.get(ns,math.inf):
                costs[ns]=new;parents[ns]=state;heapq.heappush(heap,(new+length((xs[nx],ys[ny]),end),new,*ns))
    if finish is None:raise ValueError('No route with separate lines; widen lanes, change ports, or split the view')
    points=[];cur=finish
    while cur in parents:points.append((xs[cur[0]],ys[cur[1]]));cur=parents[cur]
    points.append(begin);points.reverse()
    return simplify([start]+points+[goal])


def plan(m,header_rect):
    nodes={n['id']:n for n in m['nodes']};ports=select_ports(m);routes={};segments=[]
    clearance=m.get('routing',{}).get('clearance',8);stub=m.get('routing',{}).get('stub',16)
    # Main traffic first, then secondary semantics; stable IDs make input order irrelevant.
    rank={'traffic':0,'egress':1,'replication':2,'dns':3,'association':4,'management':5}
    def order(e):
        a,b=nodes[e['source']],nodes[e['target']]
        distance=length((a['x']+a['w']/2,a['y']+a['h']/2),(b['x']+b['w']/2,b['y']+b['h']/2))
        return e.get('priority',rank[e.get('kind','traffic')]),distance,e['id']
    ordered=sorted(m['edges'],key=order)
    for e in ordered:
        a,b=nodes[e['source']],nodes[e['target']]
        sa,fa=ports[(e['id'],'source')];sb,fb=ports[(e['id'],'target')]
        obstacles=[pad(rect(n),0 if n['id'] in (a['id'],b['id']) else clearance) for n in m['nodes']]
        obstacles += [pad(header_rect(c),4) for c in m['containers']]
        start,goal=anchor(a,sa,fa),anchor(b,sb,fb)
        try:pts=solve(start,goal,sa,sb,obstacles,m['width'],m['height'],segments,clearance,stub)
        except ValueError as exc:raise ValueError(f"{e['id']}: {exc}") from exc
        routes[e['id']]=pts;segments.extend(zip(pts,pts[1:]))
    return routes,ports


def place_labels(m,routes,header_rect):
    obstacles=[pad(rect(n),4) for n in m['nodes']]+[pad(header_rect(b),4) for b in m['containers']]
    labels={};segments=[(eid,a,b) for eid,pts in routes.items() for a,b in zip(pts,pts[1:])]
    by={e['id']:e for e in m['edges']}
    for eid in sorted(routes,key=lambda k:(-len(by[k].get('label','')),k)):
        e=by[eid];label=e.get('label')
        if not label:continue
        units=sum(1 if unicodedata.east_asian_width(c) in 'WF' else .58 for c in label)
        lw=max(44,units*11+16);lh=22;pts=routes[eid];total=sum(length(a,b) for a,b in zip(pts,pts[1:]));before=0;candidates=[]
        for a,b in zip(pts,pts[1:]):
            seglen=length(a,b)
            if seglen<24:before+=seglen;continue
            for f in (.5,.4,.6,.3,.7,.2,.8):
                cx=a[0]+(b[0]-a[0])*f;cy=a[1]+(b[1]-a[1])*f
                offsets=[(-lw/2,-lh-5),(-lw/2,5)] if a[1]==b[1] else [(6,-lh/2),(-lw-6,-lh/2)]
                for dx,dy in offsets:
                    r=(cx+dx,cy+dy,lw,lh)
                    if r[0]<12 or r[1]<80 or r[0]+lw>m['width']-12 or r[1]+lh>m['height']-88:continue
                    if any(overlap(r,o) for o in obstacles):continue
                    if any(hits(u,v,pad(r,3)) for _,u,v in segments):continue
                    # Avoid captions covering container boundary lines.
                    if any(hits(u,v,pad(r,2)) for c in m['containers'] for u,v in [((c['x'],c['y']),(c['x']+c['w'],c['y'])),((c['x'],c['y']+c['h']),(c['x']+c['w'],c['y']+c['h'])),((c['x'],c['y']),(c['x'],c['y']+c['h'])),((c['x']+c['w'],c['y']),(c['x']+c['w'],c['y']+c['h']))]):continue
                    score=abs((before+seglen*f)/total-.5)*30+(0 if a[1]==b[1] else 5)
                    candidates.append((score,r,(before+seglen*f)/total*2-1,(cx,cy)))
            before+=seglen
        if not candidates:raise ValueError(f'{eid}: no clear label position for {label!r}; enlarge a lane or shorten the label')
        _,r,along,point=min(candidates,key=lambda v:v[0]);labels[eid]={'rect':r,'relativeX':along,'offset':(r[0]-point[0],r[1]-point[1])};obstacles.append(pad(r,4))
    return labels
