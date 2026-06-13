"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api, type Character, type TranscriptLine } from "@/lib/api";

export default function TranscriptPage() {
  const { id } = useParams<{ id: string }>();
  const [lines, setLines] = useState<TranscriptLine[]>([]);
  const [charMap, setCharMap] = useState<Record<string, string>>({});
  const [total, setTotal] = useState(0);
  const [newText, setNewText] = useState("");
  const [err, setErr] = useState("");
  const [rendering, setRendering] = useState(false);

  const load = useCallback(async () => {
    try {
      const [tr, chars] = await Promise.all([api.getTranscript(id), api.listCharacters(id)]);
      setLines(tr.shots);
      setTotal(tr.total_duration_s);
      setCharMap(Object.fromEntries(chars.map((c: Character) => [c.id, c.name])));
      setErr("");
    } catch (e) {
      setErr(String(e));
    }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  async function saveText(line: TranscriptLine, text: string) {
    if (text.trim() === line.text || !text.trim()) return;
    await api.patchShot(line.id, { text: text.trim() });
    await load();
  }

  async function del(lineId: string) {
    await api.deleteShot(lineId);
    await load();
  }

  async function move(idx: number, dir: -1 | 1) {
    const j = idx + dir;
    if (j < 0 || j >= lines.length) return;
    const order = lines.map((l) => l.id);
    [order[idx], order[j]] = [order[j], order[idx]];
    await api.reorderShots(id, order);
    await load();
  }

  async function addLine() {
    if (!newText.trim()) return;
    await api.insertShot(id, { text: newText.trim() });
    setNewText("");
    await load();
  }

  async function renderStale() {
    setRendering(true);
    try {
      await api.renderAllKeyframes(id, false);
      for (let i = 0; i < 40; i++) {
        await new Promise((r) => setTimeout(r, 2000));
        const tr = await api.getTranscript(id);
        setLines(tr.shots);
        if (!tr.shots.some((s) => s.stale)) break;
      }
      await load();
    } catch (e) {
      setErr(String(e));
    } finally {
      setRendering(false);
    }
  }

  const staleCount = lines.filter((l) => l.stale).length;

  return (
    <div>
      <p className="muted"><a href={`/projects/${id}`}>← Project</a> · <a href={`/projects/${id}/storyboard`}>Storyboard →</a></p>
      <div className="spread">
        <h1>Transcript</h1>
        <span className="badge">{lines.length} lines · {total}s</span>
      </div>
      <p className="muted">Edit a line to change that shot. Delete a line and its video + audio drop from the episode.</p>
      {err && <p className="error">{err}</p>}

      {staleCount > 0 && (
        <div className="panel spread">
          <span className="badge warn">{staleCount} line(s) need rendering</span>
          <button onClick={renderStale} disabled={rendering}>
            {rendering ? "rendering…" : "Render changed shots"}
          </button>
        </div>
      )}

      <div className="grid" style={{ gap: 8 }}>
        {lines.map((l, i) => (
          <div key={l.id} className="card row" style={{ gap: 12, alignItems: "center" }}>
            <div style={{ width: 88, flex: "0 0 auto" }}>
              <div className="mono muted">{l.start_s.toFixed(1)}–{l.end_s.toFixed(1)}s</div>
              <div className="mono" style={{ fontSize: 11, color: l.has_keyframe ? "var(--ok)" : "var(--muted)" }}>
                {l.has_keyframe ? "▣ keyframe" : "□ no frame"}
              </div>
            </div>
            <input
              defaultValue={l.text}
              key={`${l.id}:${l.text}`}
              onBlur={(e) => saveText(l, e.target.value)}
              style={{ flex: 1 }}
            />
            <div className="pill-list" style={{ width: 160, flex: "0 0 auto" }}>
              {l.characters.map((cid) => <span key={cid} className="badge ok">{charMap[cid] ?? "?"}</span>)}
              <span className="badge">{l.camera}</span>
              {l.stale ? <span className="badge warn">stale</span> : <span className="badge ok">✓</span>}
            </div>
            <div className="row" style={{ width: "auto", gap: 4 }}>
              <button className="ghost" title="move up" onClick={() => move(i, -1)} disabled={i === 0}>↑</button>
              <button className="ghost" title="move down" onClick={() => move(i, 1)} disabled={i === lines.length - 1}>↓</button>
              <button className="ghost" title="delete line" onClick={() => del(l.id)}>✕</button>
            </div>
          </div>
        ))}
        {lines.length === 0 && <p className="muted">No lines yet — add one below or plan a script in the Storyboard.</p>}
      </div>

      <div className="panel row">
        <input value={newText} onChange={(e) => setNewText(e.target.value)}
          placeholder="Add a new line…" onKeyDown={(e) => { if (e.key === "Enter") addLine(); }} style={{ flex: 1 }} />
        <button onClick={addLine} disabled={!newText.trim()}>Add line</button>
      </div>
    </div>
  );
}
