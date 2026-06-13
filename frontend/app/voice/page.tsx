"use client";

import { useEffect, useState } from "react";
import { api, API_BASE } from "@/lib/api";

export default function VoiceLabPage() {
  const [languages, setLanguages] = useState<string[]>(["en", "fr"]);
  const [available, setAvailable] = useState<boolean | null>(null);

  // TTS
  const [text, setText] = useState("Hello! I am Mila, and I love to sing.");
  const [language, setLanguage] = useState("en");
  const [speed, setSpeed] = useState(1.0);
  const [audioUrl, setAudioUrl] = useState("");
  const [ttsInfo, setTtsInfo] = useState("");
  const [ttsErr, setTtsErr] = useState("");
  const [ttsBusy, setTtsBusy] = useState(false);

  // Melody
  const [melodyDesc, setMelodyDesc] = useState("upbeat C-major nursery melody, AABB");
  const [tempo, setTempo] = useState(96);
  const [melodyUrl, setMelodyUrl] = useState("");
  const [melodyMeta, setMelodyMeta] = useState("");
  const [melodyBusy, setMelodyBusy] = useState(false);

  // Sing (SVS)
  const [lyrics, setLyrics] = useState("Twinkle twinkle little star, how I wonder what you are");
  const [singLang, setSingLang] = useState("en");
  const [singKey, setSingKey] = useState("C");
  const [singTempo, setSingTempo] = useState(100);
  const [vibrato, setVibrato] = useState(0.3);
  const [singUrl, setSingUrl] = useState("");
  const [singInfo, setSingInfo] = useState("");
  const [singErr, setSingErr] = useState("");
  const [singBusy, setSingBusy] = useState(false);

  useEffect(() => {
    api.listVoices()
      .then((v) => { setLanguages(v.languages); setAvailable(v.available); })
      .catch(() => setAvailable(false));
  }, []);

  async function speak(e: React.FormEvent) {
    e.preventDefault();
    setTtsBusy(true); setTtsErr(""); setAudioUrl("");
    try {
      const r = await api.tts({ text, language, speed });
      setAudioUrl(`${API_BASE}${r.url}?t=${Date.now()}`);
      setTtsInfo(`${r.voice} · ${r.duration_s}s`);
    } catch (e) {
      setTtsErr(String(e));
    } finally {
      setTtsBusy(false);
    }
  }

  async function compose(e: React.FormEvent) {
    e.preventDefault();
    setMelodyBusy(true); setMelodyUrl("");
    try {
      const r = await api.melody({ description: melodyDesc, tempo, duration_s: 16 });
      setMelodyUrl(`${API_BASE}${r.url}`);
      setMelodyMeta(JSON.stringify(r.meta));
    } catch (e) {
      setMelodyMeta(String(e));
    } finally {
      setMelodyBusy(false);
    }
  }

  async function sing(e: React.FormEvent) {
    e.preventDefault();
    setSingBusy(true); setSingErr(""); setSingUrl("");
    try {
      const r = await api.sing({ lyrics, language: singLang, key: singKey, tempo: singTempo, vibrato });
      setSingUrl(`${API_BASE}${r.url}?t=${Date.now()}`);
      setSingInfo(`${r.key} · ${r.tempo} BPM · ${r.duration_s}s · ${r.note}`);
    } catch (e) {
      setSingErr(String(e));
    } finally {
      setSingBusy(false);
    }
  }

  return (
    <div>
      <p className="muted"><a href="/">← Home</a></p>
      <div className="spread">
        <h1>VoiceLab</h1>
        {available !== null && (
          <span className={`badge ${available ? "ok" : "warn"}`}>
            TTS {available ? "ready (Piper, local)" : "unavailable — run scripts/download_voices.py"}
          </span>
        )}
      </div>

      <form className="panel" onSubmit={speak}>
        <h3>Speak (text → speech, EN/FR)</h3>
        <textarea value={text} onChange={(e) => setText(e.target.value)} />
        <div className="row" style={{ marginTop: 10 }}>
          <div>
            <label>Language</label>
            <select value={language} onChange={(e) => setLanguage(e.target.value)}>
              {languages.map((l) => <option key={l} value={l}>{l}</option>)}
            </select>
          </div>
          <div>
            <label>Speed · {speed.toFixed(2)}×</label>
            <input type="range" min={0.5} max={2} step={0.05}
                   value={speed} onChange={(e) => setSpeed(parseFloat(e.target.value))} />
          </div>
          <div style={{ alignSelf: "end" }}>
            <button disabled={ttsBusy || !text.trim()}>{ttsBusy ? "synthesizing…" : "Speak"}</button>
          </div>
        </div>
        {ttsErr && <p className="error">{ttsErr}</p>}
        {audioUrl && (
          <div style={{ marginTop: 12 }}>
            <audio controls src={audioUrl} style={{ width: "100%" }} />
            <div className="caption">{ttsInfo}</div>
          </div>
        )}
      </form>

      <form className="panel" onSubmit={compose}>
        <h3>Compose melody (text → MIDI the SVS will sing)</h3>
        <input value={melodyDesc} onChange={(e) => setMelodyDesc(e.target.value)} />
        <div className="row" style={{ marginTop: 10 }}>
          <div>
            <label>Tempo · {tempo} BPM</label>
            <input type="range" min={40} max={200} step={2}
                   value={tempo} onChange={(e) => setTempo(parseInt(e.target.value))} />
          </div>
          <div style={{ alignSelf: "end" }}>
            <button disabled={melodyBusy}>{melodyBusy ? "composing…" : "Compose"}</button>
          </div>
        </div>
        {melodyUrl && (
          <p style={{ marginTop: 10 }}>
            <a href={melodyUrl} download>⬇ download melody.mid</a> <span className="mono muted">{melodyMeta}</span>
          </p>
        )}
        {!melodyUrl && melodyMeta && <p className="error">{melodyMeta}</p>}
      </form>

      <form className="panel" onSubmit={sing}>
        <h3>🎤 Sing (lyrics → sung vocals, local CPU)</h3>
        <textarea value={lyrics} onChange={(e) => setLyrics(e.target.value)}
          placeholder="Paste lyrics — the app sings them to an auto melody in your key." />
        <div className="row" style={{ marginTop: 10, flexWrap: "wrap", gap: 14 }}>
          <div>
            <label>Language</label>
            <select value={singLang} onChange={(e) => setSingLang(e.target.value)}>
              {languages.map((l) => <option key={l} value={l}>{l}</option>)}
            </select>
          </div>
          <div>
            <label>Key</label>
            <select value={singKey} onChange={(e) => setSingKey(e.target.value)}>
              {["C", "D", "E", "F", "G", "A", "A minor", "E minor", "D minor"].map((k) =>
                <option key={k} value={k}>{k}</option>)}
            </select>
          </div>
          <div>
            <label>Tempo · {singTempo} BPM</label>
            <input type="range" min={50} max={180} step={2}
                   value={singTempo} onChange={(e) => setSingTempo(parseInt(e.target.value))} />
          </div>
          <div>
            <label>Vibrato · {vibrato.toFixed(2)}</label>
            <input type="range" min={0} max={1} step={0.05}
                   value={vibrato} onChange={(e) => setVibrato(parseFloat(e.target.value))} />
          </div>
          <div style={{ alignSelf: "end" }}>
            <button disabled={singBusy || !lyrics.trim()}>{singBusy ? "singing…" : "Sing it"}</button>
          </div>
        </div>
        {singErr && <p className="error">{singErr}</p>}
        {singUrl && (
          <div style={{ marginTop: 12 }}>
            <audio controls src={singUrl} style={{ width: "100%" }} />
            <div className="caption">{singInfo}</div>
          </div>
        )}
        <p className="muted" style={{ marginTop: 10 }}>
          Local CPU singing: Piper voice pitch-warped to the melody (formant-preserved +
          vibrato). Fun/stylized quality — studio-grade neural SVS (DiffSinger) is the GPU upgrade.
        </p>
      </form>
    </div>
  );
}
