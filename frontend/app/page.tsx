"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, type Project, type ProviderProbe, type Style } from "@/lib/api";

export default function Home() {
  const router = useRouter();
  const [projects, setProjects] = useState<Project[]>([]);
  const [providers, setProviders] = useState<ProviderProbe[]>([]);
  const [templates, setTemplates] = useState<{ id: string; title: string; description: string }[]>([]);
  const [styles, setStyles] = useState<Style[]>([]);
  const [health, setHealth] = useState<string>("…");
  const [name, setName] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [instantiating, setInstantiating] = useState("");

  // prompt → video
  const [prompt, setPrompt] = useState("");
  const [pStyle, setPStyle] = useState("anime_cyberpunk");
  const [pScenes, setPScenes] = useState(8);
  const [pSafe, setPSafe] = useState(false);
  const [genBusy, setGenBusy] = useState(false);
  const llmReady = providers.some((p) => p.capability === "llm" && p.selected && p.available);

  async function refresh() {
    try {
      const [h, p, prj, tpl, sty] = await Promise.all([
        api.health(),
        api.providers(),
        api.listProjects(),
        api.listTemplates(),
        api.styles(),
      ]);
      setHealth(`${h.status} · v${h.version} · ${h.languages.join("/")}`);
      setProviders(p.providers);
      setProjects(prj);
      setTemplates(tpl);
      setStyles(sty);
      setErr("");
    } catch (e) {
      setErr(`Backend not reachable at the API base. Start it: uvicorn app.main:app --port 8000  (${String(e)})`);
      setHealth("offline");
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setBusy(true);
    try {
      await api.createProject({ name: name.trim() });
      setName("");
      await refresh();
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function generateFromPrompt(e: React.FormEvent) {
    e.preventDefault();
    if (!prompt.trim()) return;
    setGenBusy(true);
    setErr("");
    try {
      const res = await api.fromPrompt({
        prompt: prompt.trim(), style_preset: pStyle, scenes: pScenes,
        safe_mode: pSafe, render: true,
      });
      router.push(`/projects/${res.project.id}/storyboard`);
    } catch (e) {
      setErr(String(e));
      setGenBusy(false);
    }
  }

  async function useTemplate(templateId: string) {
    setInstantiating(templateId);
    setErr("");
    try {
      const res = await api.instantiateTemplate(templateId);
      router.push(`/projects/${res.project.id}/storyboard`);
    } catch (e) {
      setErr(String(e));
      setInstantiating("");
    }
  }

  return (
    <div>
      <div className="spread">
        <h1>Projects</h1>
        <span className={`badge ${health.startsWith("ok") ? "ok" : "err"}`}>backend: {health}</span>
      </div>

      {err && <p className="error">{err}</p>}

      <form className="panel" onSubmit={generateFromPrompt}>
        <div className="spread">
          <h3 style={{ margin: 0 }}>🎬 Create a video from a prompt</h3>
          <span className={`badge ${llmReady ? "ok" : "warn"}`}>
            {llmReady ? "LLM ready" : "needs OPENROUTER_API_KEY"}
          </span>
        </div>
        <p className="muted" style={{ marginTop: 4 }}>
          One topic → the AI writes the song (lyrics + chorus), invents the characters, plans the
          scenes, then you render & export the full music video.
        </p>
        <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)}
          placeholder="e.g. a brave little robot who lights up a neon city at night" />
        <div className="row" style={{ marginTop: 10, flexWrap: "wrap", gap: 14, alignItems: "end" }}>
          <div>
            <label>Style</label>
            <select value={pStyle} onChange={(e) => setPStyle(e.target.value)} style={{ width: "auto" }}>
              {styles.map((s) => <option key={s.id} value={s.id}>{s.id}</option>)}
            </select>
          </div>
          <div>
            <label>Scenes</label>
            <select value={pScenes} onChange={(e) => setPScenes(Number(e.target.value))} style={{ width: "auto" }}>
              {[4, 6, 8, 10, 12].map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </div>
          <label className="row" style={{ margin: 0, width: "auto", color: "var(--text)" }} title="block violent/scary content (off = any genre)">
            <input type="checkbox" checked={pSafe} onChange={(e) => setPSafe(e.target.checked)} style={{ width: "auto", marginRight: 6 }} />
            child-safe
          </label>
          <button disabled={genBusy || !prompt.trim() || !llmReady}>
            {genBusy ? "writing the song…" : "Generate"}
          </button>
        </div>
        {!llmReady && (
          <p className="caption" style={{ textAlign: "left", marginTop: 8 }}>
            Add a free OpenRouter key to <code>backend/.env</code>:{" "}
            <code>OPENROUTER_API_KEY=sk-or-…</code> then restart the backend.
          </p>
        )}
      </form>

      {templates.length > 0 && (
        <div className="panel">
          <h3>Start from a template</h3>
          <div className="grid cols-2">
            {templates.map((t) => (
              <div key={t.id} className="card">
                <div className="spread">
                  <strong>{t.title}</strong>
                  <button onClick={() => useTemplate(t.id)} disabled={!!instantiating}>
                    {instantiating === t.id ? "creating…" : "Use"}
                  </button>
                </div>
                <div className="muted" style={{ marginTop: 6 }}>{t.description}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="panel">
        <h3>Providers ready on this machine</h3>
        <div className="pill-list">
          {providers.map((p) => (
            <span
              key={`${p.capability}:${p.provider}`}
              className={`badge ${p.available ? "ok" : "warn"}`}
              title={p.available ? p.reason : `${p.reason} — ${p.install_hint}`}
            >
              {p.available ? "●" : "○"} {p.capability}:{p.provider}
              {p.selected ? " ★" : ""}
            </span>
          ))}
          {providers.length === 0 && <span className="muted">—</span>}
        </div>
      </div>

      <form className="panel" onSubmit={create}>
        <h3>New project</h3>
        <div className="row">
          <input
            placeholder="Project name (e.g. Nursery Rhymes S1)"
            value={name}
            onChange={(e) => setName(e.target.value)}
            style={{ maxWidth: 380 }}
          />
          <button disabled={busy || !name.trim()}>Create</button>
        </div>
      </form>

      <div className="grid cols-2">
        {projects.map((p) => (
          <a key={p.id} href={`/projects/${p.id}`} className="card">
            <div className="spread">
              <strong>{p.name}</strong>
              <span className="badge">{p.style_preset}</span>
            </div>
            <div className="muted mono">{p.language} · {p.width}×{p.height} · {p.fps}fps</div>
          </a>
        ))}
        {projects.length === 0 && !err && (
          <p className="muted">No projects yet — create one above.</p>
        )}
      </div>
    </div>
  );
}
