# In-app GPU render (the app drives a free Kaggle GPU)

Real **singing** (ACE-Step) and real **animation** (LTX) need an NVIDIA GPU this machine doesn't
have. Instead of pasting cells into a Kaggle notebook, the app can dispatch the whole render to
your **free Kaggle GPU** and pull the finished MP4 back into the app — one button.

It works by building a **private Kaggle kernel** (a batch script) that clones the repo, installs
the deps, and runs `scripts/gpu_render.py` with your prompt, then the app polls it and downloads
`song.mp4`. This is the ToS-safe "batch job" model (not a tunneled server).

```
App  ──(Kaggle API)──>  private kernel on a free Kaggle GPU  ──>  song.mp4  ──>  back into the app
        push + poll          ACE-Step singing + Flux + LTX            download         saved as a video asset
```

---

## One-time setup (~3 minutes)

1. **Install the Kaggle CLI** (already in `requirements.txt`):
   ```
   pip install kaggle
   ```

2. **Create a Kaggle API token:** kaggle.com → click your avatar → **Settings** → **API** →
   **Create New Token**. This downloads `kaggle.json`. Put it at:
   - Windows: `C:\Users\<you>\.kaggle\kaggle.json`
   - Linux/Mac: `~/.kaggle/kaggle.json`

   (Or instead set `KAGGLE_USERNAME` and `KAGGLE_KEY` in `backend/.env`.)

3. **Phone-verify your Kaggle account** (kaggle.com → Settings → Phone Verification) — required
   before Kaggle will give any notebook a GPU.

4. **Make sure the repo the kernel clones is reachable.** Default is the public
   `KAGGLE_RENDER_REPO=https://github.com/4-7-9-0-6/Video_Generator.git`. If you fork it, set
   `KAGGLE_RENDER_REPO` in `backend/.env` to your fork's URL.

5. Restart the backend. The home page's **"🎥 Render on GPU"** panel should show **"Kaggle ready"**.

---

## Use it

1. On the app home page, type your prompt in the **"Create a video from a prompt"** box.
2. In the **"🎥 Render on GPU"** panel below it, pick the style/scenes (shared with the prompt box)
   and click **Render on GPU**.
3. A progress bar tracks the Kaggle run (queued → running → downloading). **It takes ~30–40 min.**
   You can leave the page open; it polls every 15s.
4. When done, the video player appears with a **download** link. The MP4 is also saved as a project
   asset.

---

## How keys are handled

The kernel needs your **OpenRouter** (lyrics) and **Cloudflare** (Flux images) keys. The app reads
them from `backend/.env` and writes them into the **private** kernel it pushes — so they're visible
only to your own Kaggle account. They are *not* committed to the repo. If you'd rather not put keys
in a kernel at all, you can switch to Kaggle Secrets later; for a personal tool the private kernel
is the simple path.

---

## Limits & notes

- **Quota:** Kaggle gives ~30 GPU-hours/week. Each video is ~35–45 min of GPU (install + render),
  so budget roughly **30–40 videos/week**.
- **One at a time:** the in-process worker is busy for the whole render, so one GPU video runs at a
  time. (The app stays responsive — it's all `await`-based.)
- **First run per session is slower** — Kaggle reinstalls deps and downloads the ACE-Step + LTX
  checkpoints (a few GB) each fresh kernel run.
- **Tuning:** the kernel honors the same env knobs as the notebook — `LTX_MAX_WIDTH/HEIGHT/FRAMES`,
  `LTX_STEPS`, `GPU_OFFLOAD`. On a bigger (paid) GPU you'd raise the LTX caps for sharper/longer
  motion.
- **Troubleshooting:** if a render fails, open the kernel on kaggle.com (it's at
  `kaggle.com/code/<your-username>/toonforge-render`) to read the full log.

---

## Config (`backend/.env`)

```
KAGGLE_USERNAME=                 # or place kaggle.json at ~/.kaggle/kaggle.json
KAGGLE_KEY=
KAGGLE_RENDER_REPO=https://github.com/4-7-9-0-6/Video_Generator.git
KAGGLE_KERNEL_SLUG=              # blank -> <username>/toonforge-render
KAGGLE_POLL_INTERVAL_S=30
KAGGLE_TIMEOUT_S=3600
```
