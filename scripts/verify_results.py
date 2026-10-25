"""Offline consistency checks on the real-data analysis. No accuracy claims."""
import json,math
from pathlib import Path
root=Path(__file__).resolve().parents[1];data=json.loads((root/'docs/data/results.json').read_text(encoding='utf-8'))
assert data['network']['demand_samples']==117
assert data['validation']['samples_checked']==80
for c in data['categories']:
    base=[]
    for r in c['samples']:
        d=r['distance_m'];euclid=r['euclidean_nearest_m']
        if d is not None:
            assert d+1e-6>=euclid
            assert abs(r['minutes']['4.8']-d/80)<1e-8
            assert r['minutes']['3']>=r['minutes']['4.8']>=r['minutes']['6']
        else:assert all(v is None for v in r['minutes'].values())
    if c['closure_scenario']:
        byid={r['id']:r for r in c['samples']}
        for r in c['closure_scenario']['sample_deltas']:
            t=byid[r['id']]['minutes']['4.8']
            if t is not None and r['after_minutes'] is not None:assert r['after_minutes']+1e-8>=t
    if c['snapped_facilities']==0:
        assert c['evaluation_status']=='no_facility_in_extract'
        assert all(s['fraction_of_all_samples_within_15_min'] is None for s in c['speed_summary'])
print('PASS: real snapshot, distance lower bound, unit conversion, speed monotonicity, closure monotonicity and missing category')
