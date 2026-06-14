"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, type Project, type ProviderProbe } from "@/lib/api";

export default function ProjectsPage() {
  const router = useRouter();
  const [projects, setProjects] = useState<Project[]>([]);
  const [providers, setProviders] = useState<ProviderProbe[]>([]);
  const [templates, setTemplates] = useState<{ id: string; title: string; description: string }[]>([]);
  const [health, setHealth] = useState("…");
  const [name, setName] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [instantiating, setInstantiating] = useState("");

  async function refresh() {
    try {
      const [h, p, prj, tpl] = await Promise.all([
        api.health(), api.providers(), api.listProjects(), api.listTemplates(),
      ]);
      setHealth(`${h.status} · v${h.version} · ${h.languages.join("/")}`);
      setProviders(p.providers);
      setProjects(prj);
      setTemplates(tpl);
      setErr("");
    } catch (e) {
      setErr(`Backend not reachable — start it on port 8000.  (${String(e)})`);
      setHealth("offline");
    }
  }

  useEffect(() => { refresh(); }, []);

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
        <h1>📁 Projects</h1>
        <span className={`badge ${health.startsWith("ok") ? "ok" : "err"}`}>backend: {health}</span>
      </div>

      {err && <p className="error">{err}</p>}

      <div className="grid cols-2" style={{ marginTop: 14 }}>
        {projects.map((p) => (
          <a key={p.id} href={`/projects/${p.id}`} className="card">
            <div className="spread">
              <strong>{p.name}</strong>
              <span className="badge">{p.style_preset}</span>
            </div>
            <div className="muted mono" style={{ marginTop: 6 }}>{p.language} · {p.width}×{p.height} · {p.fps}fps</div>
          </a>
        ))}
        {projects.length === 0 && !err && (
          <p className="muted">No projects yet — create one from a prompt on the <a href="/">home page</a>, or below.</p>
        )}
      </div>

      <form className="panel" onSubmit={create}>
        <h3>New blank project</h3>
        <div className="row">
          <input placeholder="Project name (e.g. Nursery Rhymes S1)" value={name}
            onChange={(e) => setName(e.target.value)} style={{ maxWidth: 380 }} />
          <button disabled={busy || !name.trim()}>Create</button>
        </div>
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
            <span key={`${p.capability}:${p.provider}`}
              className={`badge ${p.available ? "ok" : "warn"}`}
              title={p.available ? p.reason : `${p.reason} — ${p.install_hint}`}>
              {p.available ? "●" : "○"} {p.capability}:{p.provider}{p.selected ? " ★" : ""}
            </span>
          ))}
          {providers.length === 0 && <span className="muted">—</span>}
        </div>
      </div>
    </div>
  );
}
