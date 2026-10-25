# Method, assumptions and validation

## Study and sources

Oxford central UK is a public case study, not the user's location. The analysis rectangle is `[-1.268,51.746,-1.246,51.762]`; the larger network query rectangle is `[-1.29,51.73,-1.225,51.78]`. All distances are computed in EPSG:32630 projected metres. A 150 m lattice inside the WGS84 analysis rectangle produces 117 sample points. These are spatial samples without population or residential masks.

The raw Overpass response is preserved losslessly in `data/osm.json.gz`. `data/source.json` records source endpoint, exact query, base timestamp, retrieval time and SHA-256 of the original uncompressed bytes. Duplicate skeleton node records are merged without dropping their tagged versions. Replay does not require network access. This is a snapshot, not a guarantee of current facility operation.

## Explicit walking policy

Ways with common pedestrian-compatible highway types are allowed under the documented study policy. Motorways, construction, proposed ways and area highways are excluded. Cycleways and unknown types require explicit positive foot access. Explicit `foot=no/private/customers/delivery/destination` excludes a way. Generic private/no access excludes it unless positive foot access is present. Vehicle `oneway` is ignored for pedestrians; `oneway:foot` and foot forward/backward denials control direction. A blocked node excludes incident segments. Wall/fence nodes require positive foot access; other barriers without explicit denials remain a modelling limitation. Conditional tags are counted but not evaluated. This simplified policy is a routing assumption, not a jurisdiction-wide statement of legal access.

Every consecutive pair of shared OSM node IDs forms a straight directed segment. Coordinates crossing on the map do not create an intersection. Grade separation is therefore respected where OSM topology represents it. Parallel edges remain available; edge lengths are projected Euclidean metres. Steps are included, so the model is not wheelchair routing. Walking cost uses constant speed only; slope, steps penalties, traffic lights, dynamic restrictions and crossing delays are not estimated.

## Facilities and snapping

Facilities are OSM node/way amenity records in four separate categories. Multipolygon relations are not included. Ways use an interior representative point because verified entrances are unavailable. Tagged private/customer-only facilities are excluded. Records are not automatically merged by name and may represent duplicate providers or different services. Categories are not interchangeable medical capacity.

Facilities and demand samples snap to the nearest permitted segment if ≤100 m away. The segment is split at its projected position, preserving forward/backward permissions and every segment's length. Both sides of a connector link the actual point to its anchor; connector length counts in network distance. Snaps beyond the limit remain unassessed, not zero-time. The connectors are geometric approximations and can cross obstacles or private land; no claim of street-level navigation correctness follows from them.

## Distances and scenarios

Multi-source Dijkstra runs from facilities on the **reversed directed graph**, yielding distances from demand samples to facilities. Distance includes both connectors. Uniform speeds 3,4.8,6 km/h translate metres to minutes. The 15-minute ratio uses all 117 samples as denominator, with unavailable/unreachable points retaining denominator membership. No population coverage or equity claim is made. A facility category with no connected source is marked `no_facility_in_extract` and coverage is null, because the extract's lack of a record does not establish city-wide absence.

Each available category includes one route, chosen among reachable samples with model distance <2.5 km to expose a substantial detour. Its actual network path is exported. The optional closure scenario removes the facility selected by this example route from the source set, preserves roads and recomputes distances. It is one disclosed what-if, not an optimization over closures or a forecast of service disruption.

## Validation completed

- Synthetic topology tests: edge-interior snapping versus nearest-vertex detour, perpendicular connector cost, directed search orientation, shared-ID connectivity, false map crossings, parallel edges, same-location points, no-snap states, node access and skeleton-tag preservation.
- Real case: 20 snapped demands per category (80 category/sample pairs) compared multi-source results against repeated independent single-source NetworkX Dijkstra calls; reachable/missing states and distances agreed within 1e-6 m.
- Example paths' edge costs sum to stored network distance.
- Consistency audit: network distance ≥ shortest straight-line facility distance; speed conversions and monotonicity; removing a target facility cannot improve modeled access; unavailable categories stay null.

These checks detect algorithm/accounting failures. They do not measure correctness of OSM mapping, real access rights, facility opening, entrance connectivity, observed walking time or medical availability. No field survey or ground-truth accuracy score was performed. Further validation should compare sampled routes and barriers against verified entrances and measured walks before any navigation use.

## References

- [OSM foot tags](https://wiki.openstreetmap.org/wiki/Key:foot)
- [Overpass QL](https://wiki.openstreetmap.org/wiki/Overpass_API/Overpass_QL)
- [NetworkX multi-source Dijkstra](https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.shortest_paths.weighted.multi_source_dijkstra.html)
- [OSM data attribution and license](https://www.openstreetmap.org/copyright)

Existing algorithms are attributed; this project implements and tests the data, policy, snapping, analysis and visualization integration with AI assistance.
