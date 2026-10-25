import argparse,gzip,hashlib,json,math,platform,time
from pathlib import Path
from datetime import datetime,timezone
import networkx as nx
import numpy as np
from pyproj import Transformer
from shapely.geometry import Point,box
from .network import build_segments,facilities,snap_and_build,nearest_facilities,path_length

ROOT=Path(__file__).resolve().parents[1]

def run():
    start=time.perf_counter();config=json.loads((ROOT/'config.json').read_text());data=ROOT/'data'
    raw=(data/'osm.json').read_bytes() if (data/'osm.json').exists() else gzip.decompress((data/'osm.json.gz').read_bytes())
    source=json.loads((data/'source.json').read_text())
    if hashlib.sha256(raw).hexdigest()!=source['raw_sha256']:raise ValueError('Raw OSM hash mismatch')
    osm=json.loads(raw);segments,nodes,ways,xy,audit=build_segments(osm['elements'],config['crs'])
    pois=facilities(nodes,ways,xy,config['facility_categories'])
    forward=Transformer.from_crs('EPSG:4326',config['crs'],always_xy=True)
    inverse=Transformer.from_crs(config['crs'],'EPSG:4326',always_xy=True)
    west,south,east,north=config['analysis_bbox']
    corners=[forward.transform(lon,lat) for lon in (west,east) for lat in (south,north)]
    xmin=min(p[0] for p in corners);xmax=max(p[0] for p in corners)
    ymin=min(p[1] for p in corners);ymax=max(p[1] for p in corners);step=config['grid_spacing_m']
    demands=[]
    for x in np.arange(math.ceil(xmin/step)*step,xmax,step):
        for y in np.arange(math.ceil(ymin/step)*step,ymax,step):
            lon,lat=inverse.transform(x,y)
            if west<=lon<=east and south<=lat<=north:
                demands.append({'id':f'grid-{len(demands):03d}','xy':(float(x),float(y)),'kind':'demand'})
    graph,snaps=snap_and_build(segments,[*pois,*demands],config['maximum_snap_distance_m'])
    poi_snaps=[s for s in snaps if s.get('kind')!='demand'];demand_snaps=[s for s in snaps if s.get('kind')=='demand']
    categories=[];audit_errors=[];routes=[]
    for category in config['facility_categories']:
        available=[s for s in poi_snaps if s['category']==category and s['status']=='snapped']
        source_nodes=[s['node'] for s in available]
        distances=nearest_facilities(graph,source_nodes);records=[]
        for p in demand_snaps:
            distance=distances.get(p['node'])
            euclid=min((Point(p['xy']).distance(Point(s['xy'])) for s in available),default=None)
            records.append({'id':p['id'],'lonlat':list(inverse.transform(*p['xy'])),
                            'status':p['status'] if p['status']!='snapped' else 'no_facility_in_extract' if not available else 'reachable' if distance is not None else 'disconnected',
                            'snap_distance_m':p['snap_distance_m'],'distance_m':distance,
                            'euclidean_nearest_m':euclid,
                            'detour_ratio':distance/euclid if distance is not None and euclid and euclid>1 else None,
                            'minutes':{str(v):distance/(v*1000/60) if distance is not None else None for v in config['walking_speeds_kmh']}})
        # Numerical cross-check: independent repeated single-source shortest paths.
        tested=0
        for p in [s for s in demand_snaps if s['status']=='snapped'][:20]:
            single=nx.single_source_dijkstra_path_length(graph,p['node'],weight='length')
            brute=min((single[n] for n in source_nodes if n in single),default=None)
            fast=distances.get(p['node'])
            if (brute is None)!=(fast is None) or (brute is not None and abs(brute-fast)>1e-6):audit_errors.append(p['id'])
            tested+=1
        speed_summary=[]
        for speed in config['walking_speeds_kmh']:
            values=[r['minutes'][str(speed)] for r in records if r['minutes'][str(speed)] is not None]
            speed_summary.append({'speed_kmh':speed,'reachable_samples':len(values),'all_samples':len(records),
                                  'within_15_min':sum(t<=15 for t in values) if available else None,
                                  'fraction_of_all_samples_within_15_min':sum(t<=15 for t in values)/len(records) if available else None,
                                  'median_minutes_reachable':float(np.median(values)) if values else None})
        # Pick one real model route with a visible network detour.
        choices=[r for r in records if r['detour_ratio'] is not None and 500<=r['distance_m']<2500 and r['euclidean_nearest_m']>100]
        route=None
        if choices and source_nodes:
            chosen=max(choices,key=lambda r:r['detour_ratio'])
            origin=next(s for s in demand_snaps if s['id']==chosen['id'])
            dd,paths=nx.single_source_dijkstra(graph,origin['node'],weight='length')
            target=min((n for n in source_nodes if n in dd),key=lambda n:dd[n])
            path=paths[target];length=path_length(graph,path)
            if abs(length-chosen['distance_m'])>1e-6:raise ValueError('Route accounting mismatch')
            facility=next(s for s in available if s['node']==target)
            route={'category':category,'origin_id':chosen['id'],'facility_id':facility['id'],'facility_name':facility['name'],
                   'distance_m':length,'detour_ratio':chosen['detour_ratio'],
                   'coordinates':[list(inverse.transform(*graph.nodes[n]['xy'])) for n in path],
                   'includes_model_connectors':True}
            routes.append({'type':'Feature','properties':{k:v for k,v in route.items() if k!='coordinates'},
                           'geometry':{'type':'LineString','coordinates':route['coordinates']}})
        closure=None
        # One disclosed scenario: close the facility used by the selected example route.
        if route and len(source_nodes)>1:
            removed=next(s for s in available if s['id']==route['facility_id'])
            alt=nearest_facilities(graph,[n for n in source_nodes if n!=removed['node']])
            changes=[(alt[p['node']]-distances[p['node']])/(4.8*1000/60) for p in demand_snaps if p['node'] in alt and p['node'] in distances]
            newly_unreachable=sum(p['node'] in distances and p['node'] not in alt for p in demand_snaps)
            closure={'removed_id':removed['id'],'removed_name':removed['name'],'speed_kmh':4.8,
                     'newly_unreachable_samples':newly_unreachable,
                     'mean_added_minutes_still_reachable':float(np.mean(changes)) if changes else None,
                     'sample_deltas':[{'id':p['id'],'after_minutes':alt[p['node']]/80 if p['node'] in alt else None} for p in demand_snaps]}
        categories.append({'category':category,'evaluation_status':'evaluated' if available else 'no_facility_in_extract',
                           'mapped_facilities':sum(s['category']==category for s in poi_snaps),
                           'snapped_facilities':len(available),'samples':records,'speed_summary':speed_summary,
                           'cross_check_samples':tested,'example_route':route,'closure_scenario':closure})
    if audit_errors:raise ValueError('Multi-source mismatch: '+str(audit_errors))
    out=ROOT/'docs'/'data';out.mkdir(exist_ok=True,parents=True)
    roads=[];clip=box(xmin-250,ymin-250,xmax+250,ymax+250)
    for s in segments:
        if s['line'].intersects(clip):
            roads.append([[round(c,6) for c in inverse.transform(*p)] for p in s['line'].coords])
    facilities_out=[{k:v for k,v in s.items() if k not in ('xy','anchor_xy')}|{'lonlat':list(inverse.transform(*s['xy']))} for s in poi_snaps]
    components=list(nx.weakly_connected_components(graph))
    result={'generated_at':datetime.now(timezone.utc).isoformat(),'config':config,'source':source,'audit':audit,
            'network':{'nodes':graph.number_of_nodes(),'directed_edges':graph.number_of_edges(),'native_segments':len(segments),
                       'weak_components':len(components),'largest_component_nodes':max(map(len,components)),
                       'demand_samples':len(demands),'snapped_samples':sum(s['status']=='snapped' for s in demand_snaps)},
            'categories':categories,'facilities':facilities_out,'roads':roads,
            'validation':{'multi_source_vs_repeated_dijkstra':'passed','samples_checked':sum(x['cross_check_samples'] for x in categories),
                          'route_cost_checks':'passed','scope':'Algorithm/accounting checks, not measured real walking times'},
            'environment':{'python':platform.python_version(),'networkx':nx.__version__,'numpy':np.__version__},
            'runtime_seconds':time.perf_counter()-start,
            'limits':['Uniform demand grid is not population; coverage is a sample fraction.',
                      'Straight connector spokes may cross obstacles; no entrance verification.',
                      'Opening hours, turn restrictions, access conditionals, slopes and crossing wait times are not modelled.',
                      'Facility entities are OSM records, not guaranteed unique providers or currently open services.',
                      'No street-level walking-time ground truth; not a medical service recommendation.']}
    (out/'results.json').write_text(json.dumps(result,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    (out/'example-routes.geojson').write_text(json.dumps({'type':'FeatureCollection','features':routes}),encoding='utf-8')
    points=[]
    for c in categories:
        for r in c['samples']:points.append({'type':'Feature','properties':{'category':c['category'],**{k:v for k,v in r.items() if k!='lonlat'}},'geometry':{'type':'Point','coordinates':r['lonlat']}})
    (out/'accessibility.geojson').write_text(json.dumps({'type':'FeatureCollection','features':points},separators=(',',':')),encoding='utf-8')
    # Keep an exact compressed replay snapshot; source.json hashes the original uncompressed bytes.
    (data/'osm.json.gz').write_bytes(gzip.compress(raw,mtime=0))
    evidence=ROOT/'evidence';evidence.mkdir(exist_ok=True)
    (evidence/'validation.json').write_text(json.dumps({'network':result['network'],'validation':result['validation'],
                                                    'audit':audit,'source_sha256':source['raw_sha256']},indent=2),encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('network','validation','runtime_seconds')},indent=2))
    for c in categories:print(c['category'],c['snapped_facilities'],c['speed_summary'])

if __name__=='__main__':run()
