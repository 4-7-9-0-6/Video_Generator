"use client";

// WebGL multi-track timeline (spec Module D) — PixiJS canvas showing Video / Voice / Music /
// Subtitle lanes with per-shot clip blocks, keyframe thumbnails, a scrubbable playhead, and
// play/pause. Pure frontend, local + free, no GPU. Pixi is dynamically imported so it never
// runs during SSR.

import { useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { api, type Shot } from "@/lib/api";

const LANES = ["Video", "Voice", "Music", "Subs"] as const;
const LANE_H = 58;
const RULER_H = 24;
const LABEL_W = 66;
const PAD_R = 14;
const COLORS = {
  bg: 0x0e1117, lane: 0x161b22, laneAlt: 0x12161d, ruler: 0x1b2430,
  video: 0x3b82f6, voice: 0x22c55e, music: 0xa855f7, subs: 0xf59e0b,
  sel: 0xffffff, playhead: 0xff4d6d, text: 0xc9d1d9, tick: 0x30363d,
};

export default function TimelinePage() {
  const { id } = useParams<{ id: string }>();
  const hostRef = useRef<HTMLDivElement>(null);
  const timeRef = useRef<HTMLSpanElement>(null);
  const ctl = useRef<{ t: number; playing: boolean; total: number; pps: number; move?: () => void }>({
    t: 0, playing: false, total: 0, pps: 0,
  });
  const [shots, setShots] = useState<Shot[]>([]);
  const [charMap, setCharMap] = useState<Record<string, string>>({});
  const [sel, setSel] = useState<Shot | null>(null);
  const [playing, setPlaying] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    Promise.all([api.listShots(id), api.listCharacters(id)])
      .then(([s, c]) => {
        setShots(s);
        setCharMap(Object.fromEntries(c.map((x) => [x.id, x.name])));
      })
      .catch((e) => setErr(String(e)));
  }, [id]);

  useEffect(() => {
    if (!hostRef.current || shots.length === 0) return;
    let destroyed = false;
    let app: import("pixi.js").Application | undefined;

    (async () => {
      const PIXI = await import("pixi.js");
      const host = hostRef.current!;
      const width = Math.max(640, host.clientWidth);
      const height = RULER_H + LANES.length * LANE_H + 8;
      const trackW = width - LABEL_W - PAD_R;

      const durations = shots.map((s) => s.duration_s || 4);
      const starts: number[] = [];
      let acc = 0;
      for (const d of durations) { starts.push(acc); acc += d; }
      const total = Math.max(acc, 1);
      const pps = trackW / total;
      ctl.current = { ...ctl.current, t: 0, playing: false, total, pps };

      app = new PIXI.Application();
      await app.init({ width, height, background: COLORS.bg, antialias: true });
      if (destroyed) { app.destroy(true, { children: true }); return; }
      host.innerHTML = "";
      host.appendChild(app.canvas);

      const laneY = (i: number) => RULER_H + i * LANE_H;
      const xAt = (t: number) => LABEL_W + t * pps;

      // lane backgrounds + labels
      for (let i = 0; i < LANES.length; i++) {
        const g = new PIXI.Graphics();
        g.rect(0, laneY(i), width, LANE_H).fill(i % 2 ? COLORS.laneAlt : COLORS.lane);
        app.stage.addChild(g);
        const label = new PIXI.Text({
          text: LANES[i],
          style: { fill: COLORS.text, fontSize: 12, fontFamily: "monospace" },
        });
        label.position.set(8, laneY(i) + LANE_H / 2 - 7);
        app.stage.addChild(label);
      }

      // ruler ticks (every ~1s, thinned to keep it readable)
      const ruler = new PIXI.Graphics();
      ruler.rect(0, 0, width, RULER_H).fill(COLORS.ruler);
      const stepS = total > 30 ? 5 : total > 12 ? 2 : 1;
      for (let t = 0; t <= total + 0.001; t += stepS) {
        const x = xAt(t);
        ruler.moveTo(x, 0).lineTo(x, height).stroke({ width: 1, color: COLORS.tick, alpha: 0.5 });
        const tl = new PIXI.Text({
          text: `${t}s`, style: { fill: COLORS.text, fontSize: 10, fontFamily: "monospace" },
        });
        tl.position.set(x + 2, 5);
        app.stage.addChild(tl);
      }
      app.stage.addChildAt(ruler, 0);

      const seeded = (n: number) => { const x = Math.sin(n * 99.7) * 1e4; return x - Math.floor(x); };

      // clip blocks per shot
      shots.forEach((shot, i) => {
        const x = xAt(starts[i]);
        const w = Math.max(2, durations[i] * pps - 2);

        const drawBlock = (lane: number, color: number, h = LANE_H - 14) => {
          const g = new PIXI.Graphics();
          g.roundRect(x + 1, laneY(lane) + 7, w, h, 4).fill({ color, alpha: 0.85 });
          app!.stage.addChild(g);
          return g;
        };

        // Video lane (interactive + selectable)
        const vid = drawBlock(0, COLORS.video);
        vid.eventMode = "static";
        vid.cursor = "pointer";
        vid.on("pointerdown", () => { setSel(shot); ctl.current.t = starts[i]; ctl.current.move?.(); });
        const vlabel = new PIXI.Text({
          text: `${i + 1}`, style: { fill: 0xffffff, fontSize: 11, fontFamily: "monospace" },
        });
        vlabel.position.set(x + 5, laneY(0) + 9);
        app!.stage.addChild(vlabel);

        // Voice lane: a pseudo-waveform so it reads as audio
        if (shot.text) {
          drawBlock(1, COLORS.voice);
          const wave = new PIXI.Graphics();
          const bars = Math.max(3, Math.floor(w / 4));
          for (let b = 0; b < bars; b++) {
            const bx = x + 3 + b * 4;
            const bh = 4 + seeded(i * 13 + b) * (LANE_H - 26);
            wave.moveTo(bx, laneY(1) + LANE_H / 2 - bh / 2).lineTo(bx, laneY(1) + LANE_H / 2 + bh / 2);
          }
          wave.stroke({ width: 1.5, color: 0x0b3d1e, alpha: 0.7 });
          app!.stage.addChild(wave);
        }

        // Subtitles lane: truncated cue text
        if (shot.text) {
          drawBlock(3, COLORS.subs, LANE_H - 18);
          const st = new PIXI.Text({
            text: shot.text.length > 22 ? shot.text.slice(0, 21) + "…" : shot.text,
            style: { fill: 0x3a2a00, fontSize: 10, fontFamily: "monospace" },
          });
          st.position.set(x + 5, laneY(3) + LANE_H / 2 - 6);
          const m = new PIXI.Graphics().rect(x + 1, laneY(3), w, LANE_H).fill(0xffffff);
          st.mask = m; app!.stage.addChild(m);
          app!.stage.addChild(st);
        }
      });

      // Music lane: one block spanning the episode
      const mus = new PIXI.Graphics();
      mus.roundRect(xAt(0) + 1, laneY(2) + 7, total * pps - 2, LANE_H - 14, 4).fill({ color: COLORS.music, alpha: 0.7 });
      app.stage.addChild(mus);

      // selection highlight (drawn above blocks, below playhead)
      const selG = new PIXI.Graphics();
      app.stage.addChild(selG);

      // playhead
      const playhead = new PIXI.Graphics();
      const drawHead = () => {
        playhead.clear();
        const x = xAt(ctl.current.t);
        playhead.moveTo(x, 0).lineTo(x, height).stroke({ width: 2, color: COLORS.playhead });
        playhead.circle(x, 6, 5).fill(COLORS.playhead);
        if (timeRef.current) timeRef.current.textContent = `${ctl.current.t.toFixed(1)} / ${total.toFixed(1)}s`;
      };
      ctl.current.move = drawHead;
      app.stage.addChild(playhead);
      drawHead();

      // scrub: click / drag anywhere on the tracks to move the playhead
      const bg = new PIXI.Graphics();
      bg.rect(LABEL_W, 0, trackW + PAD_R, height).fill({ color: 0xffffff, alpha: 0.001 });
      bg.eventMode = "static";
      let dragging = false;
      const seek = (gx: number) => {
        ctl.current.t = Math.max(0, Math.min(total, (gx - LABEL_W) / pps));
        drawHead();
      };
      bg.on("pointerdown", (e) => { dragging = true; seek(e.global.x); });
      bg.on("pointermove", (e) => { if (dragging) seek(e.global.x); });
      bg.on("pointerup", () => { dragging = false; });
      bg.on("pointerupoutside", () => { dragging = false; });
      app.stage.addChildAt(bg, app.stage.children.length); // top, but blocks already handle their own clicks

      // playback ticker
      app.ticker.add((ticker) => {
        if (!ctl.current.playing) return;
        ctl.current.t += ticker.deltaMS / 1000;
        if (ctl.current.t >= total) { ctl.current.t = total; ctl.current.playing = false; setPlaying(false); }
        drawHead();
      });

      // keyframe thumbnails on the video lane (best-effort; falls back to colored blocks)
      shots.forEach(async (shot, i) => {
        if (!shot.keyframe_id) return;
        try {
          const tex = await PIXI.Assets.load({ src: api.assetUrl(shot.keyframe_id), loadParser: "loadTextures" });
          if (destroyed || !app) return;
          const x = xAt(starts[i]);
          const w = Math.max(2, durations[i] * pps - 2);
          const sp = new PIXI.Sprite(tex);
          sp.position.set(x + 1, laneY(0) + 7);
          sp.width = w; sp.height = LANE_H - 14;
          const mask = new PIXI.Graphics().roundRect(x + 1, laneY(0) + 7, w, LANE_H - 14, 4).fill(0xffffff);
          sp.mask = mask;
          sp.eventMode = "static"; sp.cursor = "pointer";
          sp.on("pointerdown", () => { setSel(shot); ctl.current.t = starts[i]; drawHead(); });
          app.stage.addChildAt(mask, 1);
          app.stage.addChildAt(sp, 2);
        } catch { /* CORS/missing -> keep the colored block */ }
      });

      // expose selection redraw
      (ctl.current as { selG?: import("pixi.js").Graphics }).selG = selG;
      (ctl.current as { starts?: number[] }).starts = starts;
      (ctl.current as { durs?: number[] }).durs = durations;
    })();

    return () => { destroyed = true; if (app) app.destroy(true, { children: true }); };
  }, [shots]);

  // redraw selection highlight when sel changes
  useEffect(() => {
    const c = ctl.current as { selG?: import("pixi.js").Graphics; starts?: number[]; durs?: number[]; pps: number };
    if (!c.selG || !sel || !c.starts) return;
    const i = shots.findIndex((s) => s.id === sel.id);
    if (i < 0) return;
    c.selG.clear();
    const x = LABEL_W + c.starts[i] * c.pps;
    const w = Math.max(2, (c.durs?.[i] ?? 4) * c.pps - 2);
    c.selG.roundRect(x, RULER_H + 5, w + 2, LANE_H - 10, 5).stroke({ width: 2, color: COLORS.sel });
  }, [sel, shots]);

  function togglePlay() {
    if (ctl.current.t >= ctl.current.total) ctl.current.t = 0;
    ctl.current.playing = !ctl.current.playing;
    setPlaying(ctl.current.playing);
  }

  return (
    <div>
      <p className="muted"><a href={`/projects/${id}/storyboard`}>← Storyboard</a></p>
      <div className="spread">
        <h1>Timeline</h1>
        <span className="badge">WebGL · local</span>
      </div>
      {err && <p className="error">{err}</p>}
      {shots.length === 0 && !err && <p className="muted">No shots yet — plan a script in the Storyboard first.</p>}

      <div className="panel" style={{ padding: 12 }}>
        <div className="row" style={{ marginBottom: 10, alignItems: "center" }}>
          <button onClick={togglePlay} disabled={shots.length === 0} style={{ width: "auto" }}>
            {playing ? "⏸ pause" : "▶ play"}
          </button>
          <span className="mono muted" ref={timeRef}>0.0 / 0.0s</span>
          <span className="caption" style={{ marginLeft: "auto" }}>click a clip to select · drag the ruler to scrub</span>
        </div>
        <div ref={hostRef} style={{ width: "100%", overflow: "hidden", borderRadius: 8 }} />
      </div>

      {sel && (
        <div className="panel">
          <div className="spread">
            <strong>Shot {sel.idx + 1}</strong>
            <span className="badge">{sel.duration_s}s · {sel.camera}</span>
          </div>
          <p style={{ margin: "6px 0" }}>{sel.text}</p>
          <div className="pill-list">
            {sel.characters.map((cid) => <span key={cid} className="badge ok">{charMap[cid] ?? cid}</span>)}
            {sel.background && <span className="badge">{sel.background}</span>}
          </div>
        </div>
      )}
    </div>
  );
}
