"use client";

import { useEffect, useState } from "react";
import { api, API_BASE, type Asset } from "@/lib/api";

export default function VideosPage() {
  const [videos, setVideos] = useState<Asset[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [deleting, setDeleting] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    try {
      setVideos(await api.listAssets("video"));
      setErr("");
    } catch (e) {
      setErr(String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function remove(id: string) {
    if (!confirm("Delete this video permanently? This can't be undone.")) return;
    setDeleting(id);
    try {
      await api.deleteAsset(id);
      setVideos((v) => v.filter((a) => a.id !== id));
    } catch (e) {
      setErr(String(e));
    } finally {
      setDeleting(null);
    }
  }

  function title(a: Asset): string {
    const p = (a.meta?.prompt as string) || "";
    if (!p) return "Untitled video";
    return p.length > 90 ? p.slice(0, 90) + "…" : p;
  }
  function when(a: Asset): string {
    try {
      return new Date(a.created_at).toLocaleString();
    } catch {
      return a.created_at;
    }
  }

  return (
    <div>
      <div className="spread">
        <h1>🎬 Your Videos</h1>
        <div className="row" style={{ gap: 8 }}>
          <span className="badge">{videos.length} video{videos.length === 1 ? "" : "s"}</span>
          <button className="ghost" onClick={load} disabled={loading}>↻ Refresh</button>
        </div>
      </div>
      <p className="muted" style={{ marginTop: 4 }}>
        Every video you generate lands here — preview it, download it, or delete it.
      </p>

      {err && <p className="error">{err}</p>}

      {loading ? (
        <p className="muted" style={{ marginTop: 24 }}>Loading…</p>
      ) : videos.length === 0 ? (
        <div className="panel" style={{ textAlign: "center", padding: "40px 20px" }}>
          <div style={{ fontSize: 38 }}>🎞️</div>
          <p className="muted" style={{ marginTop: 8 }}>No videos yet.</p>
          <a href="/"><button style={{ marginTop: 6 }}>Create a video from a prompt</button></a>
        </div>
      ) : (
        <div className="grid cols-2" style={{ marginTop: 16 }}>
          {videos.map((a) => (
            <div className="card" key={a.id}>
              <video
                controls
                preload="metadata"
                style={{ width: "100%", borderRadius: 8, background: "#000", aspectRatio: "16 / 9" }}
                src={`${API_BASE}/assets/${a.id}`}
              />
              <div style={{ marginTop: 10, fontWeight: 600 }}>{title(a)}</div>
              <div className="caption" style={{ textAlign: "left", marginTop: 4 }}>
                {(a.meta?.style as string) && (
                  <span className="badge" style={{ marginRight: 6 }}>{a.meta.style as string}</span>
                )}
                {a.provider && <span>{a.provider}</span>} · {when(a)}
              </div>
              <div className="row" style={{ marginTop: 12, gap: 8 }}>
                <a href={`${API_BASE}/assets/${a.id}`} download={`${a.id}.mp4`}>
                  <button>⬇ Download</button>
                </a>
                {a.project_id && (
                  <a href={`/projects/${a.project_id}/timeline`}>
                    <button className="ghost">✏️ Edit clips</button>
                  </a>
                )}
                <button className="ghost" onClick={() => remove(a.id)} disabled={deleting === a.id}>
                  {deleting === a.id ? "deleting…" : "🗑 Delete"}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
