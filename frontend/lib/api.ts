// Typed client for the ToonForge FastAPI backend.

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export interface Project {
  id: string;
  name: string;
  language: string;
  style_preset: string;
  fps: number;
  width: number;
  height: number;
  safe_mode: number;
}

export interface Character {
  id: string;
  project_id: string;
  name: string;
  description: string;
  style_preset: string;
  palette: string[];
  style_tokens: string[];
  negative_prompt: string;
  embedding_id?: string | null;
  sheets: {
    turnaround?: string[];
    expressions?: Record<string, string>;
    poses?: Record<string, string>;
  };
  edits: { id: string; instruction: string; at: string }[];
  consistency: ConsistencyReport;
  lore?: Lore;
  ip_flagged: number;
}

export interface Lore {
  personality?: string;
  backstory?: string;
  abilities?: string[];
  archetype?: string;
  theme?: string;
  elements?: string[];
}

export interface ConsistencyReport {
  threshold?: number;
  method?: string | null;
  identity_view?: string | null;
  scores?: Record<string, number>;
  min_score?: number;
  passed?: boolean | null;
  regenerated?: Record<string, number>;
  note?: string;
}

export interface Job {
  id: string;
  project_id: string | null;
  type: string;
  status: "queued" | "running" | "succeeded" | "failed" | "cancelled";
  progress: number;
  message: string;
  payload: Record<string, unknown>;
  result: Record<string, unknown>;
  error: string;
}

export interface Asset {
  id: string;
  project_id: string | null;
  kind: string;
  path: string;
  mime: string;
  provider: string | null;
  cost_usd: number;
  gpu_seconds: number;
  meta: Record<string, unknown>;
  created_at: string;
}

export interface Shot {
  id: string;
  project_id: string;
  idx: number;
  text: string;
  characters: string[];
  camera: string;
  background: string;
  duration_s: number;
  keyframe_id?: string | null;
  clip_id?: string | null;
  status: string;
}

export interface TranscriptLine {
  id: string;
  idx: number;
  text: string;
  characters: string[];
  camera: string;
  background: string;
  duration_s: number;
  start_s: number;
  end_s: number;
  has_keyframe: boolean;
  stale: boolean;
}

export interface Style {
  id: string;
  description: string;
}

export interface ProviderProbe {
  capability: string;
  provider: string;
  selected: boolean;
  available: boolean;
  reason: string;
  install_hint: string;
  kind: string;
  free: boolean | null;
  requires_gpu: boolean | null;
}

async function req<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) {
    let detail: unknown;
    try {
      detail = (await res.json()).detail;
    } catch {
      detail = await res.text();
    }
    throw new Error(
      typeof detail === "string" ? detail : JSON.stringify(detail),
    );
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => req<{ status: string; version: string; languages: string[] }>("/health"),
  providers: () =>
    req<{ selected: Record<string, string>; providers: ProviderProbe[]; ready: ProviderProbe[]; unavailable: ProviderProbe[] }>(
      "/providers",
    ),
  styles: () => req<Style[]>("/styles"),

  listTemplates: () => req<{ id: string; title: string; description: string }[]>("/templates"),
  instantiateTemplate: (templateId: string) =>
    req<{ project: Project; characters: Character[]; shots: Shot[]; jobs: Job[] }>(
      `/templates/${templateId}/instantiate`, { method: "POST" },
    ),

  fromPrompt: (body: { prompt: string; style_preset: string; language?: string; scenes?: number; safe_mode?: boolean; render?: boolean }) =>
    req<{
      project: Project;
      song: { title: string; mood: string; has_chorus: boolean; characters: { name: string; description: string }[]; lines: { section: string; text: string; characters: string[] }[] };
      shots: Shot[];
      characters: string[];
      character_jobs: Job[];
    }>("/generate/from-prompt", { method: "POST", body: JSON.stringify(body) }),

  listAssets: (kind?: string, projectId?: string) => {
    const q = new URLSearchParams();
    if (kind) q.set("kind", kind);
    if (projectId) q.set("project_id", projectId);
    const s = q.toString();
    return req<Asset[]>(`/assets${s ? `?${s}` : ""}`);
  },
  deleteAsset: (id: string) => req<{ deleted: string }>(`/assets/${id}`, { method: "DELETE" }),

  gpuVideoAvailability: () =>
    req<{ available: boolean; hint: string; kernel: string | null }>(
      "/generate/gpu-video/availability",
    ),
  gpuVideo: (body: { prompt: string; style_preset: string; scenes?: number; project_id?: string }) =>
    req<{ job: Job; kernel: string; note: string }>(
      "/generate/gpu-video", { method: "POST", body: JSON.stringify(body) },
    ),

  listProjects: () => req<Project[]>("/projects"),
  createProject: (body: { name: string; language?: string; style_preset?: string }) =>
    req<Project>("/projects", { method: "POST", body: JSON.stringify(body) }),
  getProject: (id: string) => req<Project>(`/projects/${id}`),
  listCharacters: (projectId: string) =>
    req<Character[]>(`/projects/${projectId}/characters`),

  createCharacter: (body: {
    project_id: string;
    name: string;
    description: string;
    style_preset: string;
    palette: string[];
    sheets: string[];
  }) =>
    req<{ character: Character; job: Job }>("/characters", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  getCharacter: (id: string) => req<Character>(`/characters/${id}`),
  regenerateLore: (id: string) => req<Lore>(`/characters/${id}/lore`, { method: "POST" }),
  editCharacter: (id: string, instruction: string, sheets: string[]) =>
    req<{ character: Character; applied: unknown; job?: Job }>(
      `/characters/${id}/edit`,
      { method: "POST", body: JSON.stringify({ instruction, sheets }) },
    ),

  listJobs: (projectId?: string) =>
    req<Job[]>(`/jobs${projectId ? `?project_id=${projectId}` : ""}`),
  getJob: (jobId: string) => req<Job>(`/jobs/${jobId}`),

  exportPresets: () =>
    req<Record<string, { width: number; height: number }>>("/export/presets"),
  exportGrades: () => req<string[]>("/export/grades"),
  socialPack: (projectId: string, platform = "youtube") =>
    req<{
      platform: string; titles: string[]; description: string; hashtags: string[];
      hashtag_string: string; caption: string;
      virality: { score: number; grade: string; reasons: string[]; tips: string[] };
    }>(`/projects/${projectId}/social-pack?platform=${encodeURIComponent(platform)}`, { method: "POST" }),
  exportEpisode: (projectId: string, body: { preset: string; voice: boolean; sing?: boolean; sing_key?: string; sing_tempo?: number; sing_vibrato?: number; lipsync?: boolean; subtitles: boolean; word_subtitles?: boolean; music?: boolean; music_auto?: boolean; smart_reframe?: boolean; grade?: string }) =>
    req<Job>(`/projects/${projectId}/export`, { method: "POST", body: JSON.stringify(body) }),
  musicBrief: (projectId: string) =>
    req<{ mood: string; description: string; tempo: number; key: string; match_score: number }>(
      `/projects/${projectId}/music-brief`,
    ),
  reframePreviewUrl: (shotId: string, preset: string) =>
    `${API_BASE}/shots/${shotId}/reframe?preset=${encodeURIComponent(preset)}`,
  projectCost: (projectId: string) =>
    req<{ assets: number; by_kind: Record<string, number>; gpu_seconds: number; usd: number; note: string }>(
      `/projects/${projectId}/cost`,
    ),

  planScript: (projectId: string, script: string, defaultBackground: string) =>
    req<Shot[]>(`/projects/${projectId}/plan`, {
      method: "POST",
      body: JSON.stringify({ script, default_background: defaultBackground }),
    }),
  listShots: (projectId: string) => req<Shot[]>(`/projects/${projectId}/shots`),
  patchShot: (shotId: string, changes: Partial<Pick<Shot, "text" | "camera" | "background" | "duration_s">>) =>
    req<Shot>(`/shots/${shotId}`, { method: "PATCH", body: JSON.stringify(changes) }),
  renderKeyframe: (shotId: string, force = false) =>
    req<Job>(`/shots/${shotId}/keyframe?force=${force}`, { method: "POST" }),
  renderAllKeyframes: (projectId: string, force = false) =>
    req<Job[]>(`/projects/${projectId}/render-keyframes?force=${force}`, { method: "POST" }),
  motionPresets: () => req<Record<string, { hint: string; kind: string }>>("/motion-presets"),

  getTranscript: (projectId: string) =>
    req<{ shots: TranscriptLine[]; count: number; total_duration_s: number }>(
      `/projects/${projectId}/transcript`,
    ),
  insertShot: (projectId: string, body: { text: string; after_id?: string; characters?: string[]; background?: string }) =>
    req<Shot>(`/projects/${projectId}/shots`, { method: "POST", body: JSON.stringify(body) }),
  deleteShot: (shotId: string) =>
    req<{ deleted: string; count: number }>(`/shots/${shotId}`, { method: "DELETE" }),
  reorderShots: (projectId: string, order: string[]) =>
    req<Shot[]>(`/projects/${projectId}/transcript/reorder`, {
      method: "POST", body: JSON.stringify({ order }),
    }),

  listVoices: () =>
    req<{ available: boolean; languages: string[]; voices: Record<string, string> }>(
      "/voice/voices",
    ),
  tts: (body: { text: string; language: string; speed: number; project_id?: string }) =>
    req<{ asset_id: string; url: string; mime: string; duration_s: number; language: string; voice: string }>(
      "/voice/tts",
      { method: "POST", body: JSON.stringify(body) },
    ),
  melody: (body: { description: string; key?: string; tempo?: number; duration_s?: number; project_id?: string }) =>
    req<{ asset_id: string; url: string; mime: string; meta: Record<string, unknown> }>(
      "/voice/melody",
      { method: "POST", body: JSON.stringify(body) },
    ),
  sing: (body: { lyrics: string; language: string; key: string; tempo: number; vibrato: number; project_id?: string }) =>
    req<{ asset_id: string; url: string; mime: string; duration_s: number; key: string; tempo: number; note: string }>(
      "/voice/sing",
      { method: "POST", body: JSON.stringify(body) },
    ),

  proposeThumbnails: (projectId: string, body: { title?: string; count?: number; character_id?: string; background?: string }) =>
    req<Job>(`/projects/${projectId}/thumbnails`, { method: "POST", body: JSON.stringify(body) }),
  listThumbnails: (projectId: string) =>
    req<{ asset_id: string; title: string | null; variant: number | null; created_at: string }[]>(
      `/projects/${projectId}/thumbnails`,
    ),

  assetUrl: (assetId: string) => `${API_BASE}/assets/${assetId}`,
};
