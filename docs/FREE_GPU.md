# Free-GPU rendering — animated + sung + lip-synced videos for $0

The CPU app makes modern *stills* (Cloudflare Flux) + Ken Burns + narration. To get **real
character animation, real singing, and lip-sync**, you need a GPU — but you don't have to pay:
run `scripts/gpu_render.py` on a **free cloud GPU** (16 GB T4/P100 is plenty), then download
the MP4. When one service's free quota runs out, run the *same* steps on the next.

| Service | Free GPU | Free quota | Notes |
|---|---|---|---|
| **Kaggle** | P100 / T4 16 GB | **30 hrs/week** | most stable; background-runs after you close the tab |
| **Google Colab** | T4 16 GB | ~15–30 hrs/week | easiest; 12 hr session cap |
| **Lightning AI** | T4/L4/A10G | **22 GPU-hrs/month** | persistent VS Code env + storage |

**Rotation = robust & ToS-safe.** This is a *batch render job* (using the GPU as intended),
not a hosted server — so it doesn't risk account bans the way tunneling a live API does. When
Kaggle's 30 h/week is spent, run the same cells on Colab or Lightning.

---

## What it produces
`prompt → LLM lyrics → ACE-Step sings the whole song (vocals+music) → Flux keyframes per line
→ LTX animates each (or SadTalker lip-syncs each) → concat + sung track + subtitles → MP4.`

You need two free keys in the cells: **OpenRouter** (lyrics) and **Cloudflare** (Flux images) —
both already set up for the CPU app. The GPU runs **ACE-Step** (singing), **LTX** (animation),
and optionally **SadTalker** (lip-sync).

---

## Kaggle / Colab cells (paste each into a cell, run top to bottom)

**Cell 1 — get the code + base deps**
```bash
# Public repo: clones directly. Private repo: first run a Python cell -> import os; os.environ['GITHUB_TOKEN']='ghp_...'
!git clone https://${GITHUB_TOKEN:+$GITHUB_TOKEN@}github.com/4-7-9-0-6/Video_Generator.git || true
%cd Video_Generator/backend
!pip install -q -r requirements.txt
!pip install -q "diffusers>=0.32" "transformers>=4.44" accelerate sentencepiece imageio[ffmpeg] acestep
```

**Cell 2 — GPU check + your free keys**
```python
import torch, os
print("GPU:", torch.cuda.get_device_name(0) if torch.cuda.is_available() else "NONE — set Runtime/Accelerator to GPU")
os.environ["OPENROUTER_API_KEY"]   = "sk-or-..."      # free: openrouter.ai
os.environ["CLOUDFLARE_ACCOUNT_ID"] = "..."           # free: dash.cloudflare.com -> Workers AI
os.environ["CLOUDFLARE_API_TOKEN"]  = "..."
os.environ["PROVIDER_IMAGE"] = "cloudflare"           # fast free Flux for the stills
os.environ["PROVIDER_VIDEO"] = "ltx_local"            # GPU animation
os.environ["PROVIDER_SVS"]   = "acestep_local"        # GPU singing
```

**Cell 3 — render (LTX animation + ACE-Step singing)**
```bash
!python scripts/gpu_render.py --prompt "a brave little robot lights up a neon city at night" \
    --style anime_cyberpunk --scenes 6 --out /kaggle/working/song.mp4
```
The MP4 lands in the Kaggle/Colab output panel — download it. First run downloads the ACE-Step
+ LTX checkpoints (a few GB) once.

**Optional — lip-sync instead of scene animation (SadTalker):**
```bash
!git clone https://github.com/OpenTalker/SadTalker && (cd SadTalker && bash scripts/download_models.sh)
!pip install -q face_alignment gfpgan kornia yacs pydub safetensors librosa
```
```python
import os; os.environ["SADTALKER_DIR"] = "/kaggle/working/Video_Generator/backend/SadTalker"
os.environ["PROVIDER_LIPSYNC"] = "sadtalker_local"
```
```bash
!python scripts/gpu_render.py --prompt "..." --style 3d_toddler_original --lipsync --out /kaggle/working/song_lipsync.mp4
```

## Lightning AI (persistent — best for repeated runs)
Same commands in a Lightning **Studio** terminal (clone once, keys persist in the studio). Its
22 GPU-hrs/month is enough for many videos; switch to Kaggle when it's spent.

---

## Honest notes
- **T4 (16 GB) fits all three** (LTX small model, ACE-Step ~8–12 GB, SadTalker modest).
- **Animation vs lip-sync are alternatives per shot** — LTX animates the whole scene; SadTalker
  animates the face to the audio. The script does one mode at a time (`--lipsync` switches).
- **Not runtime-verified on a GPU from here** — the ACE-Step/SadTalker call signatures vary by
  version, so the first GPU run may need a one-line tweak in their providers. The structure is right.
- **Rotation** = run the same cells wherever you have free hours left. No always-on server, so no
  ToS/ban risk.
