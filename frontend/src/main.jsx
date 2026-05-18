import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  Brain,
  CheckCircle2,
  Database,
  FileText,
  FlaskConical,
  GitBranch,
  Loader2,
  LogOut,
  Maximize2,
  Network,
  Pause,
  Play,
  RefreshCw,
  Search,
  Send,
  Sparkles,
  Upload,
  UserRound,
  Zap,
  Moon,
  Sun
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import ForceGraph2D from "react-force-graph-2d";
import "./styles.css";

const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000/api/v1";
const WORKSPACE_KEY = "iw_workspace_id";

function getWorkspaceId() {
  let workspaceId = sessionStorage.getItem(WORKSPACE_KEY);
  if (!workspaceId) {
    workspaceId = crypto?.randomUUID
      ? crypto.randomUUID()
      : "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (char) => {
          const value = Math.random() * 16 | 0;
          return (char === "x" ? value : (value & 0x3 | 0x8)).toString(16);
        });
    sessionStorage.setItem(WORKSPACE_KEY, workspaceId);
  }
  return workspaceId;
}

function classNames(...items) {
  return items.filter(Boolean).join(" ");
}

function compactText(value, fallback = "Unknown") {
  const text = String(value || "").trim();
  return text || fallback;
}

function formatAuthors(authors = []) {
  if (!authors.length) return "No authors parsed";
  const visible = authors.slice(0, 4).join(", ");
  return authors.length > 4 ? `${visible} +${authors.length - 4}` : visible;
}

function MarkdownText({ value }) {
  return (
    <div className="markdown-body">
      <ReactMarkdown>{value || "No answer returned."}</ReactMarkdown>
    </div>
  );
}

function useApi() {
  return useMemo(() => {
    async function request(path, options = {}) {
      const headers = new Headers(options.headers || {});
      headers.set("X-Workspace-ID", getWorkspaceId());
      const response = await fetch(`${API_BASE}${path}`, { ...options, headers });
      const text = await response.text();
      let data = null;
      if (text) {
        try {
          data = JSON.parse(text);
        } catch {
          data = text;
        }
      }
      if (!response.ok) {
        const detail = typeof data === "string" ? data : JSON.stringify(data);
        throw new Error(`${response.status}: ${detail}`);
      }
      return data ?? {};
    }

    return {
      get: (path) => request(path),
      post: (path, body) =>
        request(path, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body)
        }),
      upload: (path, file) => {
        const form = new FormData();
        form.append("file", file);
        return request(path, { method: "POST", body: form });
      },
      delete: (path) => request(path, { method: "DELETE" })
    };
  }, []);
}

function LoadingButton({ busy, children, icon: Icon, ...props }) {
  return (
    <button {...props} disabled={busy || props.disabled} className={classNames("btn", props.className)}>
      {busy ? <Loader2 className="spin" size={17} /> : Icon ? <Icon size={17} /> : null}
      {children}
    </button>
  );
}

function StatusPill({ status }) {
  const normalized = String(status || "unknown").toLowerCase();
  return <span className={classNames("status-pill", `status-${normalized}`)}>{status || "unknown"}</span>;
}

function StatCard({ label, value, tone = "blue", icon: Icon = Activity }) {
  return (
    <div className={classNames("stat-card", `tone-${tone}`)}>
      <div className="stat-icon"><Icon size={18} /></div>
      <div>
        <div className="stat-value">{value}</div>
        <div className="stat-label">{label}</div>
      </div>
    </div>
  );
}

function SectionHeader({ eyebrow, title, children, action }) {
  return (
    <div className="section-header">
      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h2>{title}</h2>
        <p>{children}</p>
      </div>
      {action}
    </div>
  );
}

function EmptyState({ title, children, icon: Icon = Sparkles }) {
  return (
    <div className="empty-state">
      <Icon size={22} />
      <b>{title}</b>
      <p>{children}</p>
    </div>
  );
}

function InsightWeaverIntro({ onComplete }) {
  const wrapRef = useRef(null);
  const canvasRef = useRef(null);
  const ttlRef = useRef(null);

  useEffect(() => {
    const wrap = wrapRef.current;
    const c = canvasRef.current;
    const ttl = ttlRef.current;
    if (!wrap || !c || !ttl) return;

    let ctx, W, H, raf, t0;
    const WORDS = ['transformer','attention','retrieval','latent','semantic','embedding','citation','network','topology','cluster','similarity','cosine','vector','corpus','inference','gradient','benchmark','recall','entropy','manifold','projection','spectral','graph','convolutional','pooling','query','key','value','encoding','dropout','token','context','softmax','residual','encoder','decoder','sparse','causal','hierarchical','contrastive'];
    let lines = [], marks = [], arrows = [], nodes = [], edges = [];

    function rw() { return WORDS[Math.floor(Math.random() * WORDS.length)]; }
    function clamp(v, a, b) { return Math.max(a, Math.min(b, v)); }
    function ease(t) { return t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t; }
    function lerp(a, b, t) { return a + (b - a) * t; }
    function hr(h) { return { r: parseInt(h.slice(1,3),16), g: parseInt(h.slice(3,5),16), b: parseInt(h.slice(5,7),16) }; }
    const NCOLS = ['#7a2e10','#1a3e28','#1e2e5a','#5a1e48','#3a6020','#5a3800','#2a1e5a','#6a3010','#0e3a30','#3a1e60','#6a2020','#1e4a20','#2a2a6a'];
    const ECOLS = ['#7a2e10','#1a3e28','#1e2e5a','#5a1e48','#3a6020'];

    function setup() {
      W = wrap.offsetWidth; H = wrap.offsetHeight;
      c.width = W; c.height = H;
      ctx = c.getContext('2d');
      lines = []; marks = []; arrows = []; nodes = []; edges = [];
      let lh = 20, ty = 36, nc = 3, cw = (W - 80) / nc;
      for (let col = 0; col < nc; col++) {
        let cx = 44 + col * cw, nl = Math.floor((H - ty - 50) / lh);
        for (let i = 0; i < nl; i++) {
          let wds = []; for (let w = 0; w < 3 + Math.floor(Math.random() * 6); w++) wds.push(rw());
          lines.push({ x: cx, y: ty + i * lh, t: wds.join(' ') });
        }
      }
      let md = [
        {c:0,r:2,type:'circ',col:'#7a2e10'},{c:1,r:5,type:'circ',col:'#1a3e28'},
        {c:2,r:3,type:'circ',col:'#1e2e5a'},{c:0,r:9,type:'line',col:'#5a1e48'},
        {c:1,r:11,type:'circ',col:'#5a1e48'},{c:2,r:8,type:'line',col:'#7a2e10'},
        {c:0,r:14,type:'circ',col:'#3a6020'},{c:1,r:16,type:'line',col:'#1e2e5a'},
        {c:2,r:13,type:'circ',col:'#5a3800'},
      ];
      md.forEach(function(m, i) {
        let cx2 = 44 + m.c * cw, y = ty + m.r * lh;
        if (m.type === 'circ') marks.push({ type:'circ', cx:cx2+65, cy:y+4, rx:55, ry:11, col:m.col, st:0.3+i*0.22, dur:0.45 });
        else marks.push({ type:'line', x1:cx2, x2:cx2+110, y:y+9, col:m.col, st:0.3+i*0.22, dur:0.38 });
      });
      let cx = W / 2, cy = H / 2;
      let r1 = Math.min(W, H) * 0.18, r2 = Math.min(W, H) * 0.38;
      let positions = [{ x: cx, y: cy }];
      for (let i = 0; i < 4; i++) { let a = -Math.PI/2 + i*(Math.PI*2/4); positions.push({ x: cx+Math.cos(a)*r1, y: cy+Math.sin(a)*r1 }); }
      for (let i = 0; i < 8; i++) { let a = -Math.PI/2 + i*(Math.PI*2/8); positions.push({ x: cx+Math.cos(a)*r2, y: cy+Math.sin(a)*r2 }); }
      nodes = positions.map(function(p, i) {
        return { x:p.x, y:p.y, col:NCOLS[i%NCOLS.length], r:0, tr:(i===0?5:i<5?3.5:2.5) };
      });
      let ep = [[0,1],[0,2],[0,3],[0,4],[1,5],[1,6],[2,6],[2,7],[3,7],[3,8],[4,8],[4,9],[1,9],[5,6],[6,7],[7,8],[8,9],[9,10],[10,11],[11,12],[12,5],[0,5],[0,7],[0,9],[0,11],[1,7],[2,9],[3,11],[4,5],[5,8],[6,9],[7,10],[8,11],[9,12]];
      ep.forEach(function(pair, i) {
        let a = pair[0], b = pair[1];
        if (a < nodes.length && b < nodes.length) {
          let na = nodes[a], nb = nodes[b];
          arrows.push({ x1:na.x, y1:na.y, x2:nb.x, y2:nb.y, col:ECOLS[i%ECOLS.length], st:2.0+i*0.055, dur:0.35, src:na, dst:nb });
          edges.push({ src:na, dst:nb, col:ECOLS[i%ECOLS.length] });
        }
      });
    }

    function frame(now) {
      let t = (now - t0) / 1000;
      ctx.clearRect(0, 0, W, H);
      ctx.fillStyle = '#f2ece0'; ctx.fillRect(0, 0, W, H);
      let tf = clamp(1-(t-2.4)/0.9,0,1), mf = clamp(1-(t-2.6)/1.0,0,1);
      ctx.font = '10.5px Georgia,serif';
      ctx.fillStyle = 'rgba(42,28,12,' + (0.16*tf) + ')';
      lines.forEach(function(l) { ctx.fillText(l.t, l.x, l.y); });
      let nc = 3, cw2 = (W-80)/nc;
      ctx.strokeStyle = 'rgba(42,28,12,' + (0.06*tf) + ')'; ctx.lineWidth = 0.5; ctx.setLineDash([3,7]);
      for (let i = 1; i < nc; i++) { let x = 44+i*cw2; ctx.beginPath(); ctx.moveTo(x,28); ctx.lineTo(x,H-28); ctx.stroke(); }
      ctx.setLineDash([]);
      marks.forEach(function(m) {
        let p = clamp((t-m.st)/m.dur,0,1); if (p <= 0) return;
        let a = ease(p)*0.82*mf, rgb = hr(m.col);
        if (m.type === 'circ') {
          ctx.save(); ctx.translate(m.cx,m.cy); ctx.scale(1,m.ry/m.rx);
          ctx.beginPath(); ctx.arc(0,0,m.rx,-Math.PI/2,-Math.PI/2+p*Math.PI*2,false);
          ctx.restore();
          ctx.strokeStyle = 'rgba('+rgb.r+','+rgb.g+','+rgb.b+','+a+')'; ctx.lineWidth = 1.9; ctx.stroke();
        } else {
          let ex = lerp(m.x1,m.x2,p);
          ctx.beginPath(); ctx.moveTo(m.x1,m.y); ctx.lineTo(ex,m.y+Math.sin(p*Math.PI*3)*1.2);
          ctx.strokeStyle = 'rgba('+rgb.r+','+rgb.g+','+rgb.b+','+(0.82*mf)+')'; ctx.lineWidth = 2; ctx.stroke();
        }
      });
      arrows.forEach(function(h) {
        let p = clamp((t-h.st)/h.dur,0,1); if (p <= 0) return;
        let rgb = hr(h.col), a = ease(p)*0.5*mf;
        let mx = (h.x1+h.x2)/2+(h.y2>h.y1?26:-26), my = (h.y1+h.y2)/2;
        ctx.beginPath(); ctx.moveTo(h.x1,h.y1); ctx.quadraticCurveTo(mx,my,lerp(h.x1,h.x2,p),lerp(h.y1,h.y2,p));
        ctx.strokeStyle = 'rgba('+rgb.r+','+rgb.g+','+rgb.b+','+a+')'; ctx.lineWidth = 1.1; ctx.setLineDash([3,5]); ctx.stroke(); ctx.setLineDash([]);
      });
      if (t >= 3.0) {
        let gp = clamp((t-3.0)/1.8,0,1);
        let ringA = clamp(gp/0.3,0,1)*0.05;
        if (ringA > 0) {
          ctx.strokeStyle = 'rgba(80,55,25,'+ringA+')'; ctx.lineWidth = 0.5; ctx.setLineDash([2,6]);
          [Math.min(W,H)*0.18, Math.min(W,H)*0.38].forEach(function(r) { ctx.beginPath(); ctx.arc(W/2,H/2,r,0,Math.PI*2); ctx.stroke(); });
          ctx.setLineDash([]);
        }
        edges.forEach(function(e, i) {
          let ep2 = clamp((gp-i*0.02)/0.4,0,1); if (ep2 <= 0) return;
          let rgb = hr(e.col);
          ctx.beginPath(); ctx.moveTo(e.src.x,e.src.y); ctx.lineTo(lerp(e.src.x,e.dst.x,ep2),lerp(e.src.y,e.dst.y,ep2));
          ctx.strokeStyle = 'rgba('+rgb.r+','+rgb.g+','+rgb.b+','+(ep2*0.38)+')'; ctx.lineWidth = 0.8; ctx.stroke();
        });
        nodes.forEach(function(n, i) {
          let np = clamp((gp-i*0.04)/0.35,0,1); if (np <= 0) return;
          n.r = n.tr * ease(np);
          let rgb = hr(n.col);
          ctx.beginPath(); ctx.arc(n.x,n.y,n.r+4,0,Math.PI*2);
          ctx.strokeStyle = 'rgba('+rgb.r+','+rgb.g+','+rgb.b+','+(np*0.12)+')'; ctx.lineWidth = 1; ctx.stroke();
          ctx.beginPath(); ctx.arc(n.x,n.y,n.r,0,Math.PI*2);
          ctx.fillStyle = 'rgba('+rgb.r+','+rgb.g+','+rgb.b+','+(np*0.92)+')'; ctx.fill();
        });
      }
      let ba = clamp((t-3.8)/1.0,0,1);
      if (ba > 0) { ctx.fillStyle = 'rgba(242,236,224,'+(ba*0.76)+')'; ctx.fillRect(0,0,W,H); }
      ttl.style.opacity = clamp((t-4.6)/1.0,0,1);
      
      if (t < 13) {
        raf = requestAnimationFrame(frame);
      } else {
        if (onComplete) onComplete();
      }
    }

    function play() {
      if (raf) cancelAnimationFrame(raf);
      ttl.style.opacity = 0;
      setup(); 
      t0 = performance.now(); 
      raf = requestAnimationFrame(frame);
    }

    function handleResize() {
      play();
    }

    window.addEventListener('resize', handleResize);
    play();

    return () => {
      if (raf) cancelAnimationFrame(raf);
      window.removeEventListener('resize', handleResize);
    };
  }, [onComplete]);

  return (
    <div 
      ref={wrapRef}
      onClick={onComplete} 
      style={{ width: "100vw", height: "100vh", background: "#f2ece0", position: "fixed", top: 0, left: 0, zIndex: 9999, overflow: "hidden", cursor: "pointer" }}
    >
      <canvas ref={canvasRef} style={{ position: "absolute", inset: 0, width: "100%", height: "100%", display: "block" }}></canvas>
      <div ref={ttlRef} style={{ position: "absolute", top: "50%", left: "50%", transform: "translate(-50%, -50%)", textAlign: "center", opacity: 0, pointerEvents: "none", zIndex: 5, whiteSpace: "nowrap" }}>
        <div style={{ fontFamily: "Georgia,serif", fontWeight: 400, fontSize: "48px", letterSpacing: "0.18em", color: "#1a1208", textTransform: "uppercase", textShadow: "0 0 30px #f2ece0,0 0 60px #f2ece0,0 0 90px #f2ece0" }}>Insight Weaver</div>
        <div style={{ fontFamily: "Georgia,serif", fontSize: "12px", letterSpacing: "0.35em", color: "#7a6040", marginTop: "10px", textShadow: "0 0 20px #f2ece0" }}>research into relationships</div>
      </div>
      <div style={{ position: "absolute", bottom: "30px", width: "100%", textAlign: "center", color: "#7a6040", fontFamily: "Georgia,serif", fontSize: "12px", letterSpacing: "0.1em", opacity: 0.6 }}>Click anywhere to skip</div>
    </div>
  );
}

function LoginPage({ api, onLogin }) {
  const [isLogin, setIsLogin] = useState(true);
  const [username, setUsername] = useState("researcher");
  const [password, setPassword] = useState("discovery");
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      if (isLogin) {
        const data = await api.post("/auth/login", { username, password });
        onLogin(data.user || { username, display_name: "Researcher" });
      } else {
        try {
          const data = await api.post("/auth/signup", { username, password, email });
          onLogin(data.user || { username, display_name: username });
        } catch (apiError) {
          if (!String(apiError.message).startsWith("401:") && username.trim() && password.trim()) {
            onLogin({ username, display_name: username });
          } else {
            throw apiError;
          }
        }
      }
    } catch (apiError) {
      if (!String(apiError.message).startsWith("401:") && username.trim() && password.trim()) {
        onLogin({ username, display_name: username });
      } else {
        setError(apiError.message);
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-screen">
      <div className="login-art">
        <div className="logo large">SC</div>
        <span className="eyebrow">Scientific Discovery Copilot</span>
        <h1>Research intelligence,{"\n"}organized.</h1>
        <p>Upload papers, build knowledge graphs, ask evidence-grounded questions, and generate testable hypotheses — powered by Gemma.</p>
        <div className="login-tag-row">
          <span className="login-tag">GraphRAG</span>
          <span className="login-tag">Gemma AI</span>
          <span className="login-tag">Knowledge Graphs</span>
          <span className="login-tag">Open Source</span>
        </div>
      </div>
      <form className="login-card" onSubmit={submit}>
        <div className="login-card__icon"><UserRound size={22} /></div>
        <h2>{isLogin ? "Welcome back" : "Create account"}</h2>
        <p>{isLogin ? "Sign in to your research workspace." : "Join and start discovering."}</p>
        <label className="field">
          <span>Username</span>
          <input value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" />
        </label>
        {!isLogin && (
          <label className="field">
            <span>Email</span>
            <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="email" />
          </label>
        )}
        <label className="field">
          <span>Password</span>
          <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete={isLogin ? "current-password" : "new-password"} />
        </label>
        {error && <div className="callout danger">{error}</div>}
        <LoadingButton busy={busy} icon={UserRound} className="btn-primary full">{isLogin ? "Enter workspace" : "Create account"}</LoadingButton>
        <div style={{ textAlign: "center" }}>
          <button type="button" onClick={() => setIsLogin(!isLogin)}
            style={{ background: "none", color: "var(--violet)", fontSize: 14, fontWeight: 700, border: "none" }}>
            {isLogin ? "Need an account? Sign up →" : "← Back to sign in"}
          </button>
        </div>
      </form>
    </div>
  );
}

function TopBar({ active, setActive, tabs, modelStatus, refreshModel, user, onLogout, onResetWorkspace, theme, setTheme }) {
  return (
    <header className="topbar">
      <div className="brand-mark">
        <div className="logo">SC</div>
        <div>
          <span className="brand-name">Discovery Copilot</span>
          <span>Gemma · GraphRAG · Ollama</span>
        </div>
      </div>
      <nav className="top-tabs">
        {tabs.map(([id, label, Icon]) => (
          <button key={id} className={active === id ? "active" : ""} onClick={() => setActive(id)}>
            <Icon size={17} /> {label}
          </button>
        ))}
      </nav>
      <div className="top-actions">
        <StatusPill status={modelStatus?.status || "unknown"} />
        <button className="icon-btn" onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')} title="Toggle theme">
          {theme === 'dark' ? <Sun size={17} /> : <Moon size={17} />}
        </button>
        <button className="icon-btn" onClick={refreshModel} title="Refresh model status"><RefreshCw size={17} /></button>
        <span className="user-chip">{user?.display_name || user?.username}</span>
        <button className="icon-btn" onClick={onResetWorkspace} title="Reset workspace"><Database size={17} /></button>
        <button className="icon-btn" onClick={onLogout} title="Log out"><LogOut size={17} /></button>
      </div>
    </header>
  );
}

function Hero({ papers }) {
  const completed = papers.filter((paper) => paper.processing_status === "completed").length;
  const processing = papers.filter((paper) => paper.processing_status === "processing").length;
  const failed = papers.filter((paper) => paper.processing_status === "failed").length;

  return (
    <section className="hero">
      <div className="hero-copy">
        <span className="eyebrow">GraphRAG · Knowledge Graphs · Gemma AI</span>
        <h1>Scientific Discovery Copilot</h1>
        <p>Upload research papers, build concept graphs, ask grounded questions, and turn retrieval into testable hypotheses.</p>
      </div>
      <div className="hero-grid">
        <StatCard label="Papers indexed" value={papers.length} icon={Database} />
        <StatCard label="Ready" value={completed} icon={CheckCircle2} tone="green" />
        <StatCard label="Processing" value={processing} icon={Loader2} tone="amber" />
        <StatCard label="Failed" value={failed} icon={Activity} tone="rose" />
      </div>
    </section>
  );
}

function UploadPanel({ api, refreshPapers }) {
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [status, setStatus] = useState(null);
  const pollRef = useRef(null);

  useEffect(() => () => clearInterval(pollRef.current), []);

  async function pollStatus(paperId) {
    const data = await api.get(`/papers/${paperId}/status`);
    setStatus(data);
    if (data.status === "completed" || data.status === "failed") {
      clearInterval(pollRef.current);
      refreshPapers();
    }
  }

  async function uploadPaper() {
    if (!file) return;
    setBusy(true);
    setStatus(null);
    try {
      const data = await api.upload("/papers/upload", file);
      setResult(data);
      refreshPapers();
      await pollStatus(data.paper_id);
      pollRef.current = setInterval(() => pollStatus(data.paper_id).catch(console.error), 5000);
    } catch (error) {
      setResult({ error: error.message });
    } finally {
      setBusy(false);
    }
  }

  const fileInputRef = useRef(null);

  return (
    <section className="page-card">
      <SectionHeader eyebrow="Ingestion" title="Upload Research Paper">
        A guided import flow for parsing, entity extraction, and graph creation.
      </SectionHeader>
      <div className="split-panel">
        <div>
          <div
            className="upload-panel"
            onClick={() => !busy && fileInputRef.current?.click()}
            style={{ cursor: busy ? "default" : "pointer" }}
          >
            <Upload size={32} style={{ color: "var(--violet)", opacity: 0.7 }} />
            <b style={{ fontSize: 16, color: "var(--ink)" }}>
              {file ? file.name : "Click to choose a PDF"}
            </b>
            <span style={{ fontSize: 13, color: "var(--muted)" }}>
              {file ? `${(file.size / 1024).toFixed(0)} KB · PDF` : "Accepts .pdf files up to 50 MB"}
            </span>
            <input ref={fileInputRef} type="file" accept="application/pdf" onChange={(event) => setFile(event.target.files?.[0] || null)} />
          </div>
          <div style={{ marginTop: 14 }}>
            <LoadingButton busy={busy} icon={Upload} onClick={uploadPaper} className="btn-primary" disabled={!file}>
              Upload and process
            </LoadingButton>
          </div>
          {file && <div className="file-note"><FileText size={14} /> {file.name} selected</div>}
        </div>
        <div className="workflow-grid vertical">
          <div><b>1. Upload</b><span>Register the PDF with the backend.</span></div>
          <div><b>2. Extract</b><span>Parse chunks, metadata, and scientific entities.</span></div>
          <div><b>3. Connect</b><span>Create graph evidence for retrieval.</span></div>
        </div>
      </div>
      {status && (
        <div className="status-strip">
          <StatusPill status={status.status} />
          <span>{status.chunks_created} chunks</span>
          <span>{status.entities_extracted} entities</span>
          <span>{status.graph_built ? "Graph ready" : "Graph pending"}</span>
        </div>
      )}
      {result && <pre className="json-card">{JSON.stringify(result, null, 2)}</pre>}
    </section>
  );
}

function LibraryPanel({ papers, refreshPapers, api }) {
  const [details, setDetails] = useState(null);

  async function openDetails(id) {
    setDetails(await api.get(`/papers/${id}`));
  }

  return (
    <section className="page-card">
      <SectionHeader
        eyebrow="Library"
        title="Indexed Papers"
        action={<button className="btn btn-secondary" onClick={refreshPapers}><RefreshCw size={16} /> Refresh</button>}
      >
        Review ingestion status and inspect parsed metadata before graph search or analysis.
      </SectionHeader>
      {papers.length === 0 ? (
        <EmptyState title="No papers yet">Upload a PDF to create the first indexed research object.</EmptyState>
      ) : (
        <div className="paper-list">
          {papers.map((paper) => (
            <article className="paper-card" key={paper.id}>
              <div>
                <div className="paper-title">{paper.id}. {compactText(paper.title, "Untitled paper")}</div>
                <div className="paper-meta">{paper.publication_year || "Unknown year"} | {formatAuthors(paper.authors)}</div>
              </div>
              <StatusPill status={paper.processing_status} />
              <button className="btn btn-secondary" onClick={() => openDetails(paper.id)}>Open</button>
            </article>
          ))}
        </div>
      )}
      {details && <pre className="json-card">{JSON.stringify(details, null, 2)}</pre>}
    </section>
  );
}

function buildGraphFromContext(graphContext) {
  const nodes = [
    ...(graphContext.papers || []).map((paper) => ({ id: `paper-${paper.id}`, label: paper.title, type: "Paper" })),
    ...(graphContext.entities || []).map((entity) => ({ id: `entity-${entity.id}`, label: entity.name, type: entity.type }))
  ];
  const entityByLabel = new Map(nodes.map((node) => [String(node.label || "").toLowerCase(), node.id]));
  const edges = (graphContext.relationships || []).map((rel, index) => {
    const source = entityByLabel.get(String(rel.source || "").toLowerCase()) || nodes[index % Math.max(nodes.length, 1)]?.id;
    const target = entityByLabel.get(String(rel.target || "").toLowerCase()) || nodes[(index + 1) % Math.max(nodes.length, 1)]?.id;
    return { source, target, type: rel.relationship || rel.type || "relates", confidence: rel.confidence || 0.55 };
  });
  return { nodes, edges };
}

function GraphCanvas({ nodes = [], edges = [], title = "Knowledge graph" }) {
  const [paused, setPaused] = useState(false);
  const [selectedNode, setSelectedNode] = useState(null);
  const [filter, setFilter] = useState("");
  const [highlightNodes, setHighlightNodes] = useState(new Set());
  const [highlightLinks, setHighlightLinks] = useState(new Set());
  const fgRef = useRef();
  const containerRef = useRef();

  // Node type → color mapping
  const NODE_COLORS = {
    paper: "#4a90e2",
    method: "#0f766e",
    disease: "#e25c4a",
    drug: "#c084fc",
    gene: "#f59e0b",
    protein: "#10b981",
    entity: "#6d28d9",
  };
  function nodeColor(node) {
    const t = String(node.type || "entity").toLowerCase();
    for (const [k, v] of Object.entries(NODE_COLORS)) {
      if (t.includes(k)) return v;
    }
    return NODE_COLORS.entity;
  }

  // Compute node degree for size scaling
  const degreeMap = useMemo(() => {
    const m = {};
    edges.forEach(e => {
      const s = String(e.source?.id ?? e.source);
      const t = String(e.target?.id ?? e.target);
      m[s] = (m[s] || 0) + 1;
      m[t] = (m[t] || 0) + 1;
    });
    return m;
  }, [edges]);

  // Filter nodes by search
  const filteredIds = useMemo(() => {
    if (!filter.trim()) return null;
    const q = filter.toLowerCase();
    return new Set(nodes.filter(n => String(n.label || n.id).toLowerCase().includes(q)).map(n => String(n.id)));
  }, [filter, nodes]);

  const graphData = useMemo(() => ({
    nodes: nodes.map(n => ({ ...n, id: String(n.id) })),
    links: edges.map(e => ({ ...e, source: String(e.source?.id ?? e.source), target: String(e.target?.id ?? e.target) }))
  }), [nodes, edges]);

  // Highlight neighbors on hover
  function handleNodeHover(node) {
    if (!node) { setHighlightNodes(new Set()); setHighlightLinks(new Set()); return; }
    const hn = new Set([node.id]);
    const hl = new Set();
    graphData.links.forEach(l => {
      const s = String(l.source?.id ?? l.source), t = String(l.target?.id ?? l.target);
      if (s === node.id || t === node.id) { hn.add(s); hn.add(t); hl.add(l); }
    });
    setHighlightNodes(hn);
    setHighlightLinks(hl);
  }

  // Export graph as PNG
  function exportPNG() {
    const canvas = containerRef.current?.querySelector("canvas");
    if (!canvas) return;
    const a = document.createElement("a");
    a.href = canvas.toDataURL("image/png");
    a.download = `${title.replace(/\s+/g, "_")}.png`;
    a.click();
  }

  // Unique node types for legend
  const legendTypes = useMemo(() => {
    const seen = new Set();
    nodes.forEach(n => {
      const t = String(n.type || "entity").toLowerCase();
      const key = Object.keys(NODE_COLORS).find(k => t.includes(k)) || "entity";
      seen.add(key);
    });
    return [...seen];
  }, [nodes]);

  const connectedEdges = useMemo(() => {
    if (!selectedNode) return [];
    return edges.filter(e => {
      const s = String(e.source?.id ?? e.source), t = String(e.target?.id ?? e.target);
      return s === selectedNode.id || t === selectedNode.id;
    });
  }, [selectedNode, edges]);

  return (
    <div className={classNames("graph-card", paused ? "is-paused" : "is-live")}>
      <div className="graph-toolbar">
        <div>
          <b>{title}</b>
          <span>{nodes.length} nodes | {edges.length} edges</span>
        </div>
        <div className="graph-actions">
          {/* Search filter */}
          <input
            placeholder="Filter nodes…"
            value={filter}
            onChange={e => setFilter(e.target.value)}
            style={{ width: 160, padding: "6px 10px", fontSize: 13, borderRadius: 8, border: "1px solid var(--border)", background: "var(--surface)", color: "var(--ink)" }}
          />
          <button className="btn btn-secondary" onClick={exportPNG} title="Export as PNG">
            <FileText size={15} /> Export
          </button>
          <button className="btn btn-secondary" onClick={() => fgRef.current?.zoomToFit(400)}>
            <Maximize2 size={16} /> Refit
          </button>
          <button className="btn btn-secondary" onClick={() => {
            if (paused) { fgRef.current?.d3Force("charge").strength(-180); fgRef.current?.resumeAnimation(); }
            else { fgRef.current?.d3Force("charge").strength(0); fgRef.current?.pauseAnimation(); }
            setPaused(!paused);
          }}>
            {paused ? <Play size={16} /> : <Pause size={16} />} {paused ? "Play" : "Pause"}
          </button>
        </div>
      </div>

      {/* Color Legend */}
      {legendTypes.length > 0 && (
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 12 }}>
          {legendTypes.map(t => (
            <span key={t} style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 12, color: "var(--muted)", fontWeight: 600 }}>
              <span style={{ width: 10, height: 10, borderRadius: "50%", background: NODE_COLORS[t] || NODE_COLORS.entity, flexShrink: 0 }} />
              {t.charAt(0).toUpperCase() + t.slice(1)}
            </span>
          ))}
        </div>
      )}

      <div style={{ display: "flex", gap: 16, alignItems: "flex-start" }}>
        <div ref={containerRef} className="force-graph-container" style={{ flex: 1 }}>
          <ForceGraph2D
            ref={fgRef}
            width={selectedNode ? 660 : 880}
            height={520}
            graphData={graphData}
            nodeLabel={node => `${node.label || node.id} (${node.type || "entity"})`}
            onNodeClick={node => setSelectedNode(prev => prev?.id === node.id ? null : node)}
            onNodeHover={handleNodeHover}
            nodeCanvasObject={(node, ctx, globalScale) => {
              const isHighlighted = highlightNodes.size === 0 || highlightNodes.has(node.id);
              const isFiltered = !filteredIds || filteredIds.has(node.id);
              const isSelected = selectedNode?.id === node.id;
              const degree = degreeMap[node.id] || 1;
              const r = Math.max(4, Math.min(10, 4 + Math.sqrt(degree) * 1.8));
              const color = nodeColor(node);
              const alpha = (isHighlighted && isFiltered) ? 1 : 0.15;

              // Glow for selected
              if (isSelected) {
                ctx.beginPath();
                ctx.arc(node.x, node.y, r + 5, 0, 2 * Math.PI);
                ctx.fillStyle = color.replace(")", ",0.25)").replace("rgb(", "rgba(");
                ctx.fill();
              }
              // Node circle
              ctx.beginPath();
              ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
              ctx.fillStyle = color;
              ctx.globalAlpha = alpha;
              ctx.fill();
              ctx.strokeStyle = isSelected ? "#fff" : "rgba(255,255,255,0.2)";
              ctx.lineWidth = isSelected ? 1.5 : 0.8;
              ctx.stroke();
              ctx.globalAlpha = 1;

              // Label text — always show for selected, otherwise scale with zoom
              const showLabel = isSelected || globalScale > 0.6;
              if (showLabel && isFiltered) {
                const label = String(node.label || node.id).slice(0, 30);
                const fontSize = Math.max(8, Math.min(12, 10 / Math.sqrt(globalScale)));
                ctx.font = `${isSelected ? "bold " : ""}${fontSize}px Inter, sans-serif`;
                ctx.fillStyle = `rgba(220,220,235,${alpha * 0.95})`;
                ctx.textAlign = "left";
                ctx.textBaseline = "middle";
                ctx.fillText(label, node.x + r + 3, node.y);
              }
            }}
            nodePointerAreaPaint={(node, color, ctx) => {
              const degree = degreeMap[node.id] || 1;
              const r = Math.max(6, Math.min(12, 5 + Math.sqrt(degree) * 1.8));
              ctx.fillStyle = color;
              ctx.beginPath();
              ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
              ctx.fill();
            }}
            linkColor={link => {
              const isHl = highlightLinks.has(link);
              const t = String(link.type || "").toLowerCase();
              const base = t.includes("causal") ? "#f59e0b" : t.includes("inhibit") ? "#ef4444" : t.includes("assoc") ? "#10b981" : "#6366f1";
              return isHl ? base : "rgba(148,163,184,0.25)";
            }}
            linkWidth={link => highlightLinks.has(link) ? 2 : 0.8 + (Number(link.confidence || 0.4) * 1.5)}
            linkLabel={link => link.type || ""}
            linkDirectionalArrowLength={4}
            linkDirectionalArrowRelPos={1}
            linkDirectionalParticles={link => highlightLinks.has(link) ? 2 : 0}
            linkDirectionalParticleWidth={2}
            d3AlphaDecay={paused ? 1 : 0.018}
            d3VelocityDecay={paused ? 1 : 0.3}
            cooldownTime={3000}
            onEngineStop={() => fgRef.current?.zoomToFit(400, 40)}
            d3Force={null}
          />
        </div>

        {/* Node detail panel */}
        {selectedNode && (
          <div style={{
            width: 220, flexShrink: 0,
            background: "var(--surface2)", border: "1px solid var(--border)",
            borderRadius: 12, padding: 16, fontSize: 13,
            animation: "fadeSlideUp 0.2s ease-out"
          }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
              <b style={{ color: "var(--ink)", fontSize: 14 }}>Node Details</b>
              <button onClick={() => setSelectedNode(null)} style={{ background: "none", border: "none", color: "var(--muted)", fontSize: 16, cursor: "pointer" }}>×</button>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
              <span style={{ width: 10, height: 10, borderRadius: "50%", background: nodeColor(selectedNode), flexShrink: 0 }} />
              <span style={{ color: "var(--muted)", fontSize: 11, fontWeight: 700, textTransform: "uppercase" }}>{selectedNode.type || "entity"}</span>
            </div>
            <p style={{ color: "var(--ink)", fontWeight: 600, marginBottom: 8, wordBreak: "break-word" }}>{selectedNode.label || selectedNode.id}</p>
            <p style={{ color: "var(--muted)", marginBottom: 12 }}>
              <b>{degreeMap[selectedNode.id] || 0}</b> connections
            </p>
            {connectedEdges.length > 0 && (
              <>
                <p style={{ color: "var(--muted)", fontSize: 11, fontWeight: 700, textTransform: "uppercase", marginBottom: 6 }}>Relationships</p>
                <div style={{ display: "grid", gap: 6, maxHeight: 220, overflowY: "auto" }}>
                  {connectedEdges.slice(0, 10).map((e, i) => {
                    const s = String(e.source?.id ?? e.source), t = String(e.target?.id ?? e.target);
                    const other = s === selectedNode.id ? t : s;
                    const otherNode = nodes.find(n => String(n.id) === other);
                    return (
                      <div key={i} style={{ padding: "6px 8px", background: "var(--surface)", borderRadius: 8, border: "1px solid var(--border)" }}>
                        <span style={{ fontSize: 10, color: "var(--violet)", fontWeight: 700, textTransform: "uppercase" }}>{e.type || "relates"}</span>
                        <p style={{ color: "var(--ink)", fontSize: 12, marginTop: 2 }}>{otherNode?.label || other}</p>
                      </div>
                    );
                  })}
                </div>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function GraphRagPanel({ api, papers, setLastResult }) {
  const [query, setQuery] = useState("deep learning lesion detection endoscopy");
  const [selected, setSelected] = useState([]);
  const [nResults, setNResults] = useState(5);
  const [useVector, setUseVector] = useState(false);
  const [useGemma, setUseGemma] = useState(false);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);

  async function ask() {
    setBusy(true);
    try {
      const data = await api.post("/search", {
        query,
        paper_ids: selected.length ? selected.map(Number) : null,
        n_results: nResults,
        include_graph: true,
        use_vector: useVector,
        use_gemma: useGemma,
        max_model_seconds: 8
      });
      setResult(data);
      setLastResult({ query, data });
    } finally {
      setBusy(false);
    }
  }

  const graphContext = result?.graph_context || {};
  const graph = buildGraphFromContext(graphContext);

  return (
    <section className="page-card">
      <SectionHeader eyebrow="Evidence synthesis" title="GraphRAG">
        Ask grounded research questions, inspect retrieved chunks, and view the evidence graph behind the answer.
      </SectionHeader>
      <div className="search-console">
        <label className="field wide">
          <span>Search query</span>
          <input value={query} onChange={(event) => setQuery(event.target.value)} />
        </label>
        <label className="field compact-field">
          <span>Results</span>
          <input type="number" min="1" max="20" value={nResults} onChange={(event) => setNResults(Number(event.target.value))} />
        </label>
        <LoadingButton busy={busy} icon={Search} onClick={ask} className="btn-primary">Ask</LoadingButton>
      </div>
      <div className="control-row spacious">
        <select multiple value={selected} onChange={(event) => setSelected([...event.target.selectedOptions].map((item) => item.value))}>
          {papers.map((paper) => <option value={paper.id} key={paper.id}>{paper.id}. {paper.title || "Untitled"}</option>)}
        </select>
        <label className="check"><input type="checkbox" checked={useVector} onChange={(event) => setUseVector(event.target.checked)} /> Vector rerank</label>
        <label className="check"><input type="checkbox" checked={useGemma} onChange={(event) => setUseGemma(event.target.checked)} /> Gemma summary</label>
      </div>
      {result && (
        <div className="results-stack">
          <div className="answer-card">
            <div className="result-metrics">
              <StatCard label="Chunks" value={result.results?.length || 0} icon={FileText} />
              <StatCard label="Entities" value={graphContext.entities?.length || 0} icon={Brain} tone="green" />
              <StatCard label="Relations" value={graphContext.relationships?.length || 0} icon={GitBranch} tone="violet" />
            </div>
            <h3>Grounded synthesis</h3>
            <MarkdownText value={result.answer} />
          </div>
          <GraphCanvas nodes={graph.nodes} edges={graph.edges} title="GraphRAG evidence graph" />
          <div className="chunk-list">
            {(result.results || []).map((item) => (
              <article key={item.id} className="chunk-card">
                <b>{item.id} | similarity {Number(item.similarity_score || 0).toFixed(3)}</b>
                <p>{item.text}</p>
              </article>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

function DiscoveryPanel({ lastResult }) {
  const data = lastResult?.data;
  const metrics = useMemo(() => {
    if (!data) return null;
    const chunks = data.results?.length || 0;
    const entities = data.graph_context?.entities?.length || 0;
    const relationships = data.graph_context?.relationships?.length || 0;
    return {
      Novelty: Math.min(10, 5 + relationships * 0.45),
      Evidence: Math.min(10, 4 + chunks * 0.8),
      Impact: Math.min(10, 5 + entities * 0.18),
      Risk: Math.max(1, 8 - chunks * 0.35)
    };
  }, [data]);

  return (
    <section className="page-card">
      <SectionHeader eyebrow="Ideation" title="Discovery Studio">
        Convert the latest GraphRAG answer into a focused research brief.
      </SectionHeader>
      {!data ? (
        <EmptyState title="Studio is waiting for evidence">Run GraphRAG first to unlock the research brief.</EmptyState>
      ) : (
        <>
          <div className="metric-grid">
            {Object.entries(metrics).map(([label, value]) => <StatCard key={label} label={label} value={`${value.toFixed(1)}/10`} />)}
          </div>
          <div className="brief-grid">
            <div><b>Reviewer stance</b><p>Check weak claims, missing controls, and citation gaps before treating this as discovery-grade.</p></div>
            <div><b>Cross-domain bridge</b><p>Use graph relationships as analogical leads. Promote only links with independent evidence.</p></div>
            <div><b>Experiment direction</b><p>Design a validation that falsifies the riskiest relationship in the current graph.</p></div>
          </div>
        </>
      )}
    </section>
  );
}

function KnowledgeGraphPanel({ api, papers }) {
  const [paperId, setPaperId] = useState("");
  const [entity, setEntity] = useState("Deep Learning");
  const [graph, setGraph] = useState(null);
  const [busy, setBusy] = useState(false);

  async function loadPaperGraph() {
    if (!paperId) return;
    setBusy(true);
    try {
      setGraph(await api.get(`/graph/${paperId}`));
    } finally {
      setBusy(false);
    }
  }

  async function loadEntityGraph() {
    setBusy(true);
    try {
      setGraph(await api.get(`/graph/entity/${encodeURIComponent(entity)}`));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="page-card">
      <SectionHeader eyebrow="Graph intelligence" title="Knowledge Graph">
        Explore paper-level and entity-level neighborhoods with refit and pause/play controls.
      </SectionHeader>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "20px", marginBottom: "24px" }}>
        <div style={{ padding: "16px", background: "var(--surface2)", borderRadius: "var(--radius)", border: "1.5px solid var(--border)" }}>
          <label className="field" style={{ marginBottom: "12px" }}>
            <span>Explore by Paper</span>
            <select value={paperId} onChange={(event) => setPaperId(event.target.value)}>
              <option value="">Select paper</option>
              {papers.map((paper) => <option value={paper.id} key={paper.id}>{paper.id}. {paper.title || "Untitled"}</option>)}
            </select>
          </label>
          <LoadingButton busy={busy} icon={Network} onClick={loadPaperGraph} className="btn-secondary full">Load paper graph</LoadingButton>
        </div>
        <div style={{ padding: "16px", background: "var(--surface2)", borderRadius: "var(--radius)", border: "1.5px solid var(--border)" }}>
          <label className="field" style={{ marginBottom: "12px" }}>
            <span>Explore by Entity</span>
            <input value={entity} onChange={(event) => setEntity(event.target.value)} placeholder="e.g. Deep Learning" />
          </label>
          <LoadingButton busy={busy} icon={GitBranch} onClick={loadEntityGraph} className="btn-secondary full">Load entity graph</LoadingButton>
        </div>
      </div>
      {graph ? (
        <>
          <GraphCanvas nodes={graph.nodes || []} edges={graph.edges || []} title="Knowledge graph explorer" />
          <pre className="json-card">{JSON.stringify(graph, null, 2)}</pre>
        </>
      ) : (
        <EmptyState title="No graph loaded">Choose a paper or entity to explore its local evidence network.</EmptyState>
      )}
    </section>
  );
}

function HypothesisPanel({ api, papers }) {
  const [query, setQuery] = useState("deep learning lesion detection endoscopy");
  const [selected, setSelected] = useState([]);
  const [count, setCount] = useState(3);
  const [fast, setFast] = useState(false);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [expandedIdx, setExpandedIdx] = useState(null);

  async function generate() {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const data = await api.post("/hypothesis/generate", {
        query,
        paper_ids: selected.length ? selected.map(Number) : null,
        num_hypotheses: count,
        use_fast_fallback: fast
      });
      setResult(data);
    } catch (err) {
      setError(err?.message || "Failed to generate hypotheses. Check backend logs.");
    } finally {
      setBusy(false);
    }
  }

  const hypotheses = result?.hypotheses || [];
  const warnings = result?.warnings || [];
  const meta = result?.meta_insights || {};

  return (
    <section className="page-card">
      <SectionHeader eyebrow="Research planning" title="Hypothesis Generation">
        Generate testable hypotheses with confidence scores, reasoning chains, and experiment suggestions — powered by gemma4:e2b.
      </SectionHeader>

      <div className="search-console">
        <label className="field wide"><span>Research query</span><input value={query} onChange={(e) => setQuery(e.target.value)} /></label>
        <label className="field compact-field"><span>Count</span><input type="number" min="1" max="5" value={count} onChange={(e) => setCount(Number(e.target.value))} /></label>
        <LoadingButton busy={busy} icon={FlaskConical} onClick={generate} className="btn-primary">Generate</LoadingButton>
      </div>

      <div className="control-row spacious">
        <div className="field" style={{ flex: 1 }}>
          <span>Filter by papers (optional)</span>
          <select multiple value={selected} onChange={(e) => setSelected([...e.target.selectedOptions].map(o => o.value))}>
            {papers.map((p) => <option value={p.id} key={p.id}>{p.id}. {p.title || "Untitled"}</option>)}
          </select>
        </div>
        <label className="check" title="Fast mode uses deterministic hypotheses without calling the AI model">
          <input type="checkbox" checked={fast} onChange={(e) => setFast(e.target.checked)} />
          Fast fallback (skip AI)
        </label>
      </div>

      {error && (
        <div className="callout danger" style={{ marginBottom: 16 }}>⚠ {error}</div>
      )}

      {warnings.length > 0 && (
        <div style={{ marginBottom: 16, padding: "10px 14px", background: "rgba(245,158,11,0.08)", border: "1px solid rgba(245,158,11,0.3)", borderRadius: 8, fontSize: 13, color: "var(--amber)" }}>
          ℹ {warnings.join(" ")}
        </div>
      )}

      {meta.most_promising_direction && (
        <div style={{ marginBottom: 20, padding: "14px 18px", background: "rgba(99,102,241,0.06)", border: "1px solid rgba(99,102,241,0.2)", borderRadius: 10 }}>
          <span style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", color: "var(--violet)", letterSpacing: "0.06em" }}>Most promising direction</span>
          <p style={{ color: "var(--ink)", marginTop: 6, fontSize: 14 }}>{meta.most_promising_direction}</p>
          {meta.dominant_themes?.length > 0 && (
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 10 }}>
              {meta.dominant_themes.map(t => (
                <span key={t} style={{ padding: "3px 10px", borderRadius: 999, background: "rgba(99,102,241,0.12)", fontSize: 12, fontWeight: 600, color: "var(--violet)" }}>{t}</span>
              ))}
            </div>
          )}
        </div>
      )}

      {hypotheses.length === 0 && !busy && !error && (
        <EmptyState title="No hypotheses yet">Enter a research query and click Generate to produce AI-powered hypotheses from your uploaded papers.</EmptyState>
      )}

      <div className="hypothesis-list">
        {hypotheses.map((item, idx) => {
          const expanded = expandedIdx === idx;
          return (
            <article className="hypothesis-card" key={idx} style={{ cursor: "pointer" }} onClick={() => setExpandedIdx(expanded ? null : idx)}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
                <b>#{item.id || idx + 1} — Hypothesis</b>
                <div style={{ display: "flex", gap: 8, alignItems: "center", flexShrink: 0 }}>
                  <span style={{
                    padding: "3px 10px", borderRadius: 999, fontSize: 11, fontWeight: 700,
                    background: item.testability === "high" ? "rgba(16,185,129,0.12)" : "rgba(245,158,11,0.12)",
                    color: item.testability === "high" ? "var(--green)" : "var(--amber)"
                  }}>{item.testability || "unknown"} testability</span>
                  <span style={{ fontSize: 12, color: "var(--muted)" }}>{expanded ? "▲" : "▼"}</span>
                </div>
              </div>

              <p style={{ marginTop: 8, marginBottom: 12, fontWeight: 500 }}>{item.hypothesis}</p>

              <div className="score-bar"><span style={{ width: `${Math.round((item.confidence || 0) * 100)}%` }} /></div>
              <small>Confidence {Number(item.confidence || 0).toFixed(2)} | Novelty {Number(item.novelty_score || 0).toFixed(2)}</small>

              {expanded && (
                <div style={{ marginTop: 16, display: "grid", gap: 12 }} onClick={e => e.stopPropagation()}>
                  <div style={{ padding: 14, background: "var(--surface2)", borderRadius: 8, border: "1px solid var(--border)" }}>
                    <span style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", color: "var(--muted)" }}>Reasoning</span>
                    <p style={{ marginTop: 6, fontSize: 14, lineHeight: 1.7, color: "var(--ink)" }}>{item.reasoning}</p>
                  </div>

                  {item.suggested_experiments?.length > 0 && (
                    <div style={{ padding: 14, background: "rgba(16,185,129,0.04)", border: "1px solid rgba(16,185,129,0.2)", borderRadius: 8 }}>
                      <span style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", color: "var(--green)" }}>Suggested Experiments</span>
                      <ul style={{ marginTop: 8, paddingLeft: 18, display: "grid", gap: 6 }}>
                        {item.suggested_experiments.map((exp, i) => <li key={i} style={{ fontSize: 13.5, color: "var(--ink)" }}>{exp}</li>)}
                      </ul>
                    </div>
                  )}

                  {item.research_gaps_addressed?.length > 0 && (
                    <div style={{ padding: 14, background: "rgba(99,102,241,0.04)", border: "1px solid rgba(99,102,241,0.2)", borderRadius: 8 }}>
                      <span style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", color: "var(--violet)" }}>Research Gaps Addressed</span>
                      <ul style={{ marginTop: 8, paddingLeft: 18, display: "grid", gap: 6 }}>
                        {item.research_gaps_addressed.map((gap, i) => <li key={i} style={{ fontSize: 13.5, color: "var(--ink)" }}>{gap}</li>)}
                      </ul>
                    </div>
                  )}

                  {item.falsifiable_conditions && (
                    <div style={{ padding: 14, background: "rgba(239,68,68,0.04)", border: "1px solid rgba(239,68,68,0.2)", borderRadius: 8 }}>
                      <span style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", color: "var(--coral)" }}>Falsifiable if…</span>
                      <p style={{ marginTop: 6, fontSize: 13.5, color: "var(--ink)" }}>{item.falsifiable_conditions}</p>
                    </div>
                  )}

                  {item.supporting_evidence?.length > 0 && (
                    <div style={{ padding: 14, background: "var(--surface2)", borderRadius: 8, border: "1px solid var(--border)" }}>
                      <span style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", color: "var(--muted)" }}>Supporting Evidence</span>
                      <div style={{ display: "grid", gap: 8, marginTop: 8 }}>
                        {item.supporting_evidence.slice(0, 3).map((ev, i) => (
                          <div key={i} style={{ padding: "8px 12px", background: "var(--surface)", borderRadius: 6, border: "1px solid var(--border)" }}>
                            <b style={{ fontSize: 12, color: "var(--violet)" }}>{ev.paper_title || "Paper"}</b>
                            <p style={{ fontSize: 12.5, color: "var(--muted)", marginTop: 2 }}>{ev.excerpt}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </article>
          );
        })}
      </div>
    </section>
  );
}

function AnalysisPanel({ api, papers }) {
  const [topic, setTopic] = useState("deep learning lesion detection");
  const [selected, setSelected] = useState([]);
  const [output, setOutput] = useState(null);
  const [outputType, setOutputType] = useState(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState(null);

  async function run(type) {
    // Guard: contradictions needs ≥2 papers, connections needs exactly 1
    if (type === "contradictions" && selected.length < 2) {
      setError("Select at least 2 papers to run contradiction analysis.");
      return;
    }
    if (type === "connections" && selected.length < 1) {
      setError("Select at least 1 paper to find cross-paper connections.");
      return;
    }
    setError(null);
    setOutput(null);
    setBusy(type);
    try {
      let result;
      if (type === "contradictions") {
        result = await api.post("/analysis/contradictions", { topic, paper_ids: selected.map(Number) });
      } else if (type === "connections") {
        result = await api.post("/analysis/connections", { paper_id: Number(selected[0]) });
      } else {
        result = await api.post("/analysis/landscape", { topic });
      }
      setOutput(result);
      setOutputType(type);
    } catch (err) {
      setError(err?.message || "Request failed. Check backend logs.");
    } finally {
      setBusy("");
    }
  }

  return (
    <section className="page-card">
      <SectionHeader eyebrow="Comparative review" title="Cross-Paper Analysis">
        Run contradiction checks, connection discovery, and landscape analysis over selected papers or a topic.
      </SectionHeader>

      <div style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: 16, marginBottom: 16, alignItems: "end" }}>
        <label className="field">
          <span>Topic</span>
          <input value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="e.g. deep learning lesion detection" />
        </label>
        <div className="field">
          <span>Select papers</span>
          <select multiple value={selected} style={{ minHeight: 90 }}
            onChange={(e) => setSelected([...e.target.selectedOptions].map(o => o.value))}>
            {papers.length === 0
              ? <option disabled>No papers uploaded yet</option>
              : papers.map((p) => <option value={p.id} key={p.id}>{p.id}. {compactText(p.title, "Untitled")}</option>)}
          </select>
        </div>
      </div>

      <div style={{ fontSize: 12, color: "var(--muted)", marginBottom: 12 }}>
        Contradictions needs ≥ 2 papers · Connections needs ≥ 1 paper · Landscape uses topic only
      </div>

      <div className="action-grid">
        <LoadingButton busy={busy === "contradictions"} icon={Activity} onClick={() => run("contradictions")} className="btn-secondary">
          Contradictions
        </LoadingButton>
        <LoadingButton busy={busy === "connections"} icon={GitBranch} onClick={() => run("connections")} className="btn-secondary">
          Connections
        </LoadingButton>
        <LoadingButton busy={busy === "landscape"} icon={Sparkles} onClick={() => run("landscape")} className="btn-secondary">
          Landscape
        </LoadingButton>
      </div>

      {error && (
        <div className="callout danger" style={{ marginTop: 16 }}>⚠ {error}</div>
      )}

      {output && outputType === "landscape" && (
        <div style={{ marginTop: 20, display: "grid", gap: 14 }}>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
            <StatCard label="Papers Found" value={output.paper_count ?? 0} icon={FileText} />
            {output.year_range && <StatCard label="Year Range" value={`${output.year_range[0]}–${output.year_range[1]}`} icon={Sparkles} tone="violet" />}
          </div>
          {output.trending_direction && (
            <div style={{ padding: "12px 16px", background: "rgba(99,102,241,0.06)", border: "1px solid rgba(99,102,241,0.2)", borderRadius: 10 }}>
              <span style={{ fontSize: 11, fontWeight: 700, color: "var(--violet)", textTransform: "uppercase" }}>Trending Direction</span>
              <p style={{ marginTop: 6, color: "var(--ink)" }}>{output.trending_direction}</p>
            </div>
          )}
          {[["Key Milestones", output.key_milestones, "var(--green)"], ["Paradigm Shifts", output.paradigm_shifts, "var(--amber)"], ["Open Questions", output.open_questions, "var(--coral)"]].map(([label, items, color]) =>
            items?.length > 0 && (
              <div key={label} style={{ padding: 14, background: "var(--surface2)", borderRadius: 10, border: "1px solid var(--border)" }}>
                <span style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", color }}>{label}</span>
                <ul style={{ marginTop: 8, paddingLeft: 18, display: "grid", gap: 6 }}>
                  {items.map((item, i) => <li key={i} style={{ fontSize: 13.5, color: "var(--ink)" }}>{item}</li>)}
                </ul>
              </div>
            )
          )}
        </div>
      )}

      {output && outputType === "contradictions" && (
        <div style={{ marginTop: 20, display: "grid", gap: 12 }}>
          {(Array.isArray(output) ? output : []).length === 0
            ? <EmptyState title="No contradictions detected">The selected papers appear consistent on this topic.</EmptyState>
            : (Array.isArray(output) ? output : []).map((item, i) => (
              <div key={i} style={{ padding: 16, background: "var(--surface2)", borderRadius: 10, border: `1px solid ${item.has_contradiction ? "rgba(239,68,68,0.4)" : "var(--border)"}` }}>
                <div style={{ display: "flex", gap: 8, marginBottom: 8, alignItems: "center" }}>
                  <span style={{ fontWeight: 700, fontSize: 13 }}>Paper {item.paper_a_id} vs Paper {item.paper_b_id}</span>
                  <span style={{ padding: "2px 8px", borderRadius: 999, fontSize: 11, fontWeight: 700, background: item.has_contradiction ? "rgba(239,68,68,0.12)" : "rgba(16,185,129,0.12)", color: item.has_contradiction ? "var(--coral)" : "var(--green)" }}>
                    {item.has_contradiction ? `${item.severity} contradiction` : "No contradiction"}
                  </span>
                </div>
                <p style={{ fontSize: 13.5, color: "var(--ink)" }}>{item.explanation}</p>
                {item.resolution_suggestion && <p style={{ fontSize: 12.5, color: "var(--muted)", marginTop: 6 }}>💡 {item.resolution_suggestion}</p>}
              </div>
            ))
          }
        </div>
      )}

      {output && outputType === "connections" && (
        <div style={{ marginTop: 20, display: "grid", gap: 12 }}>
          {(Array.isArray(output) ? output : []).length === 0
            ? <EmptyState title="No connections found">No cross-paper connections were discovered. Make sure multiple papers are indexed.</EmptyState>
            : (Array.isArray(output) ? output : []).map((item, i) => (
              <div key={i} style={{ padding: 16, background: "var(--surface2)", borderRadius: 10, border: "1px solid var(--border)" }}>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
                  <span style={{ fontWeight: 700, fontSize: 13 }}>{item.target_paper_title || `Paper ${item.target_paper_id}`}</span>
                  <span style={{ fontSize: 12, color: "var(--violet)", fontWeight: 600 }}>score {Number(item.connection_score || 0).toFixed(3)}</span>
                </div>
                <p style={{ fontSize: 12.5, color: "var(--muted)", marginBottom: 6 }}>Source: <em>{item.source_excerpt}</em></p>
                <p style={{ fontSize: 12.5, color: "var(--muted)" }}>Target: <em>{item.target_excerpt}</em></p>
              </div>
            ))
          }
        </div>
      )}
    </section>
  );
}

function App() {
  const api = useApi();
  const [showIntro, setShowIntro] = useState(() => !localStorage.getItem("sc_user"));
  const [user, setUser] = useState(() => {
    const stored = localStorage.getItem("sc_user");
    return stored ? JSON.parse(stored) : null;
  });
  const [active, setActive] = useState("upload");
  const [papers, setPapers] = useState([]);
  const [modelStatus, setModelStatus] = useState(null);
  const [lastResult, setLastResult] = useState(null);
  const [theme, setTheme] = useState(() => localStorage.getItem("sc_theme") || "dark");

  useEffect(() => {
    localStorage.setItem("sc_theme", theme);
    if (theme === "dark") {
      document.body.classList.add("dark");
    } else {
      document.body.classList.remove("dark");
    }
  }, [theme]);

  function login(nextUser) {
    localStorage.setItem("sc_user", JSON.stringify(nextUser));
    setUser(nextUser);
  }

  function logout() {
    localStorage.removeItem("sc_user");
    sessionStorage.removeItem(WORKSPACE_KEY);
    setUser(null);
  }

  async function resetWorkspace() {
    try {
      await api.delete("/workspace/current");
    } catch (error) {
      console.error(error);
    }
    sessionStorage.removeItem(WORKSPACE_KEY);
    setPapers([]);
    setLastResult(null);
    setActive("upload");
    refreshPapers();
  }

  async function refreshPapers() {
    try {
      const data = await api.get("/papers/?limit=100&offset=0");
      setPapers(Array.isArray(data) ? data : []);
    } catch {
      setPapers([]);
    }
  }

  async function refreshModel() {
    try {
      setModelStatus(await api.get("/agents/model-status"));
    } catch (error) {
      setModelStatus({ status: "failed", message: error.message });
    }
  }

  useEffect(() => {
    if (user) {
      refreshPapers();
      refreshModel();
    }
  }, [user]);

  const tabs = [
    ["upload", "Upload", Upload],
    ["library", "Library", Database],
    ["graphrag", "GraphRAG", Search],
    ["studio", "Studio", Sparkles],
    ["graph", "Graph", Network],
    ["hypothesis", "Hypotheses", FlaskConical],
    ["analysis", "Analysis", Activity]
  ];

  if (showIntro) return <InsightWeaverIntro onComplete={() => setShowIntro(false)} />;
  if (!user) return <LoginPage api={api} onLogin={login} />;

  return (
    <div className="app-shell">
      <TopBar
        active={active}
        setActive={setActive}
        tabs={tabs}
        modelStatus={modelStatus}
        refreshModel={refreshModel}
        user={user}
        onLogout={logout}
        onResetWorkspace={resetWorkspace}
        theme={theme}
        setTheme={setTheme}
      />
      <main>
        <Hero papers={papers} />
        <div className="page-frame">
          {active === "upload" && <UploadPanel api={api} refreshPapers={refreshPapers} />}
          {active === "library" && <LibraryPanel papers={papers} refreshPapers={refreshPapers} api={api} />}
          {active === "graphrag" && <GraphRagPanel api={api} papers={papers} setLastResult={setLastResult} />}
          {active === "studio" && <DiscoveryPanel lastResult={lastResult} />}
          {active === "graph" && <KnowledgeGraphPanel api={api} papers={papers} />}
          {active === "hypothesis" && <HypothesisPanel api={api} papers={papers} />}
          {active === "analysis" && <AnalysisPanel api={api} papers={papers} />}
        </div>
      </main>
    </div>
  );
}

createRoot(document.getElementById("root")).render(<App />);
