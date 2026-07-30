from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "BrokerBeacon_AI_Phase2" / "app.py"
s = APP.read_text(encoding="utf-8")


def replace_once(old, new, label):
    global s
    if new in s:
        return
    if old not in s:
        raise RuntimeError(f"Could not find {label} insertion point")
    s = s.replace(old, new, 1)


replace_once('BUILD_VERSION = "11.2"', 'BUILD_VERSION = "12.0"', "build version")
replace_once('BUILD_NAME = "PRODUCTION INTELLIGENCE"', 'BUILD_NAME = "BROKER DNA"', "build name")
replace_once('VERSION 11.3 · MARKETING CENTER', 'VERSION 12.0 · BROKER DNA', "visible version")

css = r'''
/* v12.0 Broker DNA */
.dna-toolbar{display:flex;gap:9px;align-items:center;justify-content:space-between;flex-wrap:wrap;margin:14px 0}.dna-toolbar select{min-width:170px}.dna-roster{display:grid;gap:11px}.dna-card{display:grid;grid-template-columns:74px minmax(0,1fr) auto;gap:16px;align-items:center;padding:16px;border:1px solid var(--line);border-radius:14px;background:#fff;box-shadow:0 5px 16px rgba(13,35,71,.05)}.dna-card:hover{border-color:#a9bfdb;box-shadow:0 10px 25px rgba(13,35,71,.09)}.dna-orb{width:64px;height:64px;border-radius:50%;display:grid;place-items:center;background:conic-gradient(#174ea6 calc(var(--dna)*1%),#e5ebf3 0);position:relative}.dna-orb:after{content:"";position:absolute;inset:8px;border-radius:50%;background:#fff}.dna-orb strong{position:relative;z-index:1;color:#0d2347;font-size:20px}.dna-main h4{margin:0 0 5px;color:#0d2347}.dna-meta{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px}.dna-components{display:grid;grid-template-columns:repeat(4,minmax(110px,1fr));gap:7px}.dna-component{padding:8px 9px;border-radius:9px;background:#f4f7fb;border:1px solid #e0e7f0}.dna-component small{display:block;color:#6b7b92;font-size:9px;text-transform:uppercase;letter-spacing:.05em}.dna-component b{display:block;color:#173c70;margin-top:3px}.dna-next{margin-top:9px;color:#3c4f6b;font-size:12px;line-height:1.45}.dna-actions{display:flex;gap:7px;flex-wrap:wrap;justify-content:flex-end}.dna-tier{display:inline-flex;align-items:center;padding:4px 8px;border-radius:999px;font-size:10px;font-weight:900}.dna-tier-a{background:#e5f6eb;color:#17653a}.dna-tier-b{background:#e8f0fe;color:#174b91}.dna-tier-c{background:#fff5da;color:#865d00}.dna-tier-d{background:#fdecef;color:#a51e33}.dna-method{font-size:12px;line-height:1.55;color:#60708a}.dna-method b{color:#0d2347}.dark-mode .dna-card,.dark-mode .dna-orb:after{background:#101d34!important;border-color:#2b405f!important}.dark-mode .dna-main h4,.dark-mode .dna-orb strong,.dark-mode .dna-component b,.dark-mode .dna-method b{color:#edf4ff!important}.dark-mode .dna-component{background:#14223a;border-color:#2b405f}.dark-mode .dna-next,.dark-mode .dna-method{color:#aebed4}.dark-mode .dna-orb{background:conic-gradient(#4d91ea calc(var(--dna)*1%),#263750 0)}@media(max-width:850px){.dna-card{grid-template-columns:64px 1fr}.dna-actions{grid-column:1/-1;justify-content:flex-start}.dna-components{grid-template-columns:repeat(2,1fr)}}@media(max-width:520px){.dna-components{grid-template-columns:1fr}}
'''
if "/* v12.0 Broker DNA */" not in s:
    s = s.replace("</style></head>", css + "</style></head>", 1)

replace_once(
    '<button data-v="prospects">◉ Prospects</button><button data-v="outreach">',
    '<button data-v="prospects">◉ Prospects</button><button data-v="brokerdna">🧬 Broker DNA</button><button data-v="outreach">',
    "Broker DNA navigation",
)

section = r'''</tbody></table></div></section>
<section id="brokerdna" class="view">
<div class="ux-page-hero"><div><div class="kicker">BROKER DNA · ACCOUNT INTELLIGENCE</div><h2>See the strength, health, and next move for every broker relationship.</h2><p>Broker DNA combines opportunity, stored relationship activity, engagement, and product fit into one explainable account score. It uses only information recorded in BrokerBeacon.</p></div><span class="ux-page-badge">Explainable · Database-grounded</span></div>
<div class="command-kpis"><div class="command-kpi"><span>Broker profiles</span><strong id="bdTotal">0</strong><small>Accounts evaluated</small></div><div class="command-kpi"><span>Average DNA score</span><strong id="bdAverage">0</strong><small>Across the current portfolio</small></div><div class="command-kpi"><span>Tier A accounts</span><strong id="bdTierA">0</strong><small>Highest composite strength</small></div><div class="command-kpi"><span>Relationship risk</span><strong id="bdRisk">0</strong><small>Health score below 45</small></div></div>
<div class="dna-toolbar"><div><div class="kicker">RANKED BROKER PROFILES</div><h3 style="margin:4px 0">Broker DNA roster</h3></div><div class="actions"><select id="bdTierFilter" onchange="renderBrokerDna()"><option value="All">All tiers</option><option value="A">Tier A</option><option value="B">Tier B</option><option value="C">Tier C</option><option value="D">Tier D</option><option value="Risk">Relationship risk</option></select><button class="btn" onclick="brokerDna()">Recalculate</button></div></div>
<div class="grid"><div class="panel" style="grid-column:1/-1"><div id="bdRoster" class="dna-roster"><div class="empty">Loading Broker DNA…</div></div></div><div class="panel"><div class="kicker">SCORING METHOD</div><h3>How Broker DNA is calculated</h3><div id="bdMethod" class="dna-method">Loading methodology…</div></div><div class="panel"><div class="kicker">HOW TO USE IT</div><h3>Turn the score into action</h3><div class="dna-method"><p><b>Tier A:</b> Protect and advance the relationship.</p><p><b>Tier B:</b> Create a specific product or scenario conversation.</p><p><b>Tier C:</b> Improve contact data and build engagement.</p><p><b>Tier D:</b> Research first or deprioritize until stronger signals appear.</p></div></div></div>
</section>
<section id="salescoach" class="view">'''
replace_once(
    '</tbody></table></div></section>\n<section id="salescoach" class="view">',
    section,
    "Broker DNA workspace",
)

replace_once(
    "prospects:{k:'ACCOUNT INTELLIGENCE'",
    "brokerdna:{k:'BROKER DNA',h:'Understand every broker relationship as one explainable profile.',p:'Composite scores combine opportunity strength, relationship health, engagement, and product fit using only stored BrokerBeacon data.',badge:'Account DNA',main:'Start with high-DNA accounts that also show relationship risk, then complete the recommended next action.',a:['Rank','Composite score'],b:['Explain','Four components'],c:['Act','Next best action']},\n prospects:{k:'ACCOUNT INTELLIGENCE'",
    "executive UX metadata",
)
replace_once(
    "prospects:['Which brokers should I prioritize?'",
    "brokerdna:['Which Tier A brokers need attention?','Show relationship risk','Explain my top Broker DNA score'],\n prospects:['Which brokers should I prioritize?'",
    "Ash prompts",
)
replace_once(
    "production:'Production Intelligence'};",
    "production:'Production Intelligence',brokerdna:'Broker DNA'};",
    "workspace title",
)
replace_once(
    "if(v==='salescoach')salesCoach();",
    "if(v==='brokerdna')brokerDna();if(v==='salescoach')salesCoach();",
    "workspace loader",
)

js = r'''
let brokerDnaState={brokers:[],summary:{},methodology:{}};
async function brokerDna(){
  const box=$('#bdRoster');if(box)box.innerHTML='<div class="empty">Calculating Broker DNA from stored account activity…</div>';
  try{
    brokerDnaState=await api('/api/broker-dna');const s=brokerDnaState.summary||{};
    $('#bdTotal').textContent=s.total||0;$('#bdAverage').textContent=s.average_score||0;$('#bdTierA').textContent=s.tier_a||0;$('#bdRisk').textContent=s.at_risk||0;
    const m=brokerDnaState.methodology||{};$('#bdMethod').innerHTML=`<p><b>Opportunity strength:</b> ${m.opportunity_strength||0}%</p><p><b>Relationship health:</b> ${m.relationship_health||0}%</p><p><b>Engagement:</b> ${m.engagement_score||0}%</p><p><b>Product fit:</b> ${m.product_fit_score||0}%</p><p>${esc(m.note||'')}</p>`;renderBrokerDna();
  }catch(e){if(box)box.innerHTML=`<div class="empty">Unable to load Broker DNA: ${esc(e.message)}</div>`}
}
function renderBrokerDna(){
  const filter=$('#bdTierFilter')?.value||'All';let items=brokerDnaState.brokers||[];
  if(filter==='Risk')items=items.filter(x=>Number(x.relationship_health)<45);else if(filter!=='All')items=items.filter(x=>x.tier===filter);
  const box=$('#bdRoster');if(!box)return;
  box.innerHTML=items.length?items.map(x=>`<article class="dna-card"><div class="dna-orb" style="--dna:${x.dna_score}"><strong>${x.dna_score}</strong></div><div class="dna-main"><h4>${esc(x.company)}</h4><div class="dna-meta"><span class="dna-tier dna-tier-${String(x.tier).toLowerCase()}">Tier ${esc(x.tier)}</span><span class="pill">${esc(x.city||'')}${x.state?', '+esc(x.state):''}</span><span class="pill">${esc(x.status||'New')}</span></div><div class="dna-components"><div class="dna-component"><small>Opportunity</small><b>${x.opportunity_strength}</b></div><div class="dna-component"><small>Relationship</small><b>${x.relationship_health}</b></div><div class="dna-component"><small>Engagement</small><b>${x.engagement_score}</b></div><div class="dna-component"><small>Product fit</small><b>${x.product_fit_score}</b></div></div><div class="dna-next"><b>Next:</b> ${esc(x.next_best_action)}</div></div><div class="dna-actions"><button class="btn smallbtn" onclick="profile(${x.prospect_id})">Open account</button><button class="btn primary smallbtn" onclick="quickDraft(${x.prospect_id})">Draft outreach</button></div></article>`).join(''):'<div class="empty">No broker profiles match this filter.</div>';
}
'''
if "let brokerDnaState=" not in s:
    marker = "let OI=null;\nlet SC={items:[],summary:{}};"
    if marker not in s:
        raise RuntimeError("Could not find Broker DNA JavaScript insertion point")
    s = s.replace(marker, js + "\n" + marker, 1)

APP.write_text(s, encoding="utf-8")
print("Broker DNA UI patch applied")
