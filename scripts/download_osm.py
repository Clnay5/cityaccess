"""Download one modest buffered OSM extract; keep raw public response + exact query/hash."""
import hashlib,json,sys
from pathlib import Path
from datetime import datetime,timezone
import requests
root=Path(__file__).resolve().parents[1];config=json.loads((root/'config.json').read_text())
w,s,e,n=config['network_bbox'];bbox=f'{s},{w},{n},{e}'
query=f'''[out:json][timeout:90];
(
 way[highway]({bbox});
 node[amenity~"^(pharmacy|doctors|clinic|hospital)$"]({bbox});
 way[amenity~"^(pharmacy|doctors|clinic|hospital)$"]({bbox});
);
out body;
>;
out skel qt;
'''
data=root/'data';data.mkdir(exist_ok=True)
endpoint=sys.argv[1] if len(sys.argv)>1 else config['overpass_endpoint']
r=requests.get(endpoint,params={'data':query},
               headers={'User-Agent':'CityAccess/0.1 (open GIS reproducibility study; https://github.com/Clnay5/cityaccess)'},timeout=60);r.raise_for_status()
j=r.json()
if 'remark' in j:raise RuntimeError(j['remark'])
if not j.get('elements'):raise RuntimeError('Empty OSM response')
(data/'osm.json').write_bytes(r.content)
manifest={'endpoint':endpoint,'query':query,'fetched_at':datetime.now(timezone.utc).isoformat(),
          'osm_base_timestamp':j.get('osm3s',{}).get('timestamp_osm_base'),
          'raw_sha256':hashlib.sha256(r.content).hexdigest(),'bytes':len(r.content),'elements':len(j['elements']),
          'license':'ODbL-1.0','attribution':'© OpenStreetMap contributors',
          'source':'https://www.openstreetmap.org/copyright'}
(data/'source.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print(json.dumps(manifest,indent=2))
