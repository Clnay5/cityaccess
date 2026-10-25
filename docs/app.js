const $=s=>document.querySelector(s),labels={pharmacy:'药房',doctors:'医生诊所',clinic:'Clinic',hospital:'医院'};
let data,showRoute=false,selected=null;
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const statusNames={reachable:'网络可达',disconnected:'道路连通分量不可达',beyond_snap_limit:'距可用道路超过 100 m',no_facility_in_extract:'提取区内无可连接的该类设施'};
function value(r){
 const c=data.categories.find(c=>c.category===$('#category').value);
 if($('#closure').checked&&c.closure_scenario){const t=c.closure_scenario.sample_deltas.find(x=>x.id===r.id).after_minutes;return t===null?null:t*4.8/Number($('#speed').value)}return r.minutes[$('#speed').value];
}
function draw(){
 const c=data.categories.find(c=>c.category===$('#category').value),speed=Number($('#speed').value),closure=$('#closure').checked;
 const values=c.samples.map(value).filter(v=>v!==null),under=values.filter(v=>v<=15).length,ratio=under/c.samples.length;
 $('#status').textContent=c.evaluation_status==='no_facility_in_extract'?'数据不足：缓冲提取区内无可连接医院记录，不能据此判断牛津没有医院。':'模型结果：点位覆盖率以全部采样点为分母，缺失与不可达保留在分母中。';
 $('#metrics').innerHTML=[['15 分钟内采样点比例',c.snapped_facilities?(ratio*100).toFixed(1)+'%':'无法评估'],['15 分钟内 / 全部点',c.snapped_facilities?`${under} / ${c.samples.length}`:'—'],['网络可达采样点',c.snapped_facilities?`${values.length} / ${c.samples.length}`:'未评估'],['当前情景设施 · 缓冲区',c.snapped_facilities-(closure&&c.closure_scenario?1:0)]].map(([a,b])=>`<div class="metric"><span>${a}</span><strong>${b}</strong></div>`).join('');
 $('#closure').disabled=!c.closure_scenario;$('#route').disabled=!c.example_route||closure;
 $('#closureInfo').textContent=c.closure_scenario?`情景目标：${c.closure_scenario.removed_name}。只移除目标设施，保留道路和其他设施。`:'没有可用的关闭情景；该提取范围内的医院数据不足。';
 $('#routeInfo').textContent=c.example_route?`示例：${c.example_route.origin_id} → ${c.example_route.facility_name}，模型路程 ${(c.example_route.distance_m/1000).toFixed(2)} km。道路与连接边全部计入。`:'本类设施没有可展示的路径。';
 const box=[...data.config.analysis_bbox];box[0]-=.003;box[2]+=.003;box[1]-=.002;box[3]+=.002;
 if(showRoute&&!closure&&c.example_route)for(const [x,y] of c.example_route.coordinates){box[0]=Math.min(box[0],x-.001);box[2]=Math.max(box[2],x+.001);box[1]=Math.min(box[1],y-.001);box[3]=Math.max(box[3],y+.001)}
 const W=1000,H=W*(box[3]-box[1])/((box[2]-box[0])*Math.cos((box[1]+box[3])/2*Math.PI/180));
 const pos=p=>[(p[0]-box[0])/(box[2]-box[0])*W,(box[3]-p[1])/(box[3]-box[1])*H];
 const path=ps=>ps.map((p,i)=>`${i?'L':'M'}${pos(p).map(v=>v.toFixed(2)).join(',')}`).join('');
 $('#map').setAttribute('viewBox',`0 0 ${W} ${H}`);
 const color=v=>v===null?'#8d9299':v<=5?'#3f7966':v<=10?'#a4b56f':v<=15?'#e1bd75':'#c97e65';
 let html=`<path d="${data.roads.map(path).join('')}" fill="none" stroke="#adb7b4" stroke-width="2.4"/>`;
 const [w,s,e,n]=data.config.analysis_bbox;const corners=[[w,s],[e,s],[e,n],[w,n],[w,s]];
 html+=`<path d="${path(corners)}" fill="none" stroke="#6c858d" stroke-width="1.5" stroke-dasharray="8 7"/>`;
 if(showRoute&&!closure&&c.example_route)html+=`<path d="${path(c.example_route.coordinates)}" fill="none" stroke="#2b79b0" stroke-width="6"/>`;
 html+=c.samples.map(r=>{const [x,y]=pos(r.lonlat),v=value(r);return `<circle class="sample ${r.id===selected?'selected':''}" data-id="${r.id}" tabindex="0" role="button" aria-label="查看 ${r.id}" cx="${x}" cy="${y}" r="9" fill="${color(v)}"><title>${r.id} · ${v===null?'无法评估':v.toFixed(1)+' 分钟'}</title></circle>`}).join('');
 html+=data.facilities.filter(f=>f.category===c.category&&f.status==='snapped'&&!(closure&&c.closure_scenario?.removed_id===f.id)).map(f=>{const [x,y]=pos(f.lonlat);return `<path class="facility" d="M${x},${y-11} l9,11 l-9,11 l-9,-11 Z"><title>${esc(f.name)}</title></path>`}).join('');
 $('#map').innerHTML=html;
 $('#map').querySelectorAll('.sample').forEach(el=>{const choose=()=>{selected=el.dataset.id;detail(c.samples.find(r=>r.id===selected));$('#map').querySelectorAll('.sample').forEach(x=>x.classList.toggle('selected',x===el))};el.onclick=choose;el.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();choose()}}});
 if(selected)detail(c.samples.find(r=>r.id===selected));
}
function detail(r){if(!r)return;const v=value(r);$('#pointInfo').innerHTML=`<b>${r.id}</b><p>${esc(statusNames[r.status])}<br>当前情景时间：${v===null?'未评估／不可达':v.toFixed(2)+' 分钟'}<br>道路连接：${r.snap_distance_m.toFixed(1)} m<br>基线路程：${r.distance_m===null?'—':r.distance_m.toFixed(1)+' m'}<br>最近设施直线距离：${r.euclidean_nearest_m===null?'—':r.euclidean_nearest_m.toFixed(1)+' m'}<br>基线绕行系数：${r.detour_ratio===null?'—':r.detour_ratio.toFixed(2)}</p>`}
fetch('data/results.json').then(r=>{if(!r.ok)throw Error(r.status);return r.json()}).then(j=>{data=j;const n=j.network;$('#quality').innerHTML=`<p>${n.native_segments.toLocaleString()} 条原生道路段 · ${n.nodes.toLocaleString()} 图节点 · ${n.directed_edges.toLocaleString()} 条有向边</p><p>${n.weak_components} 个弱连通分量；${n.snapped_samples}/${n.demand_samples} 个采样点成功连接。保留未连接点，不删除问题样本。</p>`;$('#source').innerHTML=`<p>OSM 数据时间：${esc(j.source.osm_base_timestamp)}<br>查询与原始数据 SHA-256 已保存。</p><code>${j.source.raw_sha256}</code><p>${j.validation.samples_checked} 组多源／逐点最短路数值核对通过；示例路线成本核对通过。这验证算法一致性，不是实测步行精度。</p>`;draw();$('#category').onchange=()=>{showRoute=false;selected=null;$('#closure').checked=false;$('#pointInfo').textContent='点击地图采样点查看模型结果。';draw()};$('#speed').onchange=draw;$('#closure').onchange=draw;$('#route').onclick=()=>{showRoute=!showRoute;draw()}}).catch(e=>$('#status').textContent='加载失败：'+e.message);
