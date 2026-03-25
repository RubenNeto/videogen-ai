"""
Interface Web com Gradio - UI 2026 Redesign
TikTok Video Generator - Creator Studio
"""

import gradio as gr
import logging
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from config.settings import THEMES, SUBTITLE_STYLES, VIDEO_FORMAT, VIDEOS_DIR
from pipeline import VideoGenerationPipeline
from job_queue.video_queue import VideoQueue, JobStatus

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
logger = logging.getLogger(__name__)

pipeline = None
video_queue = None

def get_pipeline():
    global pipeline, video_queue
    if pipeline is None:
        pipeline = VideoGenerationPipeline()
        video_queue = VideoQueue(pipeline)
        video_queue.start(num_workers=2)
    return pipeline, video_queue

# ─── Lógica ───────────────────────────────────────────────────────────────────

VOICE_MAP = {
    "Feminina PT 🇵🇹": "pt_female",
    "Masculina PT 🇵🇹": "pt_male",
    "Feminine EN 🇬🇧": "en_female",
    "Masculine EN 🇬🇧": "en_male",
    "Femenina ES 🇪🇸": "es_female",
    "Masculino ES 🇪🇸": "es_male",
    "Robótica 🤖": "robotic",
}
LANG_MAP = {
    "Português 🇵🇹": "pt",
    "English 🇬🇧": "en",
    "Español 🇪🇸": "es",
    "Français 🇫🇷": "fr",
}
THEME_MAP = {v["name"]: k for k, v in THEMES.items()}
THEME_CHOICES = [f"{v['emoji']} {v['name']}" for v in THEMES.values()]
THEME_EMOJI_MAP = {f"{v['emoji']} {v['name']}": k for k, v in THEMES.items()}

def generate_single_video(
    theme_full, duration, voice_type, language,
    subtitle_style, topic, add_music, music_volume,
    progress=gr.Progress()
):
    progress(0, desc="A inicializar agentes...")
    pipe, _ = get_pipeline()

    def on_progress(step, total, message, job_id):
        progress(step / total, desc=message)

    theme_key = THEME_EMOJI_MAP.get(theme_full, "curiosidades")
    voice_key = VOICE_MAP.get(voice_type, "pt_female")
    lang_key = LANG_MAP.get(language, "pt")

    result = pipe.generate_video(
        theme=theme_key,
        duration=int(duration),
        voice_type=voice_key,
        language=lang_key,
        subtitle_style=subtitle_style.lower(),
        topic=topic.strip() if topic and topic.strip() else None,
        add_music=add_music,
        music_volume=music_volume,
        progress_callback=on_progress
    )

    progress(1.0, desc="Concluído!")

    if result["success"]:
        script = result.get("script", {})
        hook = script.get("hook", "—")
        cenas = script.get("cenas", [])
        hashtags = " ".join(script.get("hashtags", []))
        dur = result.get("duration_real", int(duration))
        size = result.get("size_mb", 0)
        elapsed = result.get("elapsed_seconds", 0)
        scenes_count = result.get("scenes_count", 0)
        fname = result.get("video_name", "")

        cenas_html = "".join(
            f'<div class="scene-item"><span class="scene-num">{i+1}</span><span class="scene-text">{c.get("texto","")}</span></div>'
            for i, c in enumerate(cenas[:6])
        )

        info_html = f"""
<div class="result-card">
  <div class="result-header">
    <span class="result-badge success">✓ GERADO</span>
    <span class="result-file">{fname}</span>
  </div>
  <div class="result-stats">
    <div class="stat"><span class="stat-val">{dur:.0f}s</span><span class="stat-label">Duração</span></div>
    <div class="stat"><span class="stat-val">{scenes_count}</span><span class="stat-label">Cenas</span></div>
    <div class="stat"><span class="stat-val">{size:.1f}MB</span><span class="stat-label">Tamanho</span></div>
    <div class="stat"><span class="stat-val">{elapsed:.0f}s</span><span class="stat-label">Geração</span></div>
  </div>
  <div class="result-hook">
    <span class="hook-label">HOOK</span>
    <span class="hook-text">"{hook}"</span>
  </div>
  <div class="result-scenes">
    <div class="scenes-label">CENAS</div>
    {cenas_html}
  </div>
  <div class="result-hashtags">{hashtags}</div>
</div>"""
        return result["video_path"], info_html
    else:
        err = result.get("error", "Erro desconhecido")
        return None, f'<div class="result-card error-card"><span class="result-badge error">✗ ERRO</span><p>{err}</p></div>'


def add_to_batch_queue(theme_full, duration, voice_type, language,
                       subtitle_style, topic, add_music, music_volume, num_videos):
    _, q = get_pipeline()
    config = {
        "theme": THEME_EMOJI_MAP.get(theme_full, "curiosidades"),
        "duration": int(duration),
        "voice_type": VOICE_MAP.get(voice_type, "pt_female"),
        "language": LANG_MAP.get(language, "pt"),
        "subtitle_style": subtitle_style.lower(),
        "topic": topic.strip() if topic and topic.strip() else None,
        "add_music": add_music,
        "music_volume": music_volume,
    }
    job_ids = []
    for _ in range(int(num_videos)):
        job = q.add_job(config.copy())
        job_ids.append(job.job_id)

    ids_str = " · ".join(f'<code>{jid}</code>' for jid in job_ids)
    return f'<div class="result-card"><span class="result-badge success">✓ {num_videos} JOBS CRIADOS</span><p style="margin-top:12px;opacity:.7">IDs: {ids_str}</p></div>'


def get_queue_status():
    if video_queue is None:
        return '<div class="queue-empty">Sistema não iniciado. Gera um vídeo primeiro.</div>'
    jobs = video_queue.get_all_jobs()
    if not jobs:
        return '<div class="queue-empty">Fila vazia — nenhum job em curso.</div>'

    status_map = {
        "pending":   ("⏳", "status-pending"),
        "running":   ("▶", "status-running"),
        "completed": ("✓", "status-done"),
        "failed":    ("✗", "status-error"),
        "cancelled": ("○", "status-cancel"),
    }

    rows = ""
    for job in sorted(jobs, key=lambda x: x.get("created_at",""), reverse=True)[:12]:
        s = job["status"]
        icon, cls = status_map.get(s, ("?", ""))
        jid = job["job_id"]
        theme = job.get("config", {}).get("theme", "?")
        dur = job.get("config", {}).get("duration", "?")
        msg = job.get("progress_message", "")
        step = job.get("progress_step", 0)
        total = job.get("progress_total", 6)
        pct = int(step / max(total,1) * 100)

        progress_bar = ""
        if s == "running":
            progress_bar = f'<div class="qpbar"><div class="qpbar-fill" style="width:{pct}%"></div></div>'

        rows += f"""
<div class="queue-row {cls}">
  <span class="q-icon">{icon}</span>
  <span class="q-id">{jid}</span>
  <span class="q-theme">{theme} · {dur}s</span>
  <span class="q-msg">{msg}</span>
  {progress_bar}
</div>"""

    return f'<div class="queue-list">{rows}</div>'


def list_generated_videos():
    videos = sorted(VIDEOS_DIR.glob(f"*.{VIDEO_FORMAT}"),
                    key=lambda x: x.stat().st_mtime, reverse=True)
    if not videos:
        return '<div class="queue-empty">Nenhum vídeo gerado ainda.</div>'

    cards = ""
    for v in videos[:24]:
        size = v.stat().st_size / 1024 / 1024
        mtime = time.strftime("%d %b · %H:%M", time.localtime(v.stat().st_mtime))
        name_short = v.stem[:28] + "…" if len(v.stem) > 28 else v.stem
        cards += f"""
<div class="video-card">
  <div class="video-thumb">▶</div>
  <div class="video-info">
    <div class="video-name" title="{v.name}">{name_short}</div>
    <div class="video-meta">{size:.1f} MB · {mtime}</div>
  </div>
</div>"""

    return f'<div class="video-grid">{cards}</div>'


# ─── CSS ──────────────────────────────────────────────────────────────────────

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');

:root {
  --bg:       #0a0a0f;
  --surface:  #111118;
  --card:     #16161f;
  --border:   #252535;
  --accent:   #ff2d55;
  --accent2:  #bf5af2;
  --accent3:  #0aff9d;
  --text:     #f0f0ff;
  --muted:    #666680;
  --radius:   12px;
  --font:     'Syne', sans-serif;
  --mono:     'JetBrains Mono', monospace;
}

/* Reset geral */
.gradio-container {
  background: var(--bg) !important;
  font-family: var(--font) !important;
  max-width: 1280px !important;
  margin: 0 auto !important;
  padding: 0 !important;
}
body, .dark { background: var(--bg) !important; }
footer { display: none !important; }
.svelte-1gfkn6j { display: none !important; }

/* Inputs & labels */
label, .label-wrap { color: var(--muted) !important; font-family: var(--mono) !important; font-size: 10px !important; letter-spacing: 0.12em !important; text-transform: uppercase !important; }
input, textarea, select, .wrap { background: var(--card) !important; border: 1px solid var(--border) !important; border-radius: var(--radius) !important; color: var(--text) !important; font-family: var(--font) !important; }
input:focus, textarea:focus { border-color: var(--accent) !important; box-shadow: 0 0 0 2px rgba(255,45,85,.15) !important; outline: none !important; }
.block { background: transparent !important; border: none !important; padding: 0 !important; }

/* Dropdowns */
.dropdown-arrow, svg { color: var(--muted) !important; }
ul.options { background: var(--card) !important; border: 1px solid var(--border) !important; border-radius: var(--radius) !important; }
ul.options li { color: var(--text) !important; }
ul.options li:hover, ul.options li.selected { background: rgba(255,45,85,.12) !important; color: var(--accent) !important; }

/* Slider */
input[type=range] { accent-color: var(--accent) !important; }

/* Checkbox */
input[type=checkbox] { accent-color: var(--accent) !important; }

/* Tabs */
.tabs { border: none !important; background: transparent !important; }
.tab-nav { background: var(--surface) !important; border-bottom: 1px solid var(--border) !important; padding: 0 24px !important; gap: 0 !important; border-radius: 0 !important; }
.tab-nav button {
  background: transparent !important;
  border: none !important;
  border-bottom: 2px solid transparent !important;
  color: var(--muted) !important;
  font-family: var(--mono) !important;
  font-size: 11px !important;
  letter-spacing: .1em !important;
  padding: 16px 20px !important;
  border-radius: 0 !important;
  transition: all .2s !important;
  text-transform: uppercase !important;
}
.tab-nav button.selected {
  color: var(--accent) !important;
  border-bottom-color: var(--accent) !important;
  background: transparent !important;
}
.tab-nav button:hover { color: var(--text) !important; }
.tabitem { background: transparent !important; border: none !important; padding: 32px 24px !important; }

/* Botão primário */
button.primary, .primary {
  background: linear-gradient(135deg, var(--accent), var(--accent2)) !important;
  border: none !important;
  border-radius: var(--radius) !important;
  color: #fff !important;
  font-family: var(--mono) !important;
  font-size: 12px !important;
  font-weight: 500 !important;
  letter-spacing: .12em !important;
  text-transform: uppercase !important;
  padding: 14px 28px !important;
  transition: all .2s !important;
  box-shadow: 0 4px 24px rgba(255,45,85,.25) !important;
}
button.primary:hover { transform: translateY(-1px) !important; box-shadow: 0 8px 32px rgba(255,45,85,.35) !important; }
button.secondary {
  background: var(--card) !important;
  border: 1px solid var(--border) !important;
  border-radius: var(--radius) !important;
  color: var(--text) !important;
  font-family: var(--mono) !important;
  font-size: 11px !important;
  letter-spacing: .1em !important;
  text-transform: uppercase !important;
  transition: all .2s !important;
}
button.secondary:hover { border-color: var(--accent) !important; color: var(--accent) !important; }

/* Progress bar */
.progress-bar { background: var(--border) !important; border-radius: 99px !important; }
.progress-bar > div { background: linear-gradient(90deg, var(--accent), var(--accent2)) !important; border-radius: 99px !important; }

/* Video player */
video { border-radius: var(--radius) !important; background: var(--card) !important; }
.video-container { background: var(--card) !important; border: 1px solid var(--border) !important; border-radius: var(--radius) !important; }

/* ── HEADER ── */
.studio-header {
  background: linear-gradient(180deg, rgba(255,45,85,.06) 0%, transparent 100%);
  border-bottom: 1px solid var(--border);
  padding: 32px 24px 24px;
  text-align: center;
}
.studio-logo {
  font-family: var(--font);
  font-size: 13px;
  font-weight: 800;
  letter-spacing: .3em;
  text-transform: uppercase;
  color: var(--muted);
  margin-bottom: 12px;
}
.studio-title {
  font-family: var(--font);
  font-size: clamp(2rem, 5vw, 3.5rem);
  font-weight: 800;
  color: var(--text);
  letter-spacing: -.02em;
  line-height: 1;
  margin-bottom: 8px;
}
.studio-title span { color: var(--accent); }
.studio-sub {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--muted);
  letter-spacing: .12em;
  text-transform: uppercase;
}
.studio-pills {
  display: flex;
  gap: 8px;
  justify-content: center;
  flex-wrap: wrap;
  margin-top: 20px;
}
.pill {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 99px;
  padding: 5px 14px;
  font-family: var(--mono);
  font-size: 10px;
  color: var(--muted);
  letter-spacing: .08em;
  text-transform: uppercase;
}
.pill.hot { border-color: rgba(255,45,85,.4); color: var(--accent); }
.pill.green { border-color: rgba(10,255,157,.3); color: var(--accent3); }

/* ── SECTION LABELS ── */
.section-label {
  font-family: var(--mono);
  font-size: 10px;
  letter-spacing: .2em;
  text-transform: uppercase;
  color: var(--muted);
  margin-bottom: 16px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.section-label::after {
  content: '';
  flex: 1;
  height: 1px;
  background: var(--border);
}

/* ── THEME CARDS ── */
.theme-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
  margin-bottom: 4px;
}
.theme-chip {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 10px 8px;
  text-align: center;
  cursor: pointer;
  transition: all .15s;
  font-family: var(--font);
  font-size: 11px;
  color: var(--muted);
}
.theme-chip:hover { border-color: var(--accent); color: var(--text); }
.theme-chip.active { border-color: var(--accent); background: rgba(255,45,85,.08); color: var(--accent); }

/* ── RESULT CARD ── */
.result-card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 20px;
  font-family: var(--font);
  animation: fadeUp .3s ease;
}
@keyframes fadeUp { from { opacity:0; transform:translateY(8px); } to { opacity:1; transform:translateY(0); } }
.result-header { display:flex; align-items:center; gap:12px; margin-bottom:16px; flex-wrap:wrap; }
.result-badge {
  font-family: var(--mono);
  font-size: 10px;
  letter-spacing: .15em;
  padding: 4px 10px;
  border-radius: 6px;
  font-weight: 500;
}
.result-badge.success { background: rgba(10,255,157,.12); color: var(--accent3); border: 1px solid rgba(10,255,157,.2); }
.result-badge.error { background: rgba(255,45,85,.12); color: var(--accent); border: 1px solid rgba(255,45,85,.2); }
.result-file { font-family: var(--mono); font-size: 10px; color: var(--muted); }
.result-stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 1px;
  background: var(--border);
  border-radius: 10px;
  overflow: hidden;
  margin-bottom: 16px;
}
.stat { background: var(--surface); padding: 12px 8px; text-align: center; }
.stat-val { display:block; font-family: var(--mono); font-size: 20px; font-weight:500; color: var(--text); }
.stat-label { display:block; font-family: var(--mono); font-size: 9px; letter-spacing:.1em; text-transform:uppercase; color: var(--muted); margin-top:2px; }
.result-hook {
  display:flex; align-items:flex-start; gap:10px;
  background: rgba(191,90,242,.08);
  border: 1px solid rgba(191,90,242,.15);
  border-radius: 10px;
  padding: 12px 14px;
  margin-bottom: 14px;
}
.hook-label { font-family:var(--mono); font-size:9px; letter-spacing:.15em; color: var(--accent2); text-transform:uppercase; white-space:nowrap; padding-top:2px; }
.hook-text { font-size:14px; color:var(--text); line-height:1.4; }
.result-scenes { margin-bottom:12px; }
.scenes-label { font-family:var(--mono); font-size:9px; letter-spacing:.15em; color:var(--muted); text-transform:uppercase; margin-bottom:8px; }
.scene-item { display:flex; gap:10px; align-items:flex-start; padding:6px 0; border-bottom:1px solid var(--border); }
.scene-item:last-child { border:none; }
.scene-num { font-family:var(--mono); font-size:10px; color:var(--accent); min-width:16px; padding-top:2px; }
.scene-text { font-size:13px; color:var(--text); line-height:1.4; opacity:.85; }
.result-hashtags { font-family:var(--mono); font-size:11px; color:var(--accent2); letter-spacing:.04em; }

/* ── QUEUE ── */
.queue-list { display:flex; flex-direction:column; gap:4px; }
.queue-row {
  display:grid;
  grid-template-columns: 28px 80px 1fr auto;
  align-items:center;
  gap:12px;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 14px;
  font-family: var(--mono);
  font-size: 11px;
}
.queue-row.status-running { border-color: rgba(191,90,242,.25); }
.queue-row.status-done { border-color: rgba(10,255,157,.15); }
.queue-row.status-error { border-color: rgba(255,45,85,.2); }
.q-icon { font-size:14px; text-align:center; }
.status-running .q-icon { color:var(--accent2); animation: spin 2s linear infinite; }
.status-done .q-icon { color:var(--accent3); }
.status-error .q-icon { color:var(--accent); }
.status-pending .q-icon { color:var(--muted); }
@keyframes spin { to { transform: rotate(360deg); } }
.q-id { color:var(--accent); font-size:10px; }
.q-theme { color:var(--text); }
.q-msg { color:var(--muted); font-size:10px; text-align:right; }
.qpbar { grid-column:1/-1; height:2px; background:var(--border); border-radius:99px; }
.qpbar-fill { height:100%; background:linear-gradient(90deg,var(--accent),var(--accent2)); border-radius:99px; transition:width .5s ease; }
.queue-empty { font-family:var(--mono); font-size:11px; color:var(--muted); letter-spacing:.08em; padding:24px; text-align:center; text-transform:uppercase; border:1px dashed var(--border); border-radius:var(--radius); }

/* ── VIDEO GRID ── */
.video-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(200px,1fr)); gap:12px; }
.video-card { background:var(--card); border:1px solid var(--border); border-radius:var(--radius); overflow:hidden; transition:all .2s; cursor:pointer; }
.video-card:hover { border-color:var(--accent); transform:translateY(-2px); }
.video-thumb { background:linear-gradient(135deg,#1a0a1e,#0a0a1a); height:120px; display:flex; align-items:center; justify-content:center; font-size:28px; color:var(--border); }
.video-card:hover .video-thumb { color:var(--accent); }
.video-info { padding:10px 12px; }
.video-name { font-family:var(--mono); font-size:10px; color:var(--text); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; margin-bottom:4px; }
.video-meta { font-family:var(--mono); font-size:9px; color:var(--muted); }

/* ── CONFIG PANEL ── */
.config-panel {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 24px;
}
.config-divider { height:1px; background:var(--border); margin:20px 0; }

/* ── GENERATE BTN ── */
.gen-btn-wrap { margin-top: 4px; }
.gen-btn-wrap button {
  width: 100% !important;
  height: 52px !important;
  font-size: 13px !important;
  letter-spacing: .2em !important;
  position: relative;
  overflow: hidden;
}

/* ── INSTALL GUIDE ── */
.install-guide { max-width: 720px; margin: 0 auto; }
.install-guide h2 { font-family:var(--font); font-size:22px; font-weight:700; color:var(--text); margin:32px 0 12px; padding-bottom:8px; border-bottom:1px solid var(--border); }
.install-guide h3 { font-family:var(--mono); font-size:12px; letter-spacing:.1em; color:var(--accent2); text-transform:uppercase; margin:20px 0 8px; }
.install-guide p { color:var(--muted); font-size:14px; line-height:1.7; margin:8px 0; }
.install-guide code { background:var(--surface); border:1px solid var(--border); border-radius:6px; padding:2px 8px; font-family:var(--mono); font-size:12px; color:var(--accent3); }
.install-guide pre { background:var(--surface); border:1px solid var(--border); border-radius:var(--radius); padding:16px 20px; font-family:var(--mono); font-size:12px; color:var(--text); overflow-x:auto; margin:12px 0; line-height:1.6; }
.roadmap-item { display:flex; gap:12px; align-items:flex-start; padding:10px 0; border-bottom:1px solid var(--border); }
.roadmap-item:last-child { border:none; }
.roadmap-dot { width:8px; height:8px; border-radius:50%; background:var(--border); margin-top:6px; flex-shrink:0; }
.roadmap-item.soon .roadmap-dot { background:var(--accent); box-shadow:0 0 8px var(--accent); }
.roadmap-item .roadmap-text { font-size:14px; color:var(--muted); }
.roadmap-item.soon .roadmap-text { color:var(--text); }
"""

# ─── Interface ────────────────────────────────────────────────────────────────

theme_choices_ui = THEME_CHOICES
voice_choices_ui = list(VOICE_MAP.keys())
lang_choices_ui  = list(LANG_MAP.keys())
style_choices_ui = ["tiktok", "neon", "classic", "minimal"]
dur_choices_ui   = [15, 30, 60]

with gr.Blocks(title="TikTok Creator Studio") as app:

    gr.HTML("""
    <div class="studio-header">
      <div class="studio-logo">▲ Creator Studio</div>
      <div class="studio-title">TikTok <span>AI</span> Generator</div>
      <div class="studio-sub">Multi-agent · Autonomous · 2026</div>
      <div class="studio-pills">
        <span class="pill hot">6 Agentes IA</span>
        <span class="pill green">100% Gratuito</span>
        <span class="pill">Imagens IA</span>
        <span class="pill">TTS Neural</span>
        <span class="pill">9:16 Vertical</span>
        <span class="pill">Legendas TikTok</span>
      </div>
    </div>
    """)

    with gr.Tabs():

        # ── TAB 1: STUDIO ──────────────────────────────────────────────────
        with gr.Tab("STUDIO"):
            with gr.Row(equal_height=False):

                # Coluna esquerda — configurações
                with gr.Column(scale=5):
                    gr.HTML('<div class="section-label">Tema & Conteúdo</div>')

                    theme_dd = gr.Dropdown(
                        choices=theme_choices_ui,
                        value=theme_choices_ui[1],
                        label="Tema",
                        container=True,
                    )
                    topic_tb = gr.Textbox(
                        label="Tópico específico",
                        placeholder="Ex: factos sobre buracos negros  (deixa vazio para IA decidir)",
                        lines=2,
                        max_lines=3,
                    )

                    gr.HTML('<div class="section-label" style="margin-top:20px">Formato</div>')

                    with gr.Row():
                        duration_sl = gr.Radio(
                            choices=dur_choices_ui,
                            value=30,
                            label="Duração (segundos)",
                        )
                        style_dd = gr.Dropdown(
                            choices=style_choices_ui,
                            value="tiktok",
                            label="Estilo legendas",
                        )

                    gr.HTML('<div class="section-label" style="margin-top:20px">Voz & Idioma</div>')

                    with gr.Row():
                        voice_dd = gr.Dropdown(
                            choices=voice_choices_ui,
                            value=voice_choices_ui[0],
                            label="Voz",
                        )
                        lang_dd = gr.Dropdown(
                            choices=lang_choices_ui,
                            value=lang_choices_ui[0],
                            label="Idioma",
                        )

                    gr.HTML('<div class="section-label" style="margin-top:20px">Áudio</div>')

                    with gr.Row():
                        music_cb = gr.Checkbox(value=True, label="Música de fundo")
                        music_vol = gr.Slider(
                            minimum=0.05, maximum=0.50,
                            value=0.15, step=0.05,
                            label="Volume da música",
                        )

                    gr.HTML('<div style="margin-top:24px"></div>')
                    gen_btn = gr.Button("▶  GERAR VÍDEO", variant="primary", size="lg")

                # Coluna direita — output
                with gr.Column(scale=7):
                    gr.HTML('<div class="section-label">Preview</div>')
                    video_out = gr.Video(
                        label="",
                        show_label=False,
                        height=500,
                    )
                    gr.HTML('<div class="section-label" style="margin-top:16px">Resultado</div>')
                    info_out = gr.HTML(
                        '<div class="queue-empty">O teu vídeo aparece aqui após geração.</div>'
                    )

            gen_btn.click(
                fn=generate_single_video,
                inputs=[theme_dd, duration_sl, voice_dd, lang_dd,
                        style_dd, topic_tb, music_cb, music_vol],
                outputs=[video_out, info_out],
                show_progress=True,
            )

        # ── TAB 2: BATCH ───────────────────────────────────────────────────
        with gr.Tab("BATCH"):
            gr.HTML('<div class="section-label">Geração em Lote</div>')

            with gr.Row():
                with gr.Column(scale=5):
                    b_theme = gr.Dropdown(choices=theme_choices_ui, value=theme_choices_ui[1], label="Tema")
                    b_topic = gr.Textbox(label="Tópico", placeholder="Vazio = IA decide", lines=1)

                    with gr.Row():
                        b_duration = gr.Radio(choices=dur_choices_ui, value=30, label="Duração")
                        b_style = gr.Dropdown(choices=style_choices_ui, value="tiktok", label="Legendas")

                    with gr.Row():
                        b_voice = gr.Dropdown(choices=voice_choices_ui, value=voice_choices_ui[0], label="Voz")
                        b_lang  = gr.Dropdown(choices=lang_choices_ui, value=lang_choices_ui[0], label="Idioma")

                    with gr.Row():
                        b_music = gr.Checkbox(value=True, label="Música")
                        b_vol   = gr.Slider(0.05, 0.5, value=0.15, step=0.05, label="Volume")

                    b_num = gr.Slider(minimum=1, maximum=10, value=3, step=1, label="Número de vídeos")
                    b_add_btn = gr.Button("➕  ADICIONAR À FILA", variant="primary")
                    b_result  = gr.HTML('<div class="queue-empty">Configura e adiciona à fila.</div>')

                with gr.Column(scale=7):
                    gr.HTML('<div class="section-label">Estado da Fila</div>')
                    queue_status = gr.HTML('<div class="queue-empty">Fila vazia.</div>')
                    refresh_btn  = gr.Button("↻  ATUALIZAR", variant="secondary", size="sm")

            b_add_btn.click(
                fn=add_to_batch_queue,
                inputs=[b_theme, b_duration, b_voice, b_lang,
                        b_style, b_topic, b_music, b_vol, b_num],
                outputs=[b_result],
            )
            refresh_btn.click(fn=get_queue_status, outputs=[queue_status])

        # ── TAB 3: BIBLIOTECA ──────────────────────────────────────────────
        with gr.Tab("BIBLIOTECA"):
            with gr.Row():
                gr.HTML('<div class="section-label">Vídeos Gerados</div>')
                lib_refresh = gr.Button("↻  ATUALIZAR", variant="secondary", size="sm")
            lib_out = gr.HTML('<div class="queue-empty">Clica em Atualizar para carregar.</div>')
            lib_refresh.click(fn=list_generated_videos, outputs=[lib_out])

        # ── TAB 4: SETUP ───────────────────────────────────────────────────
        with gr.Tab("SETUP"):
            gr.HTML("""
            <div class="install-guide">

              <h2>Instalação Rápida</h2>

              <h3>1 — Requisitos</h3>
              <pre>python --version   # 3.10+
ffmpeg -version    # obrigatório</pre>
              <p>FFmpeg: <code>sudo apt install ffmpeg</code> · <code>brew install ffmpeg</code> · <a href="https://ffmpeg.org/download.html" style="color:#bf5af2">ffmpeg.org</a></p>

              <h3>2 — Dependências Python</h3>
              <pre>pip install -r requirements.txt</pre>

              <h3>3 — LLM (escolhe um)</h3>
              <pre># Opção A: Ollama (100% local, recomendado)
ollama pull llama3 && ollama serve

# Opção B: Groq (grátis, rápido — groq.com)
export GROQ_API_KEY="gsk_..."</pre>

              <h3>4 — Imagens</h3>
              <p>Pollinations.ai funciona automaticamente sem configuração.</p>
              <pre># Stable Diffusion local (opcional, melhor qualidade)
export SD_USE_LOCAL=true
export SD_API_URL=http://127.0.0.1:7860</pre>

              <h3>5 — Voz</h3>
              <pre>pip install edge-tts   # funciona automaticamente</pre>

              <h3>6 — Música de Fundo</h3>
              <p>Coloca ficheiros <code>.mp3</code> em <code>assets/music/</code></p>
              <p>Fontes livres de direitos: <code>pixabay.com/music</code> · <code>freemusicarchive.org</code></p>

              <h3>7 — Variáveis Railway</h3>
              <pre>GROQ_API_KEY = gsk_...
TTS_ENGINE   = edge-tts
SD_USE_LOCAL = false</pre>

              <h2>Roadmap</h2>
              <div class="roadmap-item soon">
                <div class="roadmap-dot"></div>
                <div class="roadmap-text">Upload automático para TikTok via Creator API</div>
              </div>
              <div class="roadmap-item soon">
                <div class="roadmap-dot"></div>
                <div class="roadmap-text">Sistema de trending topics (Google Trends + Twitter)</div>
              </div>
              <div class="roadmap-item">
                <div class="roadmap-dot"></div>
                <div class="roadmap-text">Personagens consistentes com LoRA / IP-Adapter</div>
              </div>
              <div class="roadmap-item">
                <div class="roadmap-dot"></div>
                <div class="roadmap-text">Scheduler automático — publica em horas de pico</div>
              </div>
              <div class="roadmap-item">
                <div class="roadmap-dot"></div>
                <div class="roadmap-text">Dashboard analytics de performance por vídeo</div>
              </div>
              <div class="roadmap-item">
                <div class="roadmap-dot"></div>
                <div class="roadmap-text">Export multi-plataforma: Reels, Shorts, Snapchat</div>
              </div>
            </div>
            """)

    gr.HTML("""
    <div style="border-top:1px solid #252535; padding:16px 24px; display:flex; justify-content:space-between; align-items:center;">
      <span style="font-family:'JetBrains Mono',monospace; font-size:10px; color:#444; letter-spacing:.1em; text-transform:uppercase;">TikTok Creator Studio · Open Source · 2026</span>
      <span style="font-family:'JetBrains Mono',monospace; font-size:10px; color:#444; letter-spacing:.1em;">100% Free · No Paid APIs Required</span>
    </div>
    """)


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 7860))
    logger.info(f"Iniciando na porta {port}...")
    app.launch(
        server_name="0.0.0.0",
        server_port=port,
        share=False,
        css=CSS,
    )
