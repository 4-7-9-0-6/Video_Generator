"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { api, type Character, type Project, type Style } from "@/lib/api";

const ALL_SHEETS = ["turnaround", "expressions", "poses"];

export default function ProjectPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();

  const [project, setProject] = useState<Project | null>(null);
  const [characters, setCharacters] = useState<Character[]>([]);
  const [styles, setStyles] = useState<Style[]>([]);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [style, setStyle] = useState("3d_toddler_original");
  const [palette, setPalette] = useState("");
  const [sheets, setSheets] = useState<string[]>(ALL_SHEETS);

  async function refresh() {
    try {
      const [prj, chars, sty] = await Promise.all([
        api.getProject(id),
        api.listCharacters(id),
        api.styles(),
      ]);
      setProject(prj);
      setCharacters(chars);
      setStyles(sty);
      setErr("");
    } catch (e) {
      setErr(String(e));
    }
  }

  useEffect(() => {
    if (id) refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  function toggleSheet(s: string) {
    setSheets((cur) => (cur.includes(s) ? cur.filter((x) => x !== s) : [...cur, s]));
  }

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr("");
    try {
      const res = await api.createCharacter({
        project_id: id,
        name: name.trim(),
        description: description.trim(),
        style_preset: style,
        palette: palette.split(",").map((s) => s.trim()).filter(Boolean),
        sheets,
      });
      router.push(`/characters/${res.character.id}`);
    } catch (e) {
      setErr(String(e));
      setBusy(false);
    }
  }

  return (
    <div>
      <p className="muted"><a href="/">← Projects</a></p>
      <div className="spread">
        <h1>{project ? project.name : "…"}</h1>
        <div className="row">
          <a className="badge" href={`/projects/${id}/transcript`}>📝 Transcript →</a>
          <a className="badge" href={`/projects/${id}/storyboard`}>🎞 Storyboard →</a>
          {project && <span className="badge">{project.style_preset} · {project.language}</span>}
        </div>
      </div>
      {err && <p className="error">{err}</p>}

      <form className="panel" onSubmit={create}>
        <h3>Create character (Foundry)</h3>
        <div className="grid cols-2">
          <div>
            <label>Name</label>
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Mila" />
          </div>
          <div>
            <label>Style preset</label>
            <select value={style} onChange={(e) => setStyle(e.target.value)}>
              {styles.map((s) => (
                <option key={s.id} value={s.id}>{s.id}</option>
              ))}
            </select>
          </div>
        </div>
        <label>Description</label>
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="4-year-old girl, big brown eyes, two curly pigtails, yellow t-shirt with a star, blue shorts, red sneakers"
        />
        <label>Palette (comma-separated hex, optional)</label>
        <input value={palette} onChange={(e) => setPalette(e.target.value)} placeholder="#FFD23F, #3A86FF, #FF5C5C" />
        <label>Sheets to generate</label>
        <div className="row">
          {ALL_SHEETS.map((s) => (
            <label key={s} className="row" style={{ margin: 0, color: "var(--text)", width: "auto" }}>
              <input
                type="checkbox"
                checked={sheets.includes(s)}
                onChange={() => toggleSheet(s)}
                style={{ width: "auto", marginRight: 6 }}
              />
              {s}
            </label>
          ))}
        </div>
        <div style={{ marginTop: 14 }}>
          <button disabled={busy || !name.trim() || !description.trim() || sheets.length === 0}>
            {busy ? "Creating…" : "Create & generate"}
          </button>
        </div>
      </form>

      <h2>Characters</h2>
      <div className="grid cols-4">
        {characters.map((c) => {
          const front = c.sheets?.turnaround?.[0];
          return (
            <a key={c.id} href={`/characters/${c.id}`} className="card">
              {front ? (
                <img className="thumb" src={api.assetUrl(front)} alt={c.name} />
              ) : (
                <div className="thumb" />
              )}
              <div className="caption" style={{ color: "var(--text)" }}>{c.name}</div>
            </a>
          );
        })}
        {characters.length === 0 && <p className="muted">No characters yet.</p>}
      </div>
    </div>
  );
}
