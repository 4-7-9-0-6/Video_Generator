"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, API_BASE, type Job, type ProviderProbe, type Style } from "@/lib/api";

export default function Home() {
  const router = useRouter();
  const [providers, setProviders] = useState<ProviderProbe[]>([]);
  const [styles, setStyles] = useState<Style[]>([]);
  const [err, setErr] = useState("");

  const [prompt, setPrompt] = useState("");
  const [pStyle, setPStyle] = useState("anime_cyberpunk");
  const [pScenes, setPScenes] = useState(6);
  const [pSafe, setPSafe] = useState(false);
  const [mode, setMode] = useState<"fast" | "gpu">("fast");

  const [genBusy, setGenBusy] = useState(false);     // fast (CPU) flow
  const [gpuAvail, setGpuAvail] = useState<{ available: boolean; hint: string } | null>(null);
  const [gpuJob, setGpuJob] = useState<Job | null>(null);
  const [gpuBusy, setGpuBusy] = useState(false);
  const [gpuVideoId, setGpuVideoId] = useState<string | null>(null);

  const llmReady = providers.some((p) => p.capability === "llm" && p.selected && p.available);
  const ready = mode === "fast" ? llmReady : !!gpuAvail?.available;
  const busy = mode === "fast" ? genBusy : gpuBusy;

  useEffect(() => {
    Promise.all([api.providers(), api.styles()])
      .then(([p, sty]) => { setProviders(p.providers); setStyles(sty); setErr(""); })
      .catch((e) => setErr(`Backend not reachable — start it on port 8000.  (${String(e)})`));
    api.gpuVideoAvailability().then(setGpuAvail).catch(() => setGpuAvail(null));
  }, []);

  async function onCreate() {
    if (!prompt.trim() || busy) return;
    if (mode === "gpu") return generateOnGpu();
    setGenBusy(true);
    setErr("");
    try {
      const res = await api.fromPrompt({
        prompt: prompt.trim(), style_preset: pStyle, scenes: pScenes, safe_mode: pSafe, render: true,
      });
      router.push(`/projects/${res.project.id}/storyboard`);
    } catch (e) {
      setErr(String(e));
      setGenBusy(false);
    }
  }

  async function generateOnGpu() {
    setGpuBusy(true);
    setErr("");
    setGpuVideoId(null);
    setGpuJob(null);
    try {
      const { job } = await api.gpuVideo({ prompt: prompt.trim(), style_preset: pStyle, scenes: pScenes });
      setGpuJob(job);
      let cur = job;
      while (cur.status === "queued" || cur.status === "running") {
        await new Promise((r) => setTimeout(r, 15000));
        cur = await api.getJob(job.id);
        setGpuJob(cur);
      }
      if (cur.status === "succeeded") {
        const assetId = cur.result?.asset_id as string | undefined;
        if (assetId) setGpuVideoId(assetId);
      } else {
        setErr(`GPU render ${cur.status}: ${cur.error || cur.message}`);
      }
    } catch (e) {
      setErr(String(e));
    } finally {
      setGpuBusy(false);
    }
  }

  const modeCard = (m: "fast" | "gpu", emoji: string, title: string, sub: string) => (
    <button type="button" onClick={() => setMode(m)} className={mode === m ? "" : "ghost"}
      style={{ textAlign: "left", padding: "12px 14px", height: "auto", lineHeight: 1.4 }}>
      <div style={{ fontWeight: 700 }}>{emoji} {title}</div>
      <div style={{ fontSize: 12, opacity: 0.85, fontWeight: 400, marginTop: 2 }}>{sub}</div>
    </button>
  );

  return (
    <div>
      <div style={{ textAlign: "center", margin: "16px 0 22px" }}>
        <h1 style={{ fontSize: 28 }}>Create a video</h1>
        <p className="muted" style={{ marginTop: 4 }}>
          Describe it in a sentence — the AI writes the song, casts the characters, and renders the music video.
        </p>
      </div>

      {err && <p className="error" style={{ textAlign: "center" }}>{err}</p>}

      <div className="panel" style={{ maxWidth: 760, margin: "0 auto" }}>
        <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)}
          placeholder="e.g. a brave little robot who lights up a neon city at night"
          style={{ minHeight: 90, fontSize: 16 }} />

        <div className="row" style={{ marginTop: 12, gap: 16, alignItems: "end", flexWrap: "wrap" }}>
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
        </div>

        <label style={{ marginTop: 16 }}>Quality</label>
        <div className="grid cols-2" style={{ gap: 10 }}>
          {modeCard("fast", "⚡", "Fast", "instant · on your PC · narrated voice + pan/zoom · free")}
          {modeCard("gpu", "✨", "Best", "~35 min · free GPU · real singing + animation")}
        </div>

        <div className="row" style={{ marginTop: 16, alignItems: "center", gap: 12 }}>
          <button onClick={onCreate} disabled={busy || !prompt.trim() || !ready} style={{ fontSize: 15, padding: "11px 22px" }}>
            {busy
              ? (mode === "fast" ? "writing the song…" : "rendering on GPU…")
              : (mode === "fast" ? "⚡ Create video" : "✨ Render on GPU")}
          </button>
          <span className={`badge ${ready ? "ok" : "warn"}`}>
            {mode === "fast"
              ? (llmReady ? "ready" : "needs OPENROUTER_API_KEY")
              : (gpuAvail?.available ? "Kaggle ready" : "needs Kaggle token")}
          </span>
        </div>

        {mode === "fast" && !llmReady && (
          <p className="caption" style={{ textAlign: "left", marginTop: 8 }}>
            Add a free OpenRouter key to <code>backend/.env</code> (<code>OPENROUTER_API_KEY=sk-or-…</code>) and restart the backend.
          </p>
        )}
        {mode === "gpu" && gpuAvail && !gpuAvail.available && (
          <p className="caption" style={{ textAlign: "left", marginTop: 8 }}>
            Setup: {gpuAvail.hint} (see <code>docs/APP_GPU_RENDER.md</code>)
          </p>
        )}
        {mode === "gpu" && (gpuBusy || gpuJob) && (
          <div style={{ marginTop: 14 }}>
            <div className="caption" style={{ textAlign: "left" }}>
              {gpuJob ? `${gpuJob.status} · ${Math.round((gpuJob.progress || 0) * 100)}% · ${gpuJob.message}` : "starting…"}
            </div>
            <div className="progress" style={{ marginTop: 6 }}>
              <span style={{ width: `${Math.round((gpuJob?.progress || 0) * 100)}%` }} />
            </div>
            <p className="caption" style={{ textAlign: "left", marginTop: 6 }}>
              This runs on a free Kaggle GPU (~30–40 min). You can leave this tab open.
            </p>
          </div>
        )}
        {gpuVideoId && (
          <div style={{ marginTop: 14 }}>
            <video controls style={{ width: "100%", borderRadius: 8, background: "#000" }} src={`${API_BASE}/assets/${gpuVideoId}`} />
            <p className="caption" style={{ textAlign: "left", marginTop: 6 }}>
              <a href={`${API_BASE}/assets/${gpuVideoId}`} download>⬇ download</a>
              {" · "}
              <a href="/videos">open in your Videos library →</a>
            </p>
          </div>
        )}
      </div>

      <div className="row" style={{ justifyContent: "center", marginTop: 22, gap: 22 }}>
        <a href="/videos">🎬 Your videos</a>
        <a href="/projects">📁 Projects &amp; templates</a>
        <a href="/voice">🎤 VoiceLab</a>
      </div>
    </div>
  );
}
