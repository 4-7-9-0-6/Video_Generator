"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { api, type Character, type Job } from "@/lib/api";
import { JobError } from "@/components/JobError";

const TURNAROUND_LABELS = ["front", "three_quarter", "side", "back"];

function isActive(j: Job) {
  return j.status === "queued" || j.status === "running";
}

export default function CharacterPage() {
  const { id } = useParams<{ id: string }>();
  const [character, setCharacter] = useState<Character | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [err, setErr] = useState("");
  const [instruction, setInstruction] = useState("");
  const [busy, setBusy] = useState(false);
  const [loreBusy, setLoreBusy] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const aliveRef = useRef(true);

  const mine = useCallback(
    (j: Job) =>
      j.type === "character_sheets" &&
      (j.payload as { character_id?: string }).character_id === id,
    [id],
  );

  useEffect(() => {
    aliveRef.current = true;
    let timer: ReturnType<typeof setTimeout>;
    async function tick() {
      if (!aliveRef.current) return;
      try {
        const c = await api.getCharacter(id);
        const js = await api.listJobs(c.project_id);
        if (!aliveRef.current) return;
        setCharacter(c);
        setJobs(js);
        setErr("");
        if (js.filter(mine).some(isActive)) timer = setTimeout(tick, 1500);
      } catch (e) {
        if (aliveRef.current) setErr(String(e));
      }
    }
    tick();
    return () => {
      aliveRef.current = false;
      clearTimeout(timer);
    };
  }, [id, mine, reloadKey]);

  async function submitEdit(e: React.FormEvent) {
    e.preventDefault();
    if (!instruction.trim()) return;
    setBusy(true);
    setErr("");
    try {
      await api.editCharacter(id, instruction.trim(), [
        "turnaround",
        "expressions",
        "poses",
      ]);
      setInstruction("");
      setReloadKey((k) => k + 1); // restart polling for the new job
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function rerollLore() {
    setLoreBusy(true);
    try {
      const l = await api.regenerateLore(id);
      setCharacter((c) => (c ? { ...c, lore: l } : c));
    } catch (e) {
      setErr(String(e));
    } finally {
      setLoreBusy(false);
    }
  }

  const myJobs = jobs.filter(mine);
  const currentJob = myJobs[0]; // listJobs returns newest first
  const generating = currentJob && isActive(currentJob);
  const report = character?.consistency;

  return (
    <div>
      <p className="muted">
        {character ? <a href={`/projects/${character.project_id}`}>← Project</a> : <a href="/">← Home</a>}
      </p>

      {!character ? (
        <p className="muted">Loading…</p>
      ) : (
        <>
          <div className="spread">
            <h1>{character.name}</h1>
            <span className="badge">{character.style_preset}</span>
          </div>
          <p className="muted">{character.description}</p>
          {character.palette?.length > 0 && (
            <div className="row">
              {character.palette.map((hex) => (
                <span key={hex} className="row" style={{ width: "auto", gap: 6 }}>
                  <span className="swatch" style={{ background: hex }} /> <span className="mono">{hex}</span>
                </span>
              ))}
            </div>
          )}
          {err && <p className="error">{err}</p>}

          {/* Character lore (rule-based, no LLM) */}
          {character.lore && (character.lore.personality || character.lore.backstory) && (
            <div className="panel">
              <div className="spread">
                <h3 style={{ margin: 0 }}>Lore</h3>
                <span className="row" style={{ width: "auto", gap: 8 }}>
                  {character.lore.archetype && <span className="badge">{character.lore.archetype}</span>}
                  {character.lore.theme && <span className="badge">{character.lore.theme}</span>}
                  <button className="ghost" onClick={rerollLore} disabled={loreBusy} style={{ width: "auto" }}>
                    {loreBusy ? "…" : "🎲 re-roll"}
                  </button>
                </span>
              </div>
              {character.lore.personality && (
                <p style={{ margin: "8px 0 4px" }}><strong>Personality.</strong> {character.lore.personality}</p>
              )}
              {character.lore.backstory && (
                <p style={{ margin: "4px 0" }}><strong>Backstory.</strong> {character.lore.backstory}</p>
              )}
              {character.lore.abilities && character.lore.abilities.length > 0 && (
                <div className="pill-list" style={{ marginTop: 8 }}>
                  {character.lore.abilities.map((a, i) => <span key={i} className="badge ok">⚡ {a}</span>)}
                </div>
              )}
            </div>
          )}

          {/* Live job progress */}
          {currentJob && (
            <div className="panel">
              <div className="spread">
                <h3 style={{ margin: 0 }}>
                  Generation · {currentJob.status}
                </h3>
                <span className={`badge ${currentJob.status === "succeeded" ? "ok" : currentJob.status === "failed" ? "err" : "warn"}`}>
                  {currentJob.message}
                </span>
              </div>
              <div className="progress" style={{ marginTop: 10 }}>
                <span style={{ width: `${Math.round(currentJob.progress * 100)}%` }} />
              </div>
              <JobError job={currentJob} title="Generation failed" />
            </div>
          )}

          {/* Consistency report */}
          {report && report.passed !== null && report.passed !== undefined && (
            <div className="panel">
              <div className="spread">
                <h3 style={{ margin: 0 }}>Consistency (palette drift)</h3>
                <span className={`badge ${report.passed ? "ok" : "warn"}`}>
                  {report.passed ? "passed" : "below threshold"} · min {report.min_score?.toFixed(3)} / {report.threshold}
                </span>
              </div>
              {report.scores && Object.keys(report.scores).length > 0 && (
                <div className="pill-list" style={{ marginTop: 10 }}>
                  {Object.entries(report.scores).map(([view, score]) => (
                    <span key={view} className={`badge ${score >= (report.threshold ?? 0.85) ? "ok" : "warn"}`}>
                      {view}: {score.toFixed(3)}
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}

          <Gallery title="Turnaround" items={
            (character.sheets?.turnaround ?? []).map((assetId, i) => ({
              key: TURNAROUND_LABELS[i] ?? `view ${i}`,
              assetId,
            }))
          } cols={4} />

          <Gallery title="Expressions" items={
            Object.entries(character.sheets?.expressions ?? {}).map(([key, assetId]) => ({ key, assetId }))
          } cols={5} square />

          <Gallery title="Poses" items={
            Object.entries(character.sheets?.poses ?? {}).map(([key, assetId]) => ({ key, assetId }))
          } cols={5} />

          {!character.sheets?.turnaround && !generating && (
            <p className="muted">No sheets yet. {currentJob?.status === "failed" ? "The last generation failed — check the image provider (rate limit / token)." : ""}</p>
          )}

          {/* Instruction edit */}
          <form className="panel" onSubmit={submitEdit}>
            <h3>Instruction edit</h3>
            <div className="row">
              <input
                value={instruction}
                onChange={(e) => setInstruction(e.target.value)}
                placeholder="change her t-shirt to green"
                style={{ maxWidth: 460 }}
              />
              <button disabled={busy || generating || !instruction.trim()}>
                {generating ? "generating…" : "Apply & regenerate"}
              </button>
            </div>
            {character.edits?.length > 0 && (
              <div className="pill-list" style={{ marginTop: 12 }}>
                {character.edits.map((ed) => (
                  <span key={ed.id} className="badge">✎ {ed.instruction}</span>
                ))}
              </div>
            )}
          </form>
        </>
      )}
    </div>
  );
}

function Gallery({
  title,
  items,
  cols,
  square,
}: {
  title: string;
  items: { key: string; assetId: string }[];
  cols: 4 | 5;
  square?: boolean;
}) {
  if (items.length === 0) return null;
  return (
    <>
      <h2>{title}</h2>
      <div className={`grid cols-${cols}`}>
        {items.map((it) => (
          <div key={it.key}>
            <img className={`thumb ${square ? "square" : ""}`} src={api.assetUrl(it.assetId)} alt={it.key} />
            <div className="caption">{it.key.replace(/_/g, " ")}</div>
          </div>
        ))}
      </div>
    </>
  );
}
