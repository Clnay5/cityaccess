import math
import pytest
import networkx as nx
from shapely.geometry import LineString
from cityaccess.network import directions,snap_and_build,nearest_facilities,path_length,build_segments

def segment(a=(0,0),b=(100,0),u='u',v='v',forward=True,backward=True):
    line=LineString([a,b]);return {'u':u,'v':v,'way':1,'line':line,'length':line.length,'forward':forward,'backward':backward,'highway':'footway'}

def test_walking_permissions_and_vehicle_oneway():
    assert directions({'highway':'residential','oneway':'yes'})==(True,True)
    assert directions({'highway':'residential','oneway:foot':'yes'})==(True,False)
    assert directions({'highway':'residential','oneway:foot':'-1'})==(False,True)
    assert directions({'highway':'path','foot':'no'}) is None
    assert directions({'highway':'service','access':'private'}) is None
    assert directions({'highway':'service','access':'private','foot':'yes'})==(True,True)
    assert directions({'highway':'motorway','foot':'yes'}) is None
    assert directions({'highway':'footway','area':'yes'}) is None
    assert directions({'highway':'cycleway'}) is None

def test_edge_projection_includes_connector_and_avoids_vertex_detour():
    points=[{'id':'f','xy':(20,0)},{'id':'d','xy':(80,5),'kind':'demand'}]
    g,s=snap_and_build([segment()],points,100)
    d=nearest_facilities(g,['point:f'])
    assert d['point:d']==pytest.approx(65)
    assert s[1]['snap_distance_m']==5
    path=nx.shortest_path(g,'point:d','point:f',weight='length')
    assert path_length(g,path)==pytest.approx(65)

def test_directed_nearest_search_reverses_graph():
    g,_=snap_and_build([segment(backward=False)],[{'id':'f','xy':(20,0)},{'id':'d','xy':(80,0)}],100)
    d=nearest_facilities(g,['point:f'])
    assert 'point:d' not in d
    assert nx.shortest_path_length(g,'point:f','point:d',weight='length')==60

def test_crossing_lines_do_not_create_false_junction():
    segs=[segment((-100,0),(100,0),'a','b'),segment((0,-100),(0,100),'c','d')]
    g,_=snap_and_build(segs,[{'id':'f','xy':(-50,0)},{'id':'p','xy':(0,50)}],100)
    assert not nx.has_path(g,'point:f','point:p')

def test_unsnapped_points_stay_missing_and_do_not_become_zero():
    g,s=snap_and_build([segment()],[{'id':'far','xy':(50,101)}],100)
    assert s[0]['status']=='beyond_snap_limit' and 'point:far' not in g
    assert nearest_facilities(g,[])=={}

def test_shared_osm_node_connects_segments():
    g,_=snap_and_build([segment(),segment((100,0),(100,100),'v','w')],
                       [{'id':'f','xy':(20,0)},{'id':'p','xy':(100,80)}],100)
    assert nx.shortest_path_length(g,'point:p','point:f',weight='length')==160

def test_same_edge_multiple_points_and_parallel_edges():
    g,_=snap_and_build([segment(),segment()],
                       [{'id':'f','xy':(25,0)},{'id':'p','xy':(25,0)},{'id':'q','xy':(75,0)}],100)
    assert nx.shortest_path_length(g,'point:p','point:f',weight='length')==0
    assert nx.shortest_path_length(g,'point:q','point:f',weight='length')==50

def test_blocked_node_and_duplicate_skeleton_tags():
    es=[{'type':'node','id':1,'lon':0,'lat':0,'tags':{'access':'private'}},
        {'type':'node','id':1,'lon':0,'lat':0},
        {'type':'node','id':2,'lon':.001,'lat':0},
        {'type':'node','id':3,'lon':.002,'lat':0},
        {'type':'way','id':1,'nodes':[1,2,3],'tags':{'highway':'footway'}}]
    seg,nodes,_,_,audit=build_segments(es,'EPSG:32631')
    assert len(seg)==1 and audit['blocked_node_segments']==1
    assert nodes[1]['tags']['access']=='private'
