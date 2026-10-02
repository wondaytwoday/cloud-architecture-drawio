"""Deterministic orthogonal routing, global label placement and geometric QA."""
from bisect import bisect_left, bisect_right
from collections import defaultdict
from functools import lru_cache
import heapq
import math
import unicodedata

from model_validation import EDGE_KINDS, ENDPOINT_KINDS, MARGIN_BOTTOM, MARGIN_SIDE, MARGIN_TOP

SIDES={'right':(1,0),'left':(-1,0),'bottom':(0,1),'top':(0,-1)}


def rect(n): return tuple(n[k] for k in ('x','y','w','h'))


def endpoints(m):
    """Shapes a connector may attach to, by ID: nodes and network boundaries."""
    shapes={c['id']:c for c in m.get('containers',[]) if c['kind'] in ENDPOINT_KINDS and not c.get('overlay')}
    shapes.update({n['id']:n for n in m['nodes']})
    return shapes
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


def self_contact(points):
    """Collinear length and contact points where one route meets itself again."""
    segs=list(zip(points,points[1:]));shared=0;contacts=set()
    for i,(a,b) in enumerate(segs):
        for c,d in segs[i+2:]:
            amount,point=relation(a,b,c,d);shared+=amount
            if point:contacts.add(point)
    return shared,sorted(contacts)


def continuation(a,b,c,d):
    """Gap between two segments on one line, or None when they are not collinear."""
    if a[1]==b[1]==c[1]==d[1]:axis=0
    elif a[0]==b[0]==c[0]==d[0]:axis=1
    else:return None
    return max(min(a[axis],b[axis]),min(c[axis],d[axis]))-min(max(a[axis],b[axis]),max(c[axis],d[axis]))


def metrics(routes):
    crossings=[]; overlaps=[]; joins=[]; bends=0; total=0
    items=list(routes.items())
    for i,(aid,ap) in enumerate(items):
        bends+=max(0,len(ap)-2);total+=sum(length(a,b) for a,b in zip(ap,ap[1:]))
        shared,contacts=self_contact(ap)
        if shared:overlaps.append({'edges':[aid,aid],'length':round(shared,2)})
        for p in contacts:crossings.append({'edges':[aid,aid],'point':p})
        for bid,bp in items[i+1:]:
            points=set(); shared=0
            for a,b in zip(ap,ap[1:]):
                for c,d in zip(bp,bp[1:]):
                    amount,point=relation(a,b,c,d);shared+=amount
                    if point and not(point in (tuple(ap[0]),tuple(ap[-1])) and point in (tuple(bp[0]),tuple(bp[-1]))):points.add(point)
            if shared:overlaps.append({'edges':[aid,bid],'length':round(shared,2)})
            for p in sorted(points):crossings.append({'edges':[aid,bid],'point':p})
            # End-to-end on one line with a short gap, two connectors read as one.
            for a,b in zip(ap,ap[1:]):
                for c,d in zip(bp,bp[1:]):
                    gap=continuation(a,b,c,d)
                    if gap is not None and 0<gap<CONTINUATION_GAP:
                        joins.append({'edges':[aid,bid],'gap':round(gap,2),'line':[list(a),list(b),list(c),list(d)]})
    return {'crossingCount':len(crossings),'overlapLength':round(sum(v['length'] for v in overlaps),2),'bendCount':bends,'totalLength':round(total,2),
            'continuationCount':len(joins),'crossings':crossings,'overlaps':overlaps,'continuations':joins}


def anchor(node,side,fraction):
    x,y,w,h=rect(node)
    return {'top':(x+w*fraction,y),'bottom':(x+w*fraction,y+h),'left':(x,y+h*fraction),'right':(x+w,y+h*fraction)}[side]


def select_ports(m):
    nodes=endpoints(m); ports={}; groups=defaultdict(list)
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
        # Explicit offsets follow the spacing that automatic ports keep.
        ordered=sorted(reserved)
        for low,high in zip(ordered,ordered[1:]):
            if high-low<gap-1e-9:
                raise ValueError(f'{nid} {side}: explicit port offsets {low} and {high} are {(high-low)*size:.1f}px apart, which reads as one line; keep them at least {gap*size:.0f}px apart')
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


BORDER_GAP=8
BORDER_LANE=10
BORDER_FACTOR=3
PARALLEL_H=40
PARALLEL_V=60
PARALLEL_FACTOR=.3
# Captions prefer this much space from connectors other than their own.
CAPTION_GAP=8
# Collinear lines of different connectors closer end to end than this look joined.
CONTINUATION_GAP=24
# Search steps (A* expansions) all routing modes may use together.
ROUTING_WORK_LIMIT=1_500_000


def solve(start,goal,sa,sb,obstacles,width,height,segments,clearance=8,stub=16,pending=(),borders=(),spread=True,names=None,owners=None,stub_lanes=True,work=None,joins=False):
    """Directed lead-ins, obstacle padding, exact overlap rejection and crossing cost."""
    vx,vy=SIDES[sa];wx,wy=SIDES[sb]
    begin=(start[0]+vx*stub,start[1]+vy*stub);end=(goal[0]+wx*stub,goal[1]+wy*stub)
    # Lead-ins that overlap or cross each other force a route back over itself.
    shared,touch=relation(start,begin,end,goal)
    if shared>0:
        axis=0 if vx else 1;gap=abs(goal[axis]-start[axis])
        raise ValueError(f'facing card sides are {gap:g}px apart; connected sides need at least 2 x stub ({2*stub:g}px), so move the cards apart, choose other ports or lower routing.stub')
    if touch and begin!=end:
        raise ValueError('the source and target lead-ins cross each other; move the cards apart or choose other ports')
    # Lead-ins of connectors that are not routed yet block like finished lines.
    blocking=list(segments)+list(pending);finished=len(segments)
    names=names or [('a card or title',0)]*len(obstacles);owners=owners or [None]*len(blocking)
    for end_name,port,(dx,dy),(a,b) in (('source',start,(vx,vy),(start,begin)),('target',goal,(wx,wy),(end,goal))):
        for r,(name,margin) in zip(obstacles,names):
            if hits(a,b,r):
                x,y,w,h=r
                # Signed: negative when the shape already sits inside its margin.
                room=(x-port[0]) if dx>0 else (port[0]-x-w) if dx<0 else (y-port[1]) if dy>0 else (port[1]-y-h)
                keep=f' (lines keep {margin:g}px from it)' if margin else ''
                raise ValueError(f'Connector {end_name} lead-in intersects {name}: only {max(0,room):g}px of its {stub:g}px is clear{keep}, so move them {stub-room:g}px further apart or choose another port')
        for (c,d),owner in zip(blocking,owners):
            amount,point=relation(a,b,c,d)
            other=f'connector {owner!r}' if owner else 'another connector'
            if amount>0:raise ValueError(f'Connector lead-ins overlap with {other}; use distinct port offsets')
            # An arrow ending on another line reads as a junction, not a crossing.
            if point in (start,goal):
                raise ValueError(f"Connector {'source' if point==start else 'target'} port at ({point[0]:g}, {point[1]:g}) lies on {other}, which reads as a junction; choose another side or offset, or widen the lane beside the card")
    # Event-based grid includes obstacle boundaries, not every pixel of a huge canvas.
    for end_name,(px,py) in (('source',begin),('target',end)):
        if not MARGIN_SIDE<=px<=width-MARGIN_SIDE:
            raise ValueError(f'Connector {end_name} lead-in enters the {MARGIN_SIDE}px side margin; move the card inward or use another port')
        if not MARGIN_TOP<=py<=height-MARGIN_BOTTOM:
            raise ValueError(f'Connector {end_name} lead-in enters the title band or legend footer; keep the card {stub}px clear of it or use another port')
    xs={MARGIN_SIDE,width-MARGIN_SIDE,begin[0],end[0]};ys={MARGIN_TOP,height-MARGIN_BOTTOM,begin[1],end[1]}
    for x,y,w,h in obstacles:
        xs.update((x-10,x,x+w,x+w+10));ys.update((y-10,y,y+h,y+h+10))
    # Lanes 10px either side of a boundary let routes keep clear of it.
    for a,b in borders:
        xs.update((a[0]-BORDER_LANE,a[0]+BORDER_LANE,b[0]-BORDER_LANE,b[0]+BORDER_LANE));ys.update((a[1]-BORDER_LANE,a[1]+BORDER_LANE,b[1]-BORDER_LANE,b[1]+BORDER_LANE))
    for a,b in (blocking if stub_lanes else segments):
        xs.update((a[0]-10,a[0],a[0]+10,b[0]-10,b[0],b[0]+10))
        ys.update((a[1]-10,a[1],a[1]+10,b[1]-10,b[1],b[1]+10))
    xs=sorted(x for x in xs if MARGIN_SIDE<=x<=width-MARGIN_SIDE and (x in (begin[0],end[0]) or all(abs(x-v)>=10 for v in (begin[0],end[0]))))
    ys=sorted(y for y in ys if MARGIN_TOP<=y<=height-MARGIN_BOTTOM and (y in (begin[1],end[1]) or all(abs(y-v)>=10 for v in (begin[1],end[1]))))
    if begin[0] not in xs or end[0] not in xs or begin[1] not in ys or end[1] not in ys:raise ValueError('Connector enters title/footer margin')
    sx,sy=xs.index(begin[0]),ys.index(begin[1]);gx,gy=xs.index(end[0]),ys.index(end[1])
    dirs=list(SIDES.values());first=dirs.index((vx,vy));last=dirs.index((-wx,-wy))
    initial=(sx,sy,first);costs={initial:0};parents={};heap=[(length(begin,end),0,*initial)];finish=None
    own=[(start,begin),(end,goal)]
    # Index obstacles and earlier lines by grid line. The search asks about many
    # short moves, and scanning every card and line per move dominated runtime.
    blocked=set()
    for x,y,w,h in obstacles:
        for j in range(bisect_right(ys,y),bisect_left(ys,y+h)):
            for i in range(max(0,bisect_right(xs,x)-1),min(len(xs)-1,bisect_left(xs,x+w))):
                if max(xs[i],x)<min(xs[i+1],x+w):blocked.add((i,j,i+1,j))
        for i in range(bisect_right(xs,x),bisect_left(xs,x+w)):
            for j in range(max(0,bisect_right(ys,y)-1),min(len(ys)-1,bisect_left(ys,y+h))):
                if max(ys[j],y)<min(ys[j+1],y+h):blocked.add((i,j,i,j+1))
    lines=({},{})  # horizontal segments by y, vertical segments by x
    for k,(a,b) in enumerate(blocking):
        axis=1 if a[1]==b[1] else 0
        lines[axis-1 if axis else 1].setdefault(a[axis],[]).append(k)
    keys=tuple(sorted(index) for index in lines)
    def nearby(p,q):
        """Indices of earlier segments that can touch, cross or run beside p-q."""
        if p[1]==q[1]:same,cross,at,lo,hi=lines[0],lines[1],p[1],min(p[0],q[0]),max(p[0],q[0]);sk,ck=keys
        else:same,cross,at,lo,hi=lines[1],lines[0],p[0],min(p[1],q[1]),max(p[1],q[1]);ck,sk=keys
        reach=max(10,(PARALLEL_H if p[1]==q[1] else PARALLEL_V) if spread else 10)
        found=[k for v in sk[bisect_right(sk,at-reach):bisect_left(sk,at+reach)] for k in same[v]]
        found+=[k for v in ck[bisect_left(ck,lo):bisect_right(ck,hi)] for k in cross[v]]
        return sorted(found)
    border_lines=({},{})
    for a,b in borders:
        axis=1 if a[1]==b[1] else 0
        border_lines[0 if axis else 1].setdefault(a[axis],[]).append((a,b))
    border_keys=tuple(sorted(index) for index in border_lines)
    def near_borders(p,q):
        """Boundary edges parallel to p-q and closer than BORDER_GAP px."""
        horizontal=p[1]==q[1];index,ks=(border_lines[0],border_keys[0]) if horizontal else (border_lines[1],border_keys[1])
        at=p[1] if horizontal else p[0]
        return [seg for v in ks[bisect_right(ks,at-BORDER_GAP):bisect_left(ks,at+BORDER_GAP)] for seg in index[v]]
    def penalty(x,y,nx,ny):
        # Moves are symmetric, so both directions share one cache entry.
        return move_cost(*((x,y,nx,ny) if (x,y)<=(nx,ny) else (nx,ny,x,y)))
    @lru_cache(None)
    def move_cost(x,y,nx,ny):
        p,q=(xs[x],ys[y]),(xs[nx],ys[ny])
        if (x,y,nx,ny) in blocked:return None
        # The route may meet its own lead-ins only where it joins them.
        for a,b in own:
            amount,point=relation(p,q,a,b)
            if amount>0 or point not in (None,begin,end):return None
        cost=0;cross=set()
        for k in nearby(p,q):
            a,b=blocking[k]
            amount,point=relation(p,q,a,b)
            if amount>0:return None
            if point in (a,b):return None
            if point:cross.add(point)
            # Prefer visible separation between parallel lines.
            if p[1]==q[1]==a[1]==b[1] or p[0]==q[0]==a[0]==b[0]:
                # On request, keep lines from meeting another line end to end.
                if joins and k<finished and 0<(continuation(p,q,a,b) or 0)<CONTINUATION_GAP:cost+=180
                continue
            if p[1]==q[1] and a[1]==b[1] and abs(p[1]-a[1])<10:
                if max(min(p[0],q[0]),min(a[0],b[0]))<min(max(p[0],q[0]),max(a[0],b[0])):cost+=length(p,q)*3
            if p[0]==q[0] and a[0]==b[0] and 0<abs(p[0]-a[0])<10:
                if max(min(p[1],q[1]),min(a[1],b[1]))<min(max(p[1],q[1]),max(a[1],b[1])):cost+=length(p,q)*3
            # Long neighbouring runs squeeze the caption lane between them.
            if not spread:continue
            if p[1]==q[1] and a[1]==b[1] and 10<=abs(p[1]-a[1])<PARALLEL_H:
                if max(min(p[0],q[0]),min(a[0],b[0]))<min(max(p[0],q[0]),max(a[0],b[0])):cost+=length(p,q)*PARALLEL_FACTOR
            if p[0]==q[0] and a[0]==b[0] and 10<=abs(p[0]-a[0])<PARALLEL_V:
                if max(min(p[1],q[1]),min(a[1],b[1]))<min(max(p[1],q[1]),max(a[1],b[1])):cost+=length(p,q)*PARALLEL_FACTOR
        # A line running along a boundary reads as part of that boundary.
        for a,b in near_borders(p,q):
            if max(min(p[0],q[0]),min(a[0],b[0]))<min(max(p[0],q[0]),max(a[0],b[0])) if p[1]==q[1] else max(min(p[1],q[1]),min(a[1],b[1]))<min(max(p[1],q[1]),max(a[1],b[1])):
                cost+=length(p,q)*BORDER_FACTOR
        return cost+len(cross)*180
    work=work if work is not None else {}
    while heap:
        _,cost,x,y,d=heapq.heappop(heap);state=(x,y,d);work['steps']=work.get('steps',0)+1
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


def plan(m,header_rect,reserve=True,clear_borders=True,spread=True,stub_lanes=True,work=None,joins=False):
    nodes=endpoints(m);ports=select_ports(m);routes={};segments=[];seg_owners=[]
    boxes={c['id'] for c in m['containers']}
    clearance=m.get('routing',{}).get('clearance',8);stub=m.get('routing',{}).get('stub',16)
    title_pad=4
    names=[f"card {n['id']!r}" for n in m['nodes']]+[f"the title of {c['id']!r}" for c in m['containers']]
    # Main traffic first, then secondary semantics; stable IDs make input order irrelevant.
    rank={kind:index for index,kind in enumerate(EDGE_KINDS)}
    def order(e):
        a,b=nodes[e['source']],nodes[e['target']]
        distance=length((a['x']+a['w']/2,a['y']+a['h']/2),(b['x']+b['w']/2,b['y']+b['h']/2))
        return e.get('priority',rank[e.get('kind','traffic')]),distance,e['id']
    ordered=sorted(m['edges'],key=order)
    borders=[] if not clear_borders else sorted(seg for c in m['containers'] if not c.get('overlay') for seg in (((c['x'],c['y']),(c['x']+c['w'],c['y'])),((c['x'],c['y']+c['h']),(c['x']+c['w'],c['y']+c['h'])),((c['x'],c['y']),(c['x'],c['y']+c['h'])),((c['x']+c['w'],c['y']),(c['x']+c['w'],c['y']+c['h']))))
    # Every port's lead-in is known before routing starts. Reserving the ones not
    # routed yet stops an early connector from blocking or crossing them.
    stubs={}
    if reserve:
        # Sorted, so the input order of edges cannot change any route.
        for e in sorted(m['edges'],key=lambda e:e['id']):
            for end in ('source','target'):
                side,f=ports[(e['id'],end)];p=anchor(nodes[e[end]],side,f);v=SIDES[side]
                stubs[(e['id'],end)]=(p,(p[0]+v[0]*stub,p[1]+v[1]*stub))
    for e in ordered:
        a,b=nodes[e['source']],nodes[e['target']]
        sa,fa=ports[(e['id'],'source')];sb,fb=ports[(e['id'],'target')]
        margins=[0 if n['id'] in (a['id'],b['id']) else clearance for n in m['nodes']]+[title_pad]*len(m['containers'])
        obstacles=[pad(rect(n),margin) for n,margin in zip(m['nodes'],margins)]
        obstacles += [pad(header_rect(c),title_pad) for c in m['containers']]
        # A connector that ends on a boundary stays outside it.
        inside=[x for x in (a,b) if x['id'] in boxes]
        obstacles += [rect(x) for x in inside]
        start,goal=anchor(a,sa,fa),anchor(b,sb,fb)
        waiting=[(eid,seg) for (eid,_),seg in stubs.items() if eid!=e['id'] and eid not in routes]
        try:pts=solve(start,goal,sa,sb,obstacles,m['width'],m['height'],segments,clearance,stub,[seg for _,seg in waiting],borders,spread,
                      list(zip(names,margins))+[(f"the inside of {x['id']!r}",0) for x in inside],seg_owners+[eid for eid,_ in waiting],stub_lanes,work,joins)
        except ValueError as exc:raise RouteError(f"{e['id']}: {exc}") from exc
        if any(self_contact(pts)):
            raise RouteError(f"{e['id']}: route doubles back on itself; choose other ports, widen the lane or lower routing.stub")
        routes[e['id']]=pts;segments.extend(zip(pts,pts[1:]));seg_owners.extend([e['id']]*(len(pts)-1))
    return routes,ports


# Preferred first: reserved lead-ins stop early connectors from blocking or
# crossing later ones, and boundary clearance keeps lines off container edges.
# Both add constraints that occasionally leave no clear caption lane, so the
# plainer modes remain as fallbacks.
ROUTING_MODES=tuple({'reservedLeadIns':r,'borderClearance':b,'spreadParallels':p,'stubLanes':l}
                    for r in (True,False) for p in (False,True) for b in (True,False) for l in ((False,True) if r else (False,)))


class RouteError(ValueError):
    """A connector could not be routed."""


class LabelError(ValueError):
    """Every connector was routed, but some captions found no clear place."""
    def __init__(self,failures):
        super().__init__('\n'.join(failures));self.failures=failures


def route_and_label(m,header_rect):
    """Return routes, ports, labels and the first routing mode that places every caption.

    When no mode succeeds, report the attempt that got furthest: one that routed
    everything and missed the fewest captions, else the preferred mode's error.
    """
    best=None;work={'steps':0}
    for tried,mode in enumerate(ROUTING_MODES):
        # A deterministic budget of search steps, so a large diagram that no mode
        # can draw fails in seconds rather than after every mode has run.
        if tried and work['steps']>ROUTING_WORK_LIMIT:
            best.args=(f'{best}\n(stopped after {tried} of {len(ROUTING_MODES)} routing modes: this diagram is large for one view; split it, or widen the lanes named above)',)
            break
        try:
            routes,ports=plan(m,header_rect,mode['reservedLeadIns'],mode['borderClearance'],mode['spreadParallels'],mode['stubLanes'],work)
            labels=place_labels(m,routes,header_rect)
        except LabelError as exc:
            if not isinstance(best,LabelError) or len(exc.failures)<len(best.failures):best=exc
            continue
        except ValueError as exc:
            best=best or exc
            continue
        # Lines meeting end to end read as one; retry this mode avoiding that,
        # and keep the retry only when it succeeds with fewer such joins.
        joined=len(metrics(routes)['continuations'])
        if joined:
            try:
                retry,retry_ports=plan(m,header_rect,mode['reservedLeadIns'],mode['borderClearance'],mode['spreadParallels'],mode['stubLanes'],work,True)
                if len(metrics(retry)['continuations'])<joined:
                    return retry,retry_ports,place_labels(m,retry,header_rect),dict(mode,avoidJoins=True)
            except ValueError:
                pass
        return routes,ports,labels,dict(mode)
    raise best


def place_labels(m,routes,header_rect):
    obstacles=[(pad(rect(n),4),f"card {n['id']!r}") for n in m['nodes']]+[(pad(header_rect(b),4),f"the title of {b['id']!r}") for b in m['containers']]
    labels={};segments=[(eid,a,b) for eid,pts in routes.items() for a,b in zip(pts,pts[1:])]
    borders=[(seg,c['id']) for c in m['containers'] for seg in (((c['x'],c['y']),(c['x']+c['w'],c['y'])),((c['x'],c['y']+c['h']),(c['x']+c['w'],c['y']+c['h'])),((c['x'],c['y']),(c['x'],c['y']+c['h'])),((c['x']+c['w'],c['y']),(c['x']+c['w'],c['y']+c['h'])))]
    by={e['id']:e for e in m['edges']};failures=[]
    def blockers(eid,r,others=3):
        """Names of whatever keeps a caption rectangle from being clear."""
        found=[]
        if r[0]<12 or r[1]<80 or r[0]+r[2]>m['width']-12 or r[1]+r[3]>m['height']-88:found.append('the page margin')
        found+=[name for o,name in obstacles if overlap(r,o)]
        found+=['its own connector' if other==eid else f'connector {other!r}' for other,u,v in segments if hits(u,v,pad(r,3 if other==eid else others))]
        # Avoid captions covering container boundary lines.
        found+=[f'the border of {cid!r}' for (u,v),cid in borders if hits(u,v,pad(r,2))]
        return found
    for eid in sorted(routes,key=lambda k:(-len(by[k].get('label','')),k)):
        e=by[eid];label=e.get('label')
        if not label:continue
        units=sum(1 if unicodedata.east_asian_width(c) in 'WF' else .58 for c in label)
        lw=max(44,units*11+16);lh=22;pts=routes[eid];total=sum(length(a,b) for a,b in zip(pts,pts[1:]));before=0;candidates=[]
        for a,b in zip(pts,pts[1:]):
            seglen=length(a,b)
            if seglen<24:before+=seglen;continue
            # Anchors every ~6px plus the midpoint and the classic fractions, kept
            # clear of the bends at each end.
            margin=min(12,seglen*.2);steps=max(1,int((seglen-2*margin)//6))
            fractions={(margin+(seglen-2*margin)*k/steps)/seglen for k in range(steps+1)}|{.5,.4,.6,.3,.7,.2,.8}
            horizontal=a[1]==b[1];extent=lw if horizontal else lh
            for f in sorted(fractions):
                cx=a[0]+(b[0]-a[0])*f;cy=a[1]+(b[1]-a[1])*f
                offsets=[(-lw/2,-lh-5),(-lw/2,5)] if horizontal else [(6,-lh/2),(-lw-6,-lh/2)]
                score=abs((before+seglen*f)/total-.5)*30+(0 if horizontal else 5)
                # How far the caption reaches past either end of its segment.
                reach=max(0,extent/2-seglen*min(f,1-f))
                for dx,dy in offsets:
                    candidates.append((score,(cx+dx,cy+dy,lw,lh),(before+seglen*f)/total*2-1,(cx,cy),reach))
            before+=seglen
        # Prefer a caption that stays within its segment and keeps clear of other
        # connectors, so it cannot read as their label; relax each wish in turn.
        # Within a tier the best-scoring clear candidate wins.
        ranked=sorted(candidates,key=lambda v:(v[0],v[1]))
        chosen=None
        for inside,others in ((True,CAPTION_GAP),(True,3),(False,CAPTION_GAP),(False,3)):
            chosen=next((c for c in ranked if (not inside or c[4]<=0) and not blockers(eid,c[1],others)),None)
            if chosen:break
        if chosen:
            _,r,along,point,_=chosen
            labels[eid]={'rect':r,'relativeX':along,'offset':(r[0]-point[0],r[1]-point[1])};obstacles.append((pad(r,4),f'the caption of {eid!r}'))
        else:
            longest,run=max((length(a,b),a[1]==b[1]) for a,b in zip(pts,pts[1:]))
            if not ranked:
                failures.append(f'{eid}: no clear label position for {label!r}; every segment of its route is shorter than 24px (longest {longest:g}px), so give it a straight run or shorten the label')
                continue
            seen={}
            for _,r,_,_,_ in ranked[:12]:
                for name in blockers(eid,r):seen[name]=seen.get(name,0)+1
            worst=', '.join(sorted(seen,key=lambda n:(-seen[n],n))[:3])
            # A horizontal caption box needs its width plus 8px of straight run.
            hint=(f'; a straight horizontal run needs about {lw+8:.0f}px' if longest<lw+8 else '; that run is long enough, so the shapes beside it must move apart') if run else ''
            failures.append(f'{eid}: no clear label position for {label!r}; a {lw:.0f}x{lh}px caption fits beside none of its segments (longest {longest:g}px{hint}), and the best spots are blocked by {worst}. Widen the lane beside that segment, move those shapes, or shorten the label')
    if failures:raise LabelError(failures)
    return labels
