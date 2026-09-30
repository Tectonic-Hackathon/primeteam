import React, { useEffect, useRef, useState } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { ArrowRight, BookOpen, Check, ChevronDown, CircleAlert, Database, ExternalLink, FileText, Filter, Info, LayoutDashboard, Link2, Search, ShieldCheck, Sparkles, UploadCloud, X } from 'lucide-react'
import './styles.css'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'
type Role = 'employee' | 'steward'
type View = 'ask' | 'review' | 'sources'
type Tab = 'answer' | 'review'
type Source = { id:string; family:string; version:string; type:string; title:string; original_name:string; owner:string|null; status:string; country:string|null; domain:string|null; client:string|null; project:string|null; effective_from:string|null; effective_until:string|null; modified_at:string|null; acl:string; mime:string; ingested_at:string; tags:string[] }
type Evidence = { id:string; span_id:string; source_id:string; source_title:string; location:string; excerpt:string; source_type:string; status:string }
type Claim = { id:string; text:string; status:string; evidence_ids:string[]; component:string|null }
type Review = { id:string; kind:string; label:string; title:string; source_ids:string[]; action:string }
type Expert = { id:string; name:string; role:string; team:string; country:string; topic:string; activities:{ id:string; kind:string; source_id:string; span_id:string; happened_at:string; explanation:string }[] }
type Result = { api_version:string; run_id:string; mode:string; status:string; scope:{country:string;domain:string;client:string|null;project:string|null;as_of:string}; claims:Claim[]; evidence:Evidence[]; completeness:{component:string;status:string;reason:string}[]; unknown:string[]; review_items:Review[]; exclusions:{source_id:string;title:string;reasons:string[];score:number}[]; experts:Expert[]; plan:{reformulations:string[];routes:string[]}; diagnostics:{candidate_ids:string[];excluded:unknown[];scores:Record<string,number>} }
type EvidenceDetail = { id:string; excerpt:string; location:string; source:Source }

function apiFetch(path:string, role:Role, init?:RequestInit) {
  return fetch(`${API}${path}`, { ...init, headers: { 'X-Demo-Role':role, ...(init?.headers || {}) } }).then(async response => {
    if (!response.ok) {
      const body = await response.json().catch(() => ({}))
      throw new Error(typeof body.detail === 'string' ? body.detail : `Request failed (${response.status})`)
    }
    return response.json()
  })
}

function App() {
  const [view, setView] = useState<View>('ask')
  const [tab, setTab] = useState<Tab>('answer')
  const [role, setRole] = useState<Role>('employee')
  const [question, setQuestion] = useState('For Project Atlas in Belgium, what is the payroll handover sequence, and who confirms the client-facing completion note?')
  const [country, setCountry] = useState('Belgium')
  const [domain, setDomain] = useState('Pay')
  const [client, setClient] = useState('Atlas')
  const [project, setProject] = useState('Project Atlas')
  const [asOf, setAsOf] = useState('2026-09-30')
  const [result, setResult] = useState<Result|null>(null)
  const [sources, setSources] = useState<Source[]>([])
  const [globalReviews, setGlobalReviews] = useState<Review[]>([])
  const [selectedEvidence, setSelectedEvidence] = useState<EvidenceDetail|null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [uploadError, setUploadError] = useState('')
  const [uploadSuccess, setUploadSuccess] = useState('')
  const [showDiagnostics, setShowDiagnostics] = useState(false)
  const dialogRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    apiFetch('/api/sources', role).then(data => setSources(data.sources)).catch(e => setError(e.message))
    apiFetch('/api/review-items', role).then(data => setGlobalReviews(data.items)).catch(() => {})
  }, [role])

  useEffect(() => {
    if (!selectedEvidence) return
    dialogRef.current?.focus()
    const onKey = (event:KeyboardEvent) => { if (event.key === 'Escape') setSelectedEvidence(null) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [selectedEvidence])

  const runQuery = async (event?:React.FormEvent) => {
    event?.preventDefault()
    setLoading(true); setError(''); setView('ask'); setTab('answer')
    try {
      const data = await apiFetch('/api/query', role, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({ question,country,domain,client:client || null,project:project || null,as_of:asOf }) })
      setResult(data)
    } catch (e) { setError((e as Error).message) }
    finally { setLoading(false) }
  }

  const openEvidence = async (spanId:string) => {
    try { setSelectedEvidence(await apiFetch(`/api/evidence/${encodeURIComponent(spanId)}`, role)) }
    catch (e) { setError((e as Error).message) }
  }

  const useExample = (kind:'belgium'|'france') => {
    if (kind === 'france') {
      setQuestion('For France payroll, what is the handover process?')
      setCountry('France'); setDomain('Pay'); setClient(''); setProject('')
    } else {
      setQuestion('For Project Atlas in Belgium, what is the payroll handover sequence, and who confirms the client-facing completion note?')
      setCountry('Belgium'); setDomain('Pay'); setClient('Atlas'); setProject('Project Atlas')
    }
    setResult(null); setTab('answer'); setView('ask')
  }

  const upload = async (event:React.FormEvent<HTMLFormElement>) => {
    event.preventDefault(); setUploadError(''); setUploadSuccess('')
    const form = new FormData(event.currentTarget)
    const id = String(form.get('id') || '').trim()
    const file = form.get('file') as File
    const metadata = { id, type:String(form.get('type')), title:String(form.get('title')),
      country:String(form.get('country')), domain:String(form.get('domain')),
      owner:String(form.get('owner') || '') || null, client:null, project:null, version:'1', acl:'employee' }
    const body = new FormData(); body.set('metadata', JSON.stringify(metadata)); body.set('file', file)
    try {
      const uploaded = await apiFetch('/api/sources/import', role, {method:'POST',body})
      setUploadSuccess(`${uploaded.id} imported as a draft with ${uploaded.spans} indexed spans.`)
      const next = await apiFetch('/api/sources', role); setSources(next.sources)
      event.currentTarget.reset()
    } catch (e) { setUploadError((e as Error).message) }
  }

  const activeReviews = result?.review_items || globalReviews
  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><div className="brand-mark"><span></span><span></span><span></span><span></span></div><div><strong>SD worx<span className="brand-dot">.</span></strong><small>Knowledge Trust <em>prototype</em></small></div></div>
      <div className="side-label">WORKSPACE</div>
      <nav aria-label="Main navigation">
        <button className={view==='ask'?'nav-item active':'nav-item'} onClick={() => setView('ask')}><LayoutDashboard size={18}/> Ask knowledge</button>
        <button className={view==='review'?'nav-item active':'nav-item'} onClick={() => setView('review')}><CircleAlert size={18}/> For review <span className="nav-count">{activeReviews.length}</span></button>
        <button className={view==='sources'?'nav-item active':'nav-item'} onClick={() => setView('sources')}><Database size={18}/> Source library</button>
      </nav>
      <div className="sidebar-bottom"><div className="demo-card"><div className="demo-icon"><Sparkles size={17}/></div><div><strong>Demo environment</strong><p>All people, sources and client details are synthetic.</p></div></div><div className="role-select"><span>Viewing as</span><select aria-label="Demo role" value={role} onChange={e=>{setRole(e.target.value as Role);setResult(null)}}><option value="employee">Employee</option><option value="steward">Knowledge steward</option></select></div></div>
    </aside>
    <main className="main">
      <header className="topbar"><div className="mobile-brand">Knowledge Trust</div><div className="breadcrumb">Workspace <span>/</span> <strong>{view==='ask'?'Ask knowledge':view==='review'?'For review':'Source library'}</strong></div><div className="top-right"><span className="live-dot"></span> Local demo <span className="top-divider"></span><span className="avatar">{role==='employee'?'E':'K'}</span></div></header>
      {view === 'ask' && <div className="content">
        <div className="page-intro"><div className="eyebrow"><span className="eyebrow-line"></span> YOUR KNOWLEDGE WORKSPACE</div><h1>Answers you can<br/><span>stand behind.</span></h1><p>Ask across documents and conversations. See what applies, what conflicts, and exactly where each answer comes from.</p></div>
        <form className="query-card" onSubmit={runQuery}><div className="query-head"><div className="query-icon"><Search size={20}/></div><label htmlFor="question">What would you like to know?</label></div><textarea id="question" required minLength={5} maxLength={600} value={question} onChange={e=>setQuestion(e.target.value)} placeholder="Ask a question about a process, decision, or handover…"/><div className="context-heading"><Filter size={15}/> CONTEXT <span>Confirm where and when this answer applies</span></div><div className="context-grid"><label>Country<select value={country} onChange={e=>setCountry(e.target.value)}><option>Belgium</option><option>France</option></select></label><label>Team / domain<select value={domain} onChange={e=>setDomain(e.target.value)}><option>Pay</option><option>HR</option><option>Time</option></select></label><label>Client<input value={client} onChange={e=>setClient(e.target.value)} placeholder="Optional"/></label><label>Project<input value={project} onChange={e=>setProject(e.target.value)} placeholder="Optional"/></label><label>As of<input type="date" required value={asOf} onChange={e=>setAsOf(e.target.value)}/></label></div><div className="query-footer"><div className="example-group"><span>TRY AN EXAMPLE</span><button type="button" onClick={()=>useExample('belgium')}>Belgium handover</button><button type="button" onClick={()=>useExample('france')}>France handover</button></div><button className="primary-button" disabled={loading} type="submit">{loading?'Checking sources…':'Find trusted answer'} <ArrowRight size={17}/></button></div></form>
        {error && <div className="error-banner" role="alert"><CircleAlert size={18}/>{error}</div>}
        {result && <section className="results" aria-label="Query results"><div className="results-top"><div><div className="eyebrow small"><span className="eyebrow-line"></span> QUERY RESULT</div><h2>What the evidence says</h2><p>For <strong>{result.scope.country} · {result.scope.domain}</strong>{result.scope.client && <> · {result.scope.client}</>} on {result.scope.as_of}</p></div><span className={`status-pill ${result.status==='Supported'?'supported':'review'}`}>{result.status==='Supported'?<Check size={15}/>:<CircleAlert size={15}/>} {result.status}</span></div><div className="tab-bar" role="tablist" aria-label="Result sections"><button role="tab" aria-selected={tab==='answer'} className={tab==='answer'?'selected':''} onClick={()=>setTab('answer')}>Answer & evidence</button><button role="tab" aria-selected={tab==='review'} className={tab==='review'?'selected':''} onClick={()=>setTab('review')}>For review <span>{result.review_items.length}</span></button></div>
          {tab==='answer'? <div className="result-grid"><div className="answer-panel"><div className="panel-title"><ShieldCheck size={19}/> Evidence-backed answer</div>{result.claims.length ? <div className="claims">{result.claims.map(claim=><div className="claim" key={claim.id}><div className="claim-rail"></div><p>{claim.text} {claim.evidence_ids.map(id=>{const ev=result.evidence.find(x=>x.id===id);return <button key={id} className="citation" title={`Open ${id} evidence`} onClick={()=>ev&&openEvidence(ev.span_id)}>[{id}]</button>})}</p></div>)}</div> : <div className="empty-state"><BookOpen size={24}/><p>No approved, applicable evidence establishes an answer for this scope.</p></div>}{result.unknown.map((u,i)=><div className="unknown-callout" key={i}><CircleAlert size={18}/><span>{u}</span></div>)}<div className="answer-footer"><Info size={15}/> Verbatim source sentences are shown in deterministic demo mode.</div></div><div className="side-results"><div className="mini-panel"><h3>Answer completeness</h3><p className="muted">Each part checked separately</p>{result.completeness.length ? result.completeness.map(c=><div className="component" key={c.component}><span className={`component-icon ${c.status}`}>{c.status==='supported'?<Check size={14}/>:<CircleAlert size={14}/>}</span><div><strong>{c.component==='checklist'&&result.scope.country==='France'?'transfer register':c.component}</strong><small>{c.status} · {c.reason}</small></div></div>) : <p className="muted">No predefined components for this question. Review citations directly.</p>}</div><div className="mini-panel"><h3>Relevant expert</h3>{result.experts.length?result.experts.map(ex=><div className="expert" key={ex.id}><div className="expert-avatar">MV</div><div><strong>{ex.name}</strong><small>{ex.role} · {ex.team}</small></div><p>Suggested from topic-specific activity, not proof of authority.</p>{ex.activities.map(a=><button key={a.id} className="activity" onClick={()=>openEvidence(a.span_id)}><Link2 size={14}/>{a.explanation} <span>· {a.happened_at}</span></button>)}</div>):<p className="muted">No visible topic activity for this country.</p>}</div></div></div> : <ReviewList items={result.review_items} onSource={id=>{setView('sources');setTimeout(()=>document.getElementById(`source-${id}`)?.scrollIntoView({behavior:'smooth'}),50)}}/>}
          <div className="diagnostic"><button onClick={()=>setShowDiagnostics(!showDiagnostics)} aria-expanded={showDiagnostics}><ChevronDown size={16} className={showDiagnostics?'rotated':''}/> Retrieval details and exclusions</button>{showDiagnostics&&<div className="diagnostic-body"><p><strong>Reformulations:</strong> {result.plan.reformulations.join(' · ')}</p><p><strong>Selected spans:</strong> {result.diagnostics.candidate_ids.length} · Query run {result.run_id}</p><h4>Excluded sources</h4>{result.exclusions.length?result.exclusions.map(x=><div key={x.source_id} className="exclusion"><strong>{x.title}</strong><span>{x.reasons.join(' · ')}</span></div>):<p>No ranked exclusions.</p>}</div>}</div>
        </section>}
      </div>}
      {view==='review' && <div className="content narrow"><div className="section-heading"><div className="eyebrow"><span className="eyebrow-line"></span> KNOWLEDGE QUALITY</div><h1>For review<span className="heading-dot">.</span></h1><p>Conflicts, duplicated guidance, outdated versions, and gaps that need a person to resolve.</p></div><ReviewList items={activeReviews} onSource={id=>{setView('sources');setTimeout(()=>document.getElementById(`source-${id}`)?.scrollIntoView({behavior:'smooth'}),50)}}/></div>}
      {view==='sources' && <div className="content narrow"><div className="section-heading"><div className="eyebrow"><span className="eyebrow-line"></span> SOURCE PROVENANCE</div><h1>Source library<span className="heading-dot">.</span></h1><p>Stored originals, versions, owners, scope, and lifecycle status. Every record in this prototype is synthetic.</p></div><div className="library-head"><div><strong>{sources.length} visible sources</strong><span> · filtered for {role} access</span></div><button onClick={()=>{apiFetch('/api/sources',role).then(d=>setSources(d.sources))}}>Refresh list</button></div><div className="source-list">{sources.map(source=><div className="source-row" id={`source-${source.id}`} key={source.id}><div className="source-type"><FileText size={20}/></div><div className="source-main"><strong>{source.title}</strong><div className="source-meta">{source.type} · {source.country || 'Unknown country'} · {source.domain || 'Unknown domain'} · v{source.version} · {source.owner || 'Owner unknown'}</div><div className="source-extra">Effective {source.effective_from || 'unknown'}{source.effective_until && ` → ${source.effective_until}`} · {source.original_name}</div></div><span className={`source-status ${source.status}`}>{source.status}</span><a className="open-link" href={`${API}/api/sources/${encodeURIComponent(source.id)}/original?role=${role}`} target="_blank" rel="noreferrer" aria-label={`Open original ${source.title}`}><ExternalLink size={17}/></a></div>)}</div>{role==='steward'&&<form className="upload-card" onSubmit={upload}><div className="upload-title"><UploadCloud size={20}/><div><h2>Import a demo source</h2><p>PDF, Markdown, text, JSON or email · 2 MB maximum · imports remain drafts</p></div></div><div className="upload-grid"><label>Source ID<input name="id" pattern="[a-zA-Z0-9_-]+" required placeholder="my-source-v1"/></label><label>Title<input name="title" required placeholder="Document title"/></label><label>Type<select name="type"><option value="note">Note</option><option value="procedure">Procedure</option><option value="policy">Policy</option><option value="meeting">Meeting</option><option value="chat">Chat</option><option value="ticket">Ticket</option><option value="email">Email</option></select></label><label>Country<input name="country" required placeholder="Belgium"/></label><label>Domain<input name="domain" required placeholder="Pay"/></label><label>Owner<input name="owner" placeholder="Optional"/></label><label className="file-field">File<input name="file" type="file" required accept=".pdf,.md,.txt,.json,.eml"/></label></div><button className="primary-button" type="submit">Import source <ArrowRight size={16}/></button>{uploadError&&<p className="form-error" role="alert">{uploadError}</p>}{uploadSuccess&&<p className="form-success" role="status">{uploadSuccess}</p>}</form>}</div>}
    </main>
    {selectedEvidence && <div className="modal-backdrop" onMouseDown={e=>{if(e.target===e.currentTarget)setSelectedEvidence(null)}}><div className="evidence-drawer" role="dialog" aria-modal="true" aria-labelledby="evidence-title" tabIndex={-1} ref={dialogRef}><div className="drawer-head"><div><div className="eyebrow small"><span className="eyebrow-line"></span> EXACT EVIDENCE</div><h2 id="evidence-title">Source detail</h2></div><button className="icon-button" aria-label="Close evidence" onClick={()=>setSelectedEvidence(null)}><X size={21}/></button></div><div className="drawer-body"><span className="drawer-kicker">CITED EXCERPT</span><blockquote>{selectedEvidence.excerpt}</blockquote><div className="drawer-info"><h3>{selectedEvidence.source.title}</h3><p>{selectedEvidence.location} · Version {selectedEvidence.source.version}</p><div className="detail-row"><span>Source type</span><strong>{selectedEvidence.source.type}</strong></div><div className="detail-row"><span>Owner</span><strong>{selectedEvidence.source.owner || 'Unknown'}</strong></div><div className="detail-row"><span>Approval</span><strong>{selectedEvidence.source.status}</strong></div><div className="detail-row"><span>Scope</span><strong>{[selectedEvidence.source.country,selectedEvidence.source.domain,selectedEvidence.source.client].filter(Boolean).join(' · ')}</strong></div><div className="detail-row"><span>Effective from</span><strong>{selectedEvidence.source.effective_from || 'Unknown'}</strong></div><div className="detail-row"><span>Effective until</span><strong>{selectedEvidence.source.effective_until || 'Open / unknown'}</strong></div><div className="detail-row"><span>Original</span><strong>{selectedEvidence.source.original_name}</strong></div></div></div><div className="drawer-foot"><a className="primary-button" href={`${API}/api/sources/${encodeURIComponent(selectedEvidence.source.id)}/original?span_id=${encodeURIComponent(selectedEvidence.id)}&role=${role}`} target="_blank" rel="noreferrer">Open stored original <ExternalLink size={16}/></a><small>Opens the local original, with cited text highlighted where available.</small></div></div></div>}
  </div>
}

function ReviewList({items,onSource}:{items:Review[];onSource:(id:string)=>void}) {
  const order = ['missing_knowledge','conflicts','exact_duplicate','near_duplicate','outdated','missing_metadata']
  const grouped = order.map(kind=>({kind,items:items.filter(i=>i.kind===kind)})).filter(g=>g.items.length)
  return <div className="review-list">{grouped.length?grouped.map(group=><section className="review-group" key={group.kind}><div className="review-group-heading"><h3>{group.items[0].label}</h3><span>{group.items.length}</span></div>{group.items.map(item=><div className="review-card" key={item.id}><div className={`review-symbol ${item.kind}`}><CircleAlert size={18}/></div><div><strong>{item.title}</strong><p>{item.action}</p>{item.source_ids.length>0&&<div className="review-links">{item.source_ids.map(id=><button key={id} onClick={()=>onSource(id)}><Link2 size={13}/>{id}</button>)}</div>}</div></div>)}</section>):<div className="empty-state"><Check size={24}/><p>No review items visible for this context.</p></div>}</div>
}

const container = document.getElementById('root') as (HTMLElement & { reactRoot?: Root })
const root = container.reactRoot || createRoot(container)
container.reactRoot = root
root.render(<React.StrictMode><App/></React.StrictMode>)
