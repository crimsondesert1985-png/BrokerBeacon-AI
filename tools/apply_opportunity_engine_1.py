from pathlib import Path

APP = Path('BrokerBeacon_AI_Phase2/app.py')
text = APP.read_text(encoding='utf-8')

# Version
text = text.replace('BUILD_VERSION = "12.2"\nBUILD_NAME = "ASH MISSION CONTROL"', 'BUILD_VERSION = "12.3"\nBUILD_NAME = "OPPORTUNITY ENGINE"')
text = text.replace('VERSION 12.2 · ASH MISSION CONTROL', 'VERSION 12.3 · OPPORTUNITY ENGINE')

# Navigation
nav_anchor = '<button data-v="brokerdna">🧬 Broker DNA</button>'
if 'data-v="opportunityengine"' not in text:
    if nav_anchor not in text:
        raise SystemExit('Broker DNA navigation anchor not found')
    text = text.replace(nav_anchor, nav_anchor + '<button data-v="opportunityengine">◈ Opportunity Engine</button>')

# Styling
css = r'''
/* v12.3 Opportunity Engine */
.oe-toolbar{display:flex;justify-content:space-between;gap:10px;align-items:center;flex-wrap:wrap;margin:15px 0}.oe-filters{display:flex;gap:8px;flex-wrap:wrap}.oe-filters select{min-width:145px}.oe-list{display:grid;gap:12px}.oe-card{display:grid;grid-template-columns:76px minmax(0,1fr) auto;gap:15px;align-items:center;border:1px solid var(--line);border-radius:15px;background:#fff;padding:16px;box-shadow:0 5px 17px rgba(13,35,71,.05)}.oe-card:hover{border-color:#9db7d6;box-shadow:0 11px 27px rgba(13,35,71,.09)}.oe-score{width:65px;height:65px;border-radius:50%;display:grid;place-items:center;background:conic-gradient(#174ea6 calc(var(--oe)*1%),#e5ebf3 0);position:relative}.oe-score:after{content:"";position:absolute;inset:8px;border-radius:50%;background:#fff}.oe-score strong{position:relative;z-index:1;color:#0d2347;font-size:20px}.oe-title{display:flex;align-items:center;gap:7px;flex-wrap:wrap}.oe-title h4{margin:0;color:#0d2347}.oe-tier{display:inline-flex;padding:4px 8px;border-radius:999px;font-size:10px;font-weight:900}.oe-hot{background:#fdecef;color:#a51e33}.oe-warm{background:#fff3d2;color:#7c5700}.oe-watch{background:#e8f0fe;color:#174b91}.oe-research{background:#edf1f5;color:#526176}.oe-money{display:inline-flex;padding:5px 8px;border-radius:999px;background:#e5f6eb;color:#17653a;font-size:10px;font-weight:900}.oe-confidence{font-size:10px;color:#60708a}.oe-components{display:grid;grid-template-columns:repeat(5,minmax(90px,1fr));gap:7px;margin:9px 0}.oe-component{padding:8px;border-radius:9px;background:#f4f7fb;border:1px solid #e0e7f0}.oe-component small{display:block;color:#6b7b92;font-size:9px;text-transform:uppercase}.oe-component b{display:block;color:#173c70;margin-top:3px}.oe-explain{font-size:11px;color:#50637f;line-height:1.5}.oe-next{margin-top:7px;padding:9px 11px;border-left:3px solid #174ea6;background:#f2f7fe;border-radius:0 9px 9px 0;color:#304966;font-size:12px}.oe-actions{display:flex;gap:7px;flex-wrap:wrap;justify-content:flex-end}.dark-mode .oe-card,.dark-mode .oe-score:after{background:#101d34!important;border-color:#2b405f!important}.dark-mode .oe-title h4,.dark-mode .oe-score strong,.dark-mode .oe-component b{color:#edf4ff!important}.dark-mode .oe-component{background:#14223a;border-color:#2b405f}.dark-mode .oe-explain,.dark-mode .oe-confidence{color:#aebed4}.dark-mode .oe-next{background:#162946;color:#c3d3e7}.dark-mode .oe-score{background:conic-gradient(#4d91ea calc(var(--oe)*1%),#263750 0)}@media(max-width:900px){.oe-card{grid-template-columns:65px 1fr}.oe-actions{grid-column:1/-1;justify-content:flex-start}.oe-components{grid-template-columns:repeat(3,1fr)}}@media(max-width:580px){.oe-components{grid-template-columns:repeat(2,1fr)}.oe-filters{width:100%}.oe-filters select{flex:1;min-width:120px}}
'''
if '/* v12.3 Opportunity Engine */' not in text:
    text = text.replace('</style></head>', css + '</style></head>')

# Workspace HTML
workspace = r'''
<section id="opportunityengine" class="view">
<div class="ux-page-hero"><div><div class="kicker">ASH · OPPORTUNITY ENGINE 1.0</div><h2>Find the accounts most worth pursuing right now.</h2><p>The Opportunity Engine combines Broker DNA, modeled account value, product fit, relationship health, growth, engagement, and contact timing into an explainable priority score.</p></div><span class="ux-page-badge">Explainable · Actionable · Database-grounded</span></div>
<div class="command-kpis"><div class="command-kpi"><span>Modeled opportunity pipeline</span><strong id="oePipeline">$0</strong><small>12-month planning estimate</small></div><div class="command-kpi"><span>Hot opportunities</span><strong id="oeHot">0</strong><small>Score 80 or higher</small></div><div class="command-kpi"><span>High-value neglected</span><strong id="oeNeglected">0</strong><small>Strong account, 30+ days inactive</small></div><div class="command-kpi"><span>Average confidence</span><strong id="oeConfidence">0%</strong><small>Evidence completeness</small></div></div>
<div class="oe-toolbar"><div><div class="kicker">PORTFOLIO OPPORTUNITY RANKING</div><h3 style="margin:4px 0">Top opportunities</h3></div><div class="oe-filters"><select id="oeTier" onchange="renderOpportunityEngine()"><option value="All">All priorities</option><option value="Hot">Hot</option><option value="Warm">Warm</option><option value="Watch">Watch</option><option value="Research">Research</option></select><select id="oeState" onchange="renderOpportunityEngine()"><option value="All">All states</option></select><select id="oeProduct" onchange="renderOpportunityEngine()"><option value="All">All products</option></select><button class="btn" onclick="opportunityEngine()">Recalculate</button></div></div>
<div class="panel"><div id="oeList" class="oe-list"><div class="empty">Calculating portfolio opportunities…</div></div></div>
<div class="grid" style="margin-top:14px"><div class="panel"><div class="kicker">HOW IT SCORES</div><h3>Transparent prioritization</h3><div id="oeMethod" class="dna-method">Loading methodology…</div></div><div class="panel"><div class="kicker">HOW TO USE IT</div><h3>Move from insight to execution</h3><div class="dna-method"><p><b>Hot:</b> Work today with a personalized call or email.</p><p><b>Warm:</b> Create a relevant product conversation this week.</p><p><b>Watch:</b> Improve data or schedule a deliberate follow-up.</p><p><b>Research:</b> Verify the contact and account signal before spending selling time.</p></div></div></div>
</section>
'''
if '<section id="opportunityengine"' not in text:
    anchor = '</section>\n<section id="salescoach" class="view">'
    if anchor not in text:
        raise SystemExit('Sales Coach workspace anchor not found')
    text = text.replace(anchor, '</section>\n' + workspace + '<section id="salescoach" class="view">', 1)

# Show routing
old_show = "const titles={dashboard:'Ash Workplace',salescoach:'Ash Sales Coach',voiceagent:'AI Voice Agent',marketing:'Marketing Center',boss:'Executive View',followups:'Follow-ups',intelligence:'Opportunity Intelligence',templates:'Templates & Sequences',guidelines:'Loan Guidelines Library',production:'Production Intelligence',brokerdna:'Broker DNA'};"
new_show = "const titles={dashboard:'Ash Workplace',salescoach:'Ash Sales Coach',voiceagent:'AI Voice Agent',marketing:'Marketing Center',boss:'Executive View',followups:'Follow-ups',intelligence:'Opportunity Intelligence',opportunityengine:'Opportunity Engine',templates:'Templates & Sequences',guidelines:'Loan Guidelines Library',production:'Production Intelligence',brokerdna:'Broker DNA'};"
if old_show not in text:
    raise SystemExit('Show title map anchor not found')
text = text.replace(old_show, new_show, 1)
trigger = "if(v==='brokerdna')brokerDna();"
if "if(v==='opportunityengine')opportunityEngine();" not in text:
    text = text.replace(trigger, trigger + "if(v==='opportunityengine')opportunityEngine();", 1)

# Frontend logic
frontend = r'''
let opportunityEngineState={items:[],summary:{},methodology:{},filters:{}};
async function opportunityEngine(){
  const box=$('#oeList');if(box)box.innerHTML='<div class="empty">Calculating portfolio opportunities…</div>';
  try{
    opportunityEngineState=await api('/api/opportunity-engine');const s=opportunityEngineState.summary||{};
    $('#oePipeline').textContent=money(s.modeled_pipeline||0);$('#oeHot').textContent=s.hot||0;$('#oeNeglected').textContent=s.high_value_neglected||0;$('#oeConfidence').textContent=(s.average_confidence||0)+'%';
    const f=opportunityEngineState.filters||{};const state=$('#oeState'),product=$('#oeProduct');
    if(state&&state.options.length<=1)state.innerHTML='<option value="All">All states</option>'+(f.states||[]).map(x=>`<option>${esc(x)}</option>`).join('');
    if(product&&product.options.length<=1)product.innerHTML='<option value="All">All products</option>'+(f.products||[]).map(x=>`<option>${esc(x)}</option>`).join('');
    const m=opportunityEngineState.methodology||{};$('#oeMethod').innerHTML=`<p><b>Broker DNA:</b> ${m.dna||0}%</p><p><b>Modeled account value:</b> ${m.modeled_value||0}%</p><p><b>Product fit:</b> ${m.product_fit||0}%</p><p><b>Relationship health:</b> ${m.relationship||0}%</p><p><b>Contact timing:</b> ${m.timing||0}%</p><p><b>Growth signals:</b> ${m.growth||0}%</p><p><b>Engagement:</b> ${m.engagement||0}%</p><p>${esc(m.note||'')}</p>`;
    renderOpportunityEngine();
  }catch(e){if(box)box.innerHTML=`<div class="empty">Unable to load Opportunity Engine: ${esc(e.message)}</div>`}
}
function renderOpportunityEngine(){
  const tier=$('#oeTier')?.value||'All',state=$('#oeState')?.value||'All',product=$('#oeProduct')?.value||'All';let items=opportunityEngineState.items||[];
  if(tier!=='All')items=items.filter(x=>x.priority_tier===tier);if(state!=='All')items=items.filter(x=>x.state===state);if(product!=='All')items=items.filter(x=>(x.products||[]).includes(product));
  const box=$('#oeList');if(!box)return;
  box.innerHTML=items.length?items.slice(0,50).map(x=>`<article class="oe-card"><div class="oe-score" style="--oe:${x.opportunity_score}"><strong>${x.opportunity_score}</strong></div><div><div class="oe-title"><h4>${esc(x.company)}</h4><span class="oe-tier oe-${String(x.priority_tier).toLowerCase()}">${esc(x.priority_tier)}</span><span class="oe-money">${money(x.modeled_annual_volume||0)} modeled</span><span class="oe-confidence">Confidence ${x.confidence}%</span></div><div class="oe-components"><div class="oe-component"><small>DNA</small><b>${x.dna_score}</b></div><div class="oe-component"><small>Relationship</small><b>${x.relationship_health}</b></div><div class="oe-component"><small>Product fit</small><b>${x.product_fit_score}</b></div><div class="oe-component"><small>Growth</small><b>${x.growth_score}</b></div><div class="oe-component"><small>Inactive</small><b>${x.days_inactive>=999?'Never':x.days_inactive+'d'}</b></div></div><div class="oe-explain"><b>Why:</b> ${(x.reasons||[]).map(esc).join(' · ')}</div><div class="oe-next"><b>Next best action:</b> ${esc(x.next_best_action)}</div></div><div class="oe-actions"><button class="btn smallbtn" onclick="profile(${x.prospect_id})">Call prep</button><button class="btn primary smallbtn" onclick="quickDraft(${x.prospect_id})">Draft outreach</button></div></article>`).join(''):'<div class="empty">No opportunities match these filters.</div>';
}
'''
if 'let opportunityEngineState=' not in text:
    js_anchor = 'let OI=null;'
    if js_anchor not in text:
        raise SystemExit('Frontend JavaScript anchor not found')
    text = text.replace(js_anchor, frontend + '\n' + js_anchor, 1)

# Backend API
backend = r'''
@app.get('/api/opportunity-engine')
def opportunity_engine():
    """Rank explainable opportunities using only data stored in BrokerBeacon."""
    now=datetime.now()
    with db() as c:
        prospects=[dict(r) for r in c.execute("select * from prospects where status not in ('Funded') order by score desc")]
        dna_rows={r['prospect_id']:dict(r) for r in c.execute('select * from broker_dna')} if c.execute("select 1 from sqlite_master where type='table' and name='broker_dna'").fetchone() else {}
        last_actions={r['prospect_id']:r['last_at'] for r in c.execute('select prospect_id,max(created_at) last_at from sales_actions group by prospect_id')}
        action_counts={r['prospect_id']:r['n'] for r in c.execute('select prospect_id,count(*) n from sales_actions group by prospect_id')}
        contact_counts={r['prospect_id']:r['n'] for r in c.execute('select prospect_id,count(*) n from contacts group by prospect_id')}
        reply_counts={r['prospect_id']:r['n'] for r in c.execute('select prospect_id,count(*) n from inbound_messages where prospect_id is not null group by prospect_id')} if c.execute("select 1 from sqlite_master where type='table' and name='inbound_messages'").fetchone() else {}
        production_counts={r['prospect_id']:r['n'] for r in c.execute('select prospect_id,count(*) n from production_records where prospect_id is not null group by prospect_id')} if c.execute("select 1 from sqlite_master where type='table' and name='production_records'").fetchone() else {}
        settings={r['key']:float(r['value']) for r in c.execute('select key,value from revenue_settings')}
        avg_loan=settings.get('average_loan_amount',325000);meeting_rate=max(0,min(1,settings.get('meeting_to_application_rate',.35)));funding_rate=max(0,min(1,settings.get('application_to_funding_rate',.55)))
        items=[]
        for p in prospects:
            pid=int(p['id']);dna=dna_rows.get(pid)
            if not dna:
                dna=calculate_broker_dna(c,p)
            dna_score=int(dna.get('dna_score') or 0);relationship=int(dna.get('relationship_health') or 0);product_fit=int(dna.get('product_fit_score') or 0);engagement=int(dna.get('engagement_score') or 0)
            days=999
            if last_actions.get(pid):
                try:days=max(0,(now-datetime.fromisoformat(last_actions[pid])).days)
                except Exception:pass
            growth=max(0,min(100,int(p.get('growth_score') or 50)))
            status=p.get('status') or 'New';score=max(0,min(100,int(p.get('score') or 0)))
            status_factor={'New':.55,'Contacted':.68,'Replied':.82,'Meeting':.92,'Approved':1.0}.get(status,.6)
            health_factor=max(.35,relationship/100)
            expected_fundings=(score/100)*health_factor*status_factor*meeting_rate*funding_rate
            modeled_volume=round(expected_fundings*avg_loan*12)
            value_reference=max(avg_loan,avg_loan*12*meeting_rate*funding_rate)
            value_score=max(0,min(100,round(modeled_volume/value_reference*100)))
            timing=100 if days>=45 or days==999 else 82 if days>=30 else 65 if days>=14 else 42 if days>=7 else 25
            opportunity=round(dna_score*.25+value_score*.25+product_fit*.15+relationship*.10+timing*.10+growth*.10+engagement*.05)
            tier='Hot' if opportunity>=80 else 'Warm' if opportunity>=65 else 'Watch' if opportunity>=50 else 'Research'
            contacts=int(contact_counts.get(pid,0));actions=int(action_counts.get(pid,0));replies=int(reply_counts.get(pid,0));production=int(production_counts.get(pid,0))
            confidence=35+(12 if contacts else 0)+(10 if actions else 0)+(10 if replies else 0)+(12 if production else 0)+(10 if p.get('verification_status')=='Verified' else 0)+(8 if p.get('product_fit') else 0)
            confidence=max(30,min(95,confidence))
            reasons=[]
            if modeled_volume>=avg_loan:reasons.append(f'${modeled_volume:,.0f} modeled 12-month volume')
            if product_fit>=70:reasons.append('strong product fit')
            if relationship>=65:reasons.append('healthy relationship potential')
            elif relationship<45:reasons.append('relationship needs attention')
            if days==999:reasons.append('no sales activity recorded')
            elif days>=30:reasons.append(f'{days} days since recorded activity')
            if growth>=70:reasons.append('strong growth signal')
            if replies:reasons.append(f'{replies} stored repl' + ('y' if replies==1 else 'ies'))
            products=[x.strip() for x in (p.get('product_fit') or '').split(',') if x.strip()]
            if relationship<45:next_action='Call today to re-open the relationship, then send a product-specific follow-up.'
            elif not contacts:next_action='Verify a decision-maker contact before beginning outreach.'
            elif product_fit>=70:next_action=p.get('next_best_action') or 'Lead with the strongest product fit and ask for a live scenario.'
            else:next_action=p.get('next_best_action') or 'Run a discovery call to identify the broker’s current product need.'
            items.append({'prospect_id':pid,'company':p.get('company') or '','city':p.get('city') or '','state':p.get('state') or '','status':status,'opportunity_score':opportunity,'priority_tier':tier,'confidence':confidence,'modeled_annual_volume':modeled_volume,'dna_score':dna_score,'relationship_health':relationship,'product_fit_score':product_fit,'growth_score':growth,'engagement_score':engagement,'days_inactive':days,'products':products,'reasons':reasons[:4],'next_best_action':next_action})
    items.sort(key=lambda x:(-x['opportunity_score'],-x['modeled_annual_volume'],x['company'].lower()))
    top10=items[:10]
    summary={'total':len(items),'hot':sum(x['priority_tier']=='Hot' for x in items),'warm':sum(x['priority_tier']=='Warm' for x in items),'high_value_neglected':sum(x['opportunity_score']>=65 and x['days_inactive']>=30 for x in items),'modeled_pipeline':sum(x['modeled_annual_volume'] for x in top10),'average_confidence':round(sum(x['confidence'] for x in items)/len(items)) if items else 0}
    states=sorted({x['state'] for x in items if x['state']});products=sorted({p for x in items for p in x['products']})
    return jsonify(summary=summary,items=items,filters={'states':states,'products':products},methodology={'dna':25,'modeled_value':25,'product_fit':15,'relationship':10,'timing':10,'growth':10,'engagement':5,'note':'Scores are deterministic planning heuristics based only on stored BrokerBeacon data and configured assumptions. They do not guarantee production, responses, or revenue.'})

'''
if "@app.get('/api/opportunity-engine')" not in text:
    api_anchor = "@app.get('/api/mission-control')"
    if api_anchor not in text:
        raise SystemExit('Mission Control API anchor not found')
    text = text.replace(api_anchor, backend + api_anchor, 1)

APP.write_text(text, encoding='utf-8')
print('Opportunity Engine 1.0 applied')
