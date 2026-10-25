"""Explicit OSM walking policy and edge-split snapping, in projected metres."""
import math
from collections import Counter,defaultdict
import networkx as nx
from pyproj import Transformer
from shapely.geometry import Point,LineString,Polygon
from shapely.strtree import STRtree

DEFAULT_WALK={'footway','pedestrian','path','living_street','residential','service','unclassified',
              'tertiary','secondary','primary','tertiary_link','secondary_link','primary_link',
              'track','steps','bridleway'}
YES={'yes','designated','permissive','official'}
NO={'no','private','customers','delivery','destination'}

def directions(tags):
    """Return allowed forward/backward directions or None under the study policy."""
    foot=tags.get('foot','')
    if foot in NO:return None
    if tags.get('access') in NO and foot not in YES:return None
    highway=tags.get('highway')
    if highway in {'motorway','motorway_link','construction','proposed','raceway'}:return None
    if highway not in DEFAULT_WALK and foot not in YES:return None
    if tags.get('area')=='yes':return None
    ow=tags.get('oneway:foot','no')
    forward=ow!='-1';backward=ow not in {'yes','1','true'}
    if tags.get('foot:forward') in NO:forward=False
    if tags.get('foot:backward') in NO:backward=False
    return (forward,backward) if forward or backward else None

def build_segments(elements,crs):
    # Preserve tags when Overpass recursion emits the same node again as a skeleton.
    nodes={};ways={}
    for e in elements:
        table=nodes if e['type']=='node' else ways if e['type']=='way' else None
        if table is not None:table[e['id']]={**table.get(e['id'],{}),**e,
                                           'tags':{**table.get(e['id'],{}).get('tags',{}),**e.get('tags',{})}}
    project=Transformer.from_crs('EPSG:4326',crs,always_xy=True)
    xy={i:project.transform(n['lon'],n['lat']) for i,n in nodes.items()}
    segments=[];audit=Counter()
    for way in ways.values():
        tags=way.get('tags',{})
        if 'highway' not in tags:continue
        d=directions(tags)
        if not d:audit['excluded_ways']+=1;continue
        if any(':conditional' in k for k in tags):audit['ways_with_unmodelled_conditional_tags']+=1
        for u,v in zip(way['nodes'],way['nodes'][1:]):
            if u not in xy or v not in xy:audit['missing_node_segments']+=1;continue
            blocked=False
            for node in (u,v):
                nt=nodes[node].get('tags',{})
                if nt.get('foot') in NO or (nt.get('access') in NO and nt.get('foot') not in YES):blocked=True
                if nt.get('barrier') in {'wall','fence'} and nt.get('foot') not in YES:blocked=True
            if blocked:audit['blocked_node_segments']+=1;continue
            line=LineString([xy[u],xy[v]])
            if line.length<1e-6:audit['zero_length_segments']+=1;continue
            segments.append({'u':str(u),'v':str(v),'way':way['id'],'line':line,
                             'length':line.length,'forward':d[0],'backward':d[1],
                             'highway':tags['highway']})
        audit['accepted_ways']+=1
    if not segments:raise ValueError('No walkable segments')
    return segments,nodes,ways,xy,dict(audit)

def facilities(nodes,ways,xy,categories):
    points=[]
    for kind,items in [('node',nodes),('way',ways)]:
        for ident,item in items.items():
            tags=item.get('tags',{})
            if tags.get('amenity') not in categories:continue
            if tags.get('access') in NO:continue
            if kind=='node':p=Point(xy[ident]);method='OSM point'
            else:
                coords=[xy[n] for n in item.get('nodes',[]) if n in xy]
                if len(coords)<3:continue
                poly=Polygon(coords)
                if not poly.is_valid:poly=poly.buffer(0)
                if poly.is_empty:continue
                p=poly.representative_point();method='polygon representative point, entrance unknown'
            points.append({'id':f'{kind}/{ident}','xy':(p.x,p.y),'category':tags['amenity'],
                           'name':tags.get('name',tags.get('brand',tags['amenity'])),
                           'position_method':method})
    return points

def snap_and_build(segments,points,max_distance):
    lines=[s['line'] for s in segments];tree=STRtree(lines);splits=defaultdict(list);snaps=[]
    graph=nx.MultiDiGraph()
    for i,p in enumerate(points):
        point=Point(p['xy']);si=int(tree.nearest(point));line=lines[si]
        offset=line.project(point);anchor=line.interpolate(offset);distance=point.distance(anchor)
        record={**p,'node':f"point:{p['id']}",'snap_distance_m':distance,'segment':si}
        if distance>max_distance:
            record['status']='beyond_snap_limit';snaps.append(record);continue
        if offset<1e-6:node=segments[si]['u'];offset=0
        elif line.length-offset<1e-6:node=segments[si]['v'];offset=line.length
        else:node=f'split:{si}:{offset:.8f}'
        record.update(status='snapped',anchor_node=node,anchor_xy=(anchor.x,anchor.y))
        splits[si].append((offset,node,(anchor.x,anchor.y)))
        graph.add_node(record['node'],xy=p['xy'],kind=p.get('kind','facility'))
        graph.add_node(node,xy=(anchor.x,anchor.y),kind='road')
        graph.add_edge(record['node'],node,length=distance,kind='connector')
        graph.add_edge(node,record['node'],length=distance,kind='connector')
        snaps.append(record)
    for si,segment in enumerate(segments):
        stops=[(0,segment['u'],tuple(segment['line'].coords[0])),
               (segment['length'],segment['v'],tuple(segment['line'].coords[-1])),*splits[si]]
        unique={n:(o,n,xy) for o,n,xy in stops};stops=sorted(unique.values())
        for _,node,xy in stops:graph.add_node(node,xy=xy,kind='road')
        for (oa,a,_),(ob,b,_) in zip(stops,stops[1:]):
            if a==b:continue
            attr={'length':ob-oa,'kind':'road','way':segment['way'],'highway':segment['highway']}
            if segment['forward']:graph.add_edge(a,b,**attr)
            if segment['backward']:graph.add_edge(b,a,**attr)
    return graph,snaps

def nearest_facilities(graph,source_nodes):
    if not source_nodes:return {}
    # Distances FROM demands TO facilities require reversing the directed graph.
    return nx.multi_source_dijkstra_path_length(graph.reverse(copy=False),source_nodes,weight='length')

def path_length(graph,path):
    return sum(min(d['length'] for d in graph[a][b].values()) for a,b in zip(path,path[1:]))
