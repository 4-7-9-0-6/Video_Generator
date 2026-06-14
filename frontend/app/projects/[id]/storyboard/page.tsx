"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { api, API_BASE, type Character, type Job, type Shot } from "@/lib/api";

export default function StoryboardPage() {
  const { id } = useParams<{ id: string }>();
  const [shots, setShots] = useState<Shot[]>([]);
  const [charMap, setCharMap] = useState<Record<string, string>>({});
  const [cameras, setCameras] = useState<string[]>([]);
  const [script, setScript] = useState("");
  const [background, setBackground] = useState("");
  const [activeJobs, setActiveJobs] = useState(0);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const aliveRef = useRef(true);

  // export
  const [presets, setPresets] = useState<string[]>(["youtube_1080p"]);
  const [preset, setPreset] = useState("youtube_1080p");
  const [grades, setGrades] = useState<string[]>(["none"]);
  const [grade, setGrade] = useState("none");
  const [withVoice, setWithVoice] = useState(true);
  const [withSing, setWithSing] = useState(false);
  const [withLipsync, setWithLipsync] = useState(false);
  const [singKey, setSingKey] = useState("auto");
  const [singTempo, setSingTempo] = useState(0);   // 0 = auto from lyrics
  const [singVibrato, setSingVibrato] = useState(0.3);
  const [withSubs, setWithSubs] = useState(true);
  const [wordSubs, setWordSubs] = useState(true);
  const [withMusic, setWithMusic] = useState(false);
  const [musicBrief, setMusicBrief] = useState<{ mood: string; tempo: number; key: string } | null>(null);
  const [smartReframe, setSmartReframe] = useState(true);
  const [exportJob, setExportJob] = useState<Job | null>(null);
  const [episodeUrl, setEpisodeUrl] = useState("");
  const [cost, setCost] = useState<{ assets: number; gpu_seconds: number; usd: number } | null>(null);

  // youtube thumbnails
  const [thumbTitle, setThumbTitle] = useState("");
  const [thumbCount, setThumbCount] = useState(3);
  const [thumbs, setThumbs] = useState<{ asset_id: string; title: string | null }[]>([]);
  const [thumbJob, setThumbJob] = useState<Job | null>(null);

  const load = useCallback(async () => {
    const [chars, sh, jobs] = await Promise.all([
      api.listCharacters(id),
      api.listShots(id),
      api.listJobs(id),
    ]);
    setCharMap(Object.fromEntries(chars.map((c: Character) => [c.id, c.name])));
    setShots(sh);
    const active = jobs.filter((j: Job) => j.type === "shot_keyframe" && (j.status === "queued" || j.status === "running")).length;
    setActiveJobs(active);
    return active;
  }, [id]);

  useEffect(() => {
    aliveRef.current = true;
    let timer: ReturnType<typeof setTimeout>;
    async function tick() {
      if (!aliveRef.current) return;
      try {
        const active = await load();
        if (active > 0 && aliveRef.current) timer = setTimeout(tick, 1500);
      } catch (e) {
        if (aliveRef.current) setErr(String(e));
      }
    }
    api.motionPresets().then((m) => setCameras(Object.keys(m))).catch(() => {});
    api.exportPresets().then((p) => setPresets(Object.keys(p))).catch(() => {});
    api.exportGrades().then(setGrades).catch(() => {});
    api.listThumbnails(id).then(setThumbs).catch(() => {});
    refreshCost();
    tick();
    return () => { aliveRef.current = false; clearTimeout(timer); };
  }, [id, load]);

  async function refreshCost() {
    try { setCost(await api.projectCost(id)); } catch { /* ignore */ }
  }

  async function doExport() {
    setErr(""); setEpisodeUrl("");
    try {
      let job = await api.exportEpisode(id, {
        preset, voice: withVoice, sing: withSing,
        sing_key: singKey, sing_tempo: singTempo, sing_vibrato: singVibrato,
        lipsync: withLipsync, subtitles: withSubs, word_subtitles: wordSubs,
        music: withMusic, music_auto: true, smart_reframe: smartReframe, grade,
      });
      setExportJob(job);
      while (job.status === "queued" || job.status === "running") {
        await new Promise((r) => setTimeout(r, 1500));
        job = await api.getJob(job.id);
        setExportJob(job);
      }
      if (job.status === "succeeded") {
        setEpisodeUrl(`${API_BASE}/assets/${(job.result as { asset_id: string }).asset_id}?t=${Date.now()}`);
        refreshCost();
      } else {
        setErr(`Export ${job.status}: ${job.error}`);
      }
    } catch (e) {
      setErr(String(e));
    }
  }

  async function plan(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setErr("");
    try {
      await api.planScript(id, script, background);
      await load();
    } catch (e) { setErr(String(e)); }
    finally { setBusy(false); }
  }

  async function startTick() {
    aliveRef.current = true;
    const active = await load();
    if (active > 0) setTimeout(function again() {
      if (aliveRef.current) load().then((a) => { if (a > 0) setTimeout(again, 1500); });
    }, 1500);
  }

  async function renderAll() {
    setErr("");
    try { await api.renderAllKeyframes(id, false); await startTick(); }
    catch (e) { setErr(String(e)); }
  }

  async function regen(shotId: string) {
    setErr("");
    try { await api.renderKeyframe(shotId, true); await startTick(); }
    catch (e) { setErr(String(e)); }
  }

  async function changeCamera(shot: Shot, camera: string) {
    await api.patchShot(shot.id, { camera });
    await load();
  }

  async function toggleMusic(on: boolean) {
    setWithMusic(on);
    if (on) {
      try { setMusicBrief(await api.musicBrief(id)); } catch { setMusicBrief(null); }
    }
  }

  async function makeThumbnails() {
    setErr("");
    try {
      let job = await api.proposeThumbnails(id, {
        title: thumbTitle.trim() || undefined, count: thumbCount,
      });
      setThumbJob(job);
      while (job.status === "queued" || job.status === "running") {
        await new Promise((r) => setTimeout(r, 1500));
        job = await api.getJob(job.id);
        setThumbJob(job);
      }
      if (job.status === "succeeded") {
        setThumbs(await api.listThumbnails(id));
        refreshCost();
      } else {
        setErr(`Thumbnails ${job.status}: ${job.error}`);
      }
    } catch (e) {
      setErr(String(e));
    }
  }

  return (
    <div>
      <p className="muted"><a href={`/projects/${id}`}>← Project</a></p>
      <div className="spread">
        <h1>Storyboard</h1>
        <span className="row" style={{ width: "auto", gap: 8 }}>
          <a className="badge" href={`/projects/${id}/timeline`}>🎞 Timeline</a>
          {activeJobs > 0 && <span className="badge warn">rendering · {activeJobs} job(s)</span>}
        </span>
      </div>
      {err && <p className="error">{err}</p>}

      <form className="panel" onSubmit={plan}>
        <h3>Plan a script into shots</h3>
        <textarea value={script} onChange={(e) => setScript(e.target.value)}
          placeholder={"Paste lyrics or a script — one line per shot.\nMila wakes up and stretches!\nBo the robot says good morning.\nThey run outside to play."} />
        <label>Default background</label>
        <input value={background} onChange={(e) => setBackground(e.target.value)} placeholder="a sunny meadow with flowers" />
        <div className="row" style={{ marginTop: 12 }}>
          <button disabled={busy || !script.trim()}>{busy ? "planning…" : "Plan shots"}</button>
          {shots.length > 0 && (
            <button type="button" className="ghost" onClick={renderAll}>Render all keyframes</button>
          )}
        </div>
      </form>

      <div className="grid" style={{ gap: 12 }}>
        {shots.map((s) => (
          <div key={s.id} className="card row" style={{ alignItems: "flex-start", gap: 14 }}>
            <div style={{ width: 200, flex: "0 0 auto" }}>
              {s.keyframe_id ? (
                <img className="thumb" style={{ aspectRatio: "16/9" }} src={api.assetUrl(s.keyframe_id)} alt={`shot ${s.idx}`} />
              ) : (
                <div className="thumb" style={{ aspectRatio: "16/9", display: "grid", placeItems: "center", color: "var(--muted)" }}>
                  {activeJobs > 0 ? "…" : "no keyframe"}
                </div>
              )}
            </div>
            <div style={{ flex: 1 }}>
              <div className="spread">
                <strong>Shot {s.idx + 1}</strong>
                <span className="badge">{s.status}</span>
              </div>
              <p style={{ margin: "6px 0" }}>{s.text}</p>
              <div className="pill-list" style={{ marginBottom: 8 }}>
                {s.characters.map((cid) => <span key={cid} className="badge ok">{charMap[cid] ?? cid}</span>)}
                {s.characters.length === 0 && <span className="badge">no character</span>}
                <span className="badge">{s.duration_s}s</span>
                {s.background && <span className="badge">{s.background}</span>}
              </div>
              <div className="row">
                <select value={s.camera} onChange={(e) => changeCamera(s, e.target.value)} style={{ width: "auto" }}>
                  {(cameras.length ? cameras : [s.camera]).map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
                <button className="ghost" onClick={() => regen(s.id)}>Regenerate keyframe</button>
              </div>
            </div>
          </div>
        ))}
        {shots.length === 0 && <p className="muted">No shots yet — plan a script above.</p>}
      </div>

      {shots.length > 0 && (
        <div className="panel">
          <div className="spread">
            <h3 style={{ margin: 0 }}>Export episode</h3>
            {cost && (
              <span className="badge ok" title="cost meter">
                {cost.assets} assets · {cost.gpu_seconds} GPU-s · ${cost.usd}
              </span>
            )}
          </div>
          <div className="row" style={{ marginTop: 10 }}>
            <select value={preset} onChange={(e) => setPreset(e.target.value)} style={{ width: "auto" }} title="format / platform">
              {presets.map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
            <select value={grade} onChange={(e) => setGrade(e.target.value)} style={{ width: "auto" }} title="color-grade look">
              {grades.map((g) => <option key={g} value={g}>{g === "none" ? "no grade" : `🎨 ${g}`}</option>)}
            </select>
            <label className="row" style={{ margin: 0, width: "auto", color: "var(--text)" }}>
              <input type="checkbox" checked={withVoice} onChange={(e) => setWithVoice(e.target.checked)} style={{ width: "auto", marginRight: 6 }} />
              voiceover (Piper)
            </label>
            <label className="row" style={{ margin: 0, width: "auto", color: "var(--text)" }} title="sing the lyrics to an auto melody (local CPU, novelty quality) instead of speaking">
              <input type="checkbox" checked={withSing} onChange={(e) => setWithSing(e.target.checked)} disabled={!withVoice} style={{ width: "auto", marginRight: 6 }} />
              🎤 sing
            </label>
            <label className="row" style={{ margin: 0, width: "auto", color: "var(--text)" }} title="audio-driven mouth flap (local CPU, basic). Best on close-up character shots; replaces the Ken Burns move.">
              <input type="checkbox" checked={withLipsync} onChange={(e) => setWithLipsync(e.target.checked)} disabled={!withVoice} style={{ width: "auto", marginRight: 6 }} />
              🗣 lip-sync
            </label>
            <label className="row" style={{ margin: 0, width: "auto", color: "var(--text)" }}>
              <input type="checkbox" checked={withSubs} onChange={(e) => setWithSubs(e.target.checked)} style={{ width: "auto", marginRight: 6 }} />
              subtitles
            </label>
            <label className="row" style={{ margin: 0, width: "auto", color: "var(--text)" }} title="word-level timing via faster-whisper (first run downloads the model)">
              <input type="checkbox" checked={wordSubs} onChange={(e) => setWordSubs(e.target.checked)} disabled={!withSubs || !withVoice} style={{ width: "auto", marginRight: 6 }} />
              word-level
            </label>
            <label className="row" style={{ margin: 0, width: "auto", color: "var(--text)" }} title="auto-picks mood/tempo/key from your lyrics">
              <input type="checkbox" checked={withMusic} onChange={(e) => toggleMusic(e.target.checked)} style={{ width: "auto", marginRight: 6 }} />
              music bed{withMusic && musicBrief ? ` · 🎵 ${musicBrief.mood} ${musicBrief.tempo}bpm` : ""}
            </label>
            <label className="row" style={{ margin: 0, width: "auto", color: "var(--text)" }} title="content-aware crop to the export aspect (keeps the subject framed when exporting vertical Shorts instead of stretching 16:9)">
              <input type="checkbox" checked={smartReframe} onChange={(e) => setSmartReframe(e.target.checked)} style={{ width: "auto", marginRight: 6 }} />
              smart reframe
            </label>
            <button onClick={doExport}
              disabled={!!exportJob && (exportJob.status === "queued" || exportJob.status === "running")}>
              {exportJob && (exportJob.status === "queued" || exportJob.status === "running") ? "rendering…" : "Export MP4"}
            </button>
          </div>

          {withSing && (
            <div className="row" style={{ marginTop: 10, flexWrap: "wrap", gap: 14, alignItems: "end" }}>
              <span className="caption" style={{ alignSelf: "center" }}>🎤 sing:</span>
              <div>
                <label>Key</label>
                <select value={singKey} onChange={(e) => setSingKey(e.target.value)} style={{ width: "auto" }}>
                  {["auto", "C", "D", "E", "F", "G", "A", "A minor", "E minor", "D minor"].map((k) =>
                    <option key={k} value={k}>{k}</option>)}
                </select>
              </div>
              <div>
                <label>Tempo</label>
                <select value={singTempo} onChange={(e) => setSingTempo(parseInt(e.target.value))} style={{ width: "auto" }}>
                  <option value={0}>auto</option>
                  {[70, 90, 110, 130, 150].map((t) => <option key={t} value={t}>{t} BPM</option>)}
                </select>
              </div>
              <div>
                <label>Vibrato · {singVibrato.toFixed(2)}</label>
                <input type="range" min={0} max={1} step={0.05}
                       value={singVibrato} onChange={(e) => setSingVibrato(parseFloat(e.target.value))} />
              </div>
            </div>
          )}

          {exportJob && (exportJob.status === "queued" || exportJob.status === "running") && (
            <div className="progress" style={{ marginTop: 12 }}>
              <span style={{ width: `${Math.round(exportJob.progress * 100)}%` }} />
            </div>
          )}
          {exportJob && <div className="caption" style={{ textAlign: "left" }}>{exportJob.message}</div>}

          {episodeUrl && (
            <div style={{ marginTop: 14 }}>
              <video controls src={episodeUrl} style={{ width: "100%", borderRadius: 8, background: "#000" }} />
              <p style={{ marginTop: 8 }}><a href={episodeUrl} download>⬇ download episode.mp4</a></p>
            </div>
          )}
        </div>
      )}

      <div className="panel">
        <div className="spread">
          <h3 style={{ margin: 0 }}>YouTube thumbnails</h3>
          <span className="badge">1280×720 · local · free</span>
        </div>
        <p className="muted" style={{ marginTop: 4 }}>
          Character-locked hero art + a bold title. Proposes a few options to pick from.
        </p>
        <div className="row" style={{ marginTop: 10 }}>
          <input value={thumbTitle} onChange={(e) => setThumbTitle(e.target.value)}
            placeholder="Title (defaults to project name)" />
          <select value={thumbCount} onChange={(e) => setThumbCount(Number(e.target.value))} style={{ width: "auto" }}>
            {[1, 2, 3, 4, 5, 6].map((n) => <option key={n} value={n}>{n} option{n > 1 ? "s" : ""}</option>)}
          </select>
          <button onClick={makeThumbnails}
            disabled={!!thumbJob && (thumbJob.status === "queued" || thumbJob.status === "running")}>
            {thumbJob && (thumbJob.status === "queued" || thumbJob.status === "running") ? "generating…" : "Propose thumbnails"}
          </button>
        </div>
        {thumbJob && (thumbJob.status === "queued" || thumbJob.status === "running") && (
          <>
            <div className="progress" style={{ marginTop: 12 }}>
              <span style={{ width: `${Math.round(thumbJob.progress * 100)}%` }} />
            </div>
            <div className="caption" style={{ textAlign: "left" }}>{thumbJob.message}</div>
          </>
        )}
        {thumbs.length > 0 && (
          <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fill,minmax(280px,1fr))", gap: 12, marginTop: 14 }}>
            {thumbs.map((t) => (
              <div key={t.asset_id} className="card">
                <img className="thumb" style={{ aspectRatio: "16/9" }}
                  src={`${api.assetUrl(t.asset_id)}?t=${Date.now()}`} alt={t.title ?? "thumbnail"} />
                <p style={{ marginTop: 6 }}>
                  <a href={api.assetUrl(t.asset_id)} download>⬇ download</a>
                </p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
