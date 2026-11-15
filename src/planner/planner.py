"""Offline polygon planner. No radio, mower protocol, flashing, or motor outputs."""
from dataclasses import dataclass
import heapq
import json
import math
from pathlib import Path

from shapely.affinity import affine_transform
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

EPS = 1e-8


class PlanningError(ValueError):
    pass


@dataclass(frozen=True)
class SafetyState:
    status_known: bool = False
    lifted: bool = False
    tilted: bool = False
    emergency_stop: bool = False
    fault: bool = False
    operator_stop: bool = False


def blade_allowed(requested, safety):
    """Reference gate only; the actual mower's independent interlocks must remain."""
    return bool(requested and safety.status_known and not any((
        safety.lifted, safety.tilted, safety.emergency_stop,
        safety.fault, safety.operator_stop)))


def load_rules(path=None):
    rules = json.loads(Path(path or Path(__file__).with_name('rules.json')).read_text())
    return validate_rules(rules)


def validate_rules(rules):
    rules = dict(rules)
    required = {
        'mapping_circuits_per_job': 1,
        'phase_order': ['horizontal', 'vertical'],
        'outbound': 'parallel', 'return': 'diagonal_to_next_adjacent_row',
        'boundary_follow_between_rows': False,
        'finish_section_before_transfer': True,
        'blade_on_during_cutting_returns_and_transfers': True,
        'mapping_blade_policy': 'retain_oem_policy',
    }
    for key, value in required.items():
        if rules.get(key) != value:
            raise PlanningError(f'Unsupported rule {key}: expected {value!r}')
    width, overlap = rules['cutting_width_m'], rules['nominal_overlap_m']
    if not all(math.isfinite(v) for v in (width, overlap)) or not 0 < overlap < width:
        raise PlanningError('Cutting width must exceed a positive finite overlap.')
    return rules


def frame_point(point, phase):
    # In the vertical phase u increases upward and v increases rightward.
    return tuple(point) if phase == 'horizontal' else (point[1], point[0])


def frame_polygon(polygon, phase):
    return polygon if phase == 'horizontal' else affine_transform(polygon, [0, 1, 1, 0, 0, 0])


def lines(geometry):
    if geometry.geom_type == 'LineString':
        return [geometry] if geometry.length > EPS else []
    return [line for part in getattr(geometry, 'geoms', []) for line in lines(part)]


def partition_regions(space):
    """Split at map vertices, then merge adjacent pieces whenever convex.

    A neck or concavity remains a section boundary. No lawn coordinates or
    fixed passage-width threshold are embedded in this rule.
    """
    from shapely.ops import split
    xs=sorted(set(p[0] for ring in [space.exterior,*space.interiors]
                  for p in ring.coords))
    if len(xs)>300:
        raise PlanningError('Simplify the map before reference section decomposition.')
    pieces=[space]
    minx,miny,maxx,maxy=space.bounds
    for x in xs[1:-1]:
        divider=LineString([(x,miny-1),(x,maxy+1)])
        pieces=[part for piece in pieces for part in split(piece,divider).geoms
                if part.geom_type=='Polygon' and part.area>EPS]
    changed=True
    while changed:
        changed=False
        for i in range(len(pieces)):
            for j in range(i):
                if pieces[i].boundary.intersection(pieces[j].boundary).length<=EPS:
                    continue
                merged=pieces[i].union(pieces[j])
                if merged.geom_type=='Polygon' and merged.convex_hull.area-merged.area<EPS:
                    pieces[j]=merged
                    pieces.pop(i)
                    changed=True
                    break
            if changed:
                break
    if unary_union(pieces).symmetric_difference(space).area>1e-6:
        raise PlanningError('Section decomposition lost map area.')
    return pieces


def split_sections(space, phase, pitch, cutter_radius):
    sections=[]
    for region in partition_regions(space):
        local=frame_polygon(region,phase)
        minx,miny,maxx,maxy=local.bounds
        count=max(2,math.ceil((maxy-miny)/pitch)+1)
        if count>20000:
            raise PlanningError('Map exceeds the offline planner row budget.')
        ys={maxy-EPS+i*(miny-maxy+2*EPS)/(count-1) for i in range(count)}
        ys.update(max(miny+EPS,min(maxy-EPS,p[1])) for p in local.exterior.coords)
        for refinement in range(12):
            nodes=[]
            for row,y in enumerate(sorted(ys,reverse=True)):
                clipped=lines(local.intersection(LineString([(minx-1,y),(maxx+1,y)])))
                if len(clipped)!=1:
                    raise PlanningError('A convex section yielded an ambiguous cutting row.')
                g=clipped[0]
                nodes.append({'row':row,'left':(g.bounds[0],y),'right':(g.bounds[2],y)})
            cuts=[LineString([n['right'],n['left']]) for n in nodes]
            cuts.extend(LineString([a['left'],b['right']]) for a,b in zip(nodes,nodes[1:]))
            # Pitch is a maximum. Additional rows close sloping-edge wedges.
            covered=unary_union([c.buffer(cutter_radius,quad_segs=16) for c in cuts])
            gaps=local.difference(covered)
            if gaps.area<=1e-5:
                break
            patches=list(gaps.geoms) if hasattr(gaps,'geoms') else [gaps]
            additions={p.representative_point().y for p in patches if p.area>1e-9}
            if not additions-ys:
                raise PlanningError('Coverage refinement made no progress.')
            ys.update(additions)
        else:
            raise PlanningError('Sloping-edge coverage requires unsupported refinement.')
        sections.append(nodes)
    return sections


class Router:
    """Visibility-graph transfer routing in explicit robot-clearance space."""
    def __init__(self, space):
        self.space=space
        self.padded=space.buffer(EPS)
        self.vertices=list(dict.fromkeys(tuple(p) for ring in
            [space.exterior,*space.interiors] for p in list(ring.coords)[:-1]))
        self.graph=[[] for _ in self.vertices]
        for i,a in enumerate(self.vertices):
            for j in range(i):
                b=self.vertices[j]
                if self.visible(a,b):
                    distance=math.dist(a,b)
                    self.graph[i].append((j,distance))
                    self.graph[j].append((i,distance))

    def visible(self,a,b):
        return self.padded.covers(LineString([a,b]))

    def route(self,start,end):
        start,end=tuple(start),tuple(end)
        if self.visible(start,end):
            return [start,end]
        points=self.vertices+[start,end]
        graph=[list(row) for row in self.graph]+[[],[]]
        n=len(self.vertices)
        for i in (n,n+1):
            for j in range(n):
                if self.visible(points[i],points[j]):
                    distance=math.dist(points[i],points[j])
                    graph[i].append((j,distance))
                    graph[j].append((i,distance))
        costs={n:0.0}; previous={}; queue=[(0.0,n)]
        while queue:
            cost,node=heapq.heappop(queue)
            if cost != costs[node]:
                continue
            if node==n+1:
                result=[end]
                while node != n:
                    node=previous[node]
                    result.append(points[node])
                return list(reversed(result))
            for neighbor,distance in graph[node]:
                candidate=cost+distance
                if candidate < costs.get(neighbor,math.inf):
                    costs[neighbor]=candidate
                    previous[neighbor]=node
                    heapq.heappush(queue,(candidate,neighbor))
        raise PlanningError('No traversable connection between sections.')


def build_plan(boundary, *, clearance_m, holes=(), rules=None, dock=None):
    """Compile a reference job from an already supplied map.

    MAP_ONCE is an event contract: a hardware adapter must actually map once,
    verify closure, then supply its validated map before starting CUT events.
    """
    rules=load_rules() if rules is None else validate_rules(rules)
    width=rules['cutting_width_m']; pitch=width-rules['nominal_overlap_m']
    if not math.isfinite(clearance_m) or clearance_m < width/2:
        raise PlanningError('Provide explicit clearance at least equal to the cutter radius.')
    if not all(math.isfinite(v) for ring in [boundary,*holes] for p in ring for v in p):
        raise PlanningError('Map coordinates must be finite meters.')
    lawn=Polygon(boundary,holes)
    if not lawn.is_valid or lawn.is_empty or lawn.area<=EPS:
        raise PlanningError('Map must be a valid polygon with non-overlapping holes.')
    space=lawn.buffer(-clearance_m,join_style=2)
    if space.is_empty:
        raise PlanningError('No room remains after robot clearance.')
    if space.geom_type!='Polygon':
        raise PlanningError('Clearance disconnects the lawn; a passage is too narrow for this model.')
    router=Router(space)
    actions=[{'kind':'MAP_ONCE','circuits':1,'blade_request':None,
              'requires':'Validated map closure; do not repeat mapping between cutting phases'}]
    position=None
    if dock is not None:
        position=tuple(dock)
        if not space.buffer(EPS).covers(Point(position)):
            raise PlanningError('Dock transfer point must be inside the clearance space.')
    phase_metrics={}
    def add(kind,phase,section,points,**extra):
        nonlocal position
        points=[tuple(p) for p in points]
        line=LineString(points)
        if not router.padded.covers(line):
            raise PlanningError(f'{kind} would leave robot-clearance space.')
        if position is not None and math.dist(position,points[0])>EPS*10:
            raise PlanningError('Discontinuous route.')
        actions.append(dict(kind=kind,phase=phase,section=section,points=points,
                            blade_request=True,length_m=line.length,**extra))
        position=points[-1]
    for phase in rules['phase_order']:
        sections=split_sections(space,phase,pitch,width/2)
        if not sections:
            raise PlanningError('Map yielded no cutting rows.')
        pending=set(range(len(sections)))
        first=max(pending,key=lambda i:(sections[i][0]['right'][1],sections[i][0]['right'][0]))
        completed=[]; phase_start=len(actions)
        while pending:
            if not completed:
                chosen=first
            else:
                candidates={i:router.route(position,frame_point(sections[i][0]['right'],phase))
                            for i in pending}
                chosen=min(pending,key=lambda i:(LineString(candidates[i]).length,i))
            rows=sections[chosen]
            start=frame_point(rows[0]['right'],phase)
            if position is not None and math.dist(position,start)>EPS:
                reason='phase_change' if not completed else 'section_change'
                add('TRANSFER',phase,chosen,router.route(position,start),reason=reason)
            for index,node in enumerate(rows):
                right,left=frame_point(node['right'],phase),frame_point(node['left'],phase)
                add('PARALLEL_CUT',phase,chosen,[right,left],row=node['row'])
                if index+1<len(rows):
                    next_right=frame_point(rows[index+1]['right'],phase)
                    add('DIAGONAL_CUT',phase,chosen,[left,next_right],row=node['row'])
            completed.append(chosen); pending.remove(chosen)
        cutting=[LineString(a['points']) for a in actions[phase_start:]
                 if a['kind'] in ('PARALLEL_CUT','DIAGONAL_CUT')]
        swath=unary_union([line.buffer(width/2,quad_segs=16) for line in cutting])
        missing=space.difference(swath)
        reachable_grass=lawn.intersection(space.buffer(width/2))
        phase_metrics[phase]={
            'sections':len(sections),'completed_sections':completed,
            'parallel_passes':sum(a['kind']=='PARALLEL_CUT' for a in actions[phase_start:]),
            'diagonal_passes':sum(a['kind']=='DIAGONAL_CUT' for a in actions[phase_start:]),
            'transfers':sum(a['kind']=='TRANSFER' for a in actions[phase_start:]),
            'center_space_area_m2':space.area,'uncovered_center_space_m2':missing.area,
            'center_space_coverage_fraction':1-missing.area/space.area,
            'reachable_grass_area_m2':reachable_grass.area,
            'uncovered_reachable_grass_m2':reachable_grass.difference(swath).area,
            'uncut_boundary_margin_m2':lawn.difference(reachable_grass).area,
        }
    if dock is not None and math.dist(position,dock)>EPS:
        add('RETURN_TO_DOCK','return',None,router.route(position,dock),reason='job_complete')
        actions[-1]['blade_request']=False
    return {'rules':rules,'clearance_m':clearance_m,'boundary':list(boundary),
            'holes':[list(h) for h in holes], 'actions':actions,'metrics':phase_metrics,
            'limitations':[
                'Offline reference routes only; no manufacturer source rebuild or hardware adapter.',
                'Input map units and clearance must be calibrated before any physical use.',
                'Straight segments and vertices do not simulate turning radius, chassis sweep, wheel slip or localization error.',
                'Diagonal overlap varies. Horizontal/vertical pass pitch supplies nominal adjacent-parallel overlap.',
                'Uncut areas and boundary margin are reported, not silently marked complete.',
                'Transfer paths may approach inset corners; no wire-following control mode is emitted.',
                'Convex sections derive from map vertices; transfers use greedy nearest-next routing, not a global crossing minimum.',
                'Mapping blade behavior remains OEM policy; motion stops must still be enforced by the hardware adapter.'
            ]}
