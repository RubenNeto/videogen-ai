"""
TikTok Creator Studio — UI 2026 Complete Rebuild
Fixes: asyncio, filesystem, error feedback, diagnostics, UX
"""

import gradio as gr
import logging
import sys
import time
import os
import json
import threading
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from config.settings import THEMES, VIDEO_FORMAT, VIDEOS_DIR, LOGS_DIR
from pipeline import VideoGenerationPipeline, get_system_diagnostics, ensure_dirs
from job_queue.video_queue import VideoQueue, JobStatus

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
logger = logging.getLogger(__name__)

ensure_dirs()

# ── Globals ───────────────────────────────────────────────────────────────────
_pipeline = None
_video_queue = None
_init_lock = threading.Lock()

def get_pipeline():
    global _pipeline, _video_queue
    if _pipeline is None:
        with _init_lock:
            if _pipeline is None:
                _pipeline = VideoGenerationPipeline()
                _video_queue = VideoQueue(_pipeline)
                _video_queue.start(num_workers=1)
    return _pipeline, _video_queue

# ── Maps ──────────────────────────────────────────────────────────────────────
VOICE_MAP = {
    "Raquela · Feminina PT": "pt_female",
    "Duarte · Masculino PT": "pt_male",
    "Jenny · Feminine EN":   "en_female",
    "Guy · Masculine EN":    "en_male",
    "Elvira · Femenina ES":  "es_female",
    "Robótica 🤖":           "robotic",
}
LANG_MAP = {
    "🇵🇹 Português": "pt",
    "🇬🇧 English":   "en",
    "🇪🇸 Español":   "es",
    "🇫🇷 Français":  "fr",
}
THEME_EMOJI_MAP = {f"{v['emoji']} {v['name']}": k for k, v in THEMES.items()}
THEME_CHOICES   = [f"{v['emoji']} {v['name']}" for v in THEMES.values()]
VOICE_CHOICES   = list(VOICE_MAP.keys())
LANG_CHOICES    = list(LANG_MAP.keys())
STYLE_CHOICES   = ["tiktok", "neon", "classic", "minimal"]
DUR_CHOICES     = [15, 30, 60]

STEP_LABELS = [
    ("1", "Script", "📝"),
    ("2", "Cenas",  "🎬"),
    ("3", "Imagens","🎨"),
    ("4", "Voz",    "🔊"),
    ("5", "Legendas","💬"),
    ("6", "Vídeo",  "🎥"),
]

# ── State tracking ─────────────────────────────────────────────────────────────
_current_step = [0]
_current_msg  = [""]

# ── Helpers ────────────────────────────────────────────────────────────────────

def _steps_html(active: int) -> str:
    items = ""
    for num, label, icon in STEP_LABELS:
        n = int(num)
        if n < active:
            cls = "step-done"
            ico = "✓"
        elif n == active:
            cls = "step-active"
            ico = icon
        else:
            cls = "step-pending"
            ico = num
        items += f'<div class="step-item {cls}"><span class="step-ico">{ico}</span><span class="step-lbl">{label}</span></div>'
    return f'<div class="steps-bar">{items}</div>'

def _result_html(result: dict, duration) -> str:
    if not result["success"]:
        err = result.get("error", "Erro desconhecido")
        log = result.get("log_path", "")
        return f"""
<div class="res-card err-card">
  <div class="res-header"><span class="badge badge-err">✗ FALHOU</span></div>
  <div class="err-msg">{err}</div>
  <div class="err-hint">
    💡 Verifica se <code>GROQ_API_KEY</code> está definida no Railway.<br>
    💡 Usa o separador <strong>Diagnóstico</strong> para ver o estado do sistema.<br>
    📋 Log: <code>{log}</code>
  </div>
</div>"""

    script = result.get("script", {})
    hook   = script.get("hook", "—")
    cenas  = script.get("cenas", [])
    tags   = " ".join(script.get("hashtags", []))
    dur    = result.get("duration_real", duration)
    size   = result.get("size_mb", 0)
    elapsed= result.get("elapsed_seconds", 0)
    nc     = result.get("scenes_count", 0)
    ni     = result.get("images_generated", nc)
    na     = result.get("audio_generated", nc)
    fname  = result.get("video_name", "")

    scene_rows = "".join(
        f'<div class="scene-row"><span class="sn">{i+1}</span><span class="st">{c.get("texto","")}</span></div>'
        for i, c in enumerate(cenas[:6])
    )

    return f"""
<div class="res-card ok-card">
  <div class="res-header">
    <span class="badge badge-ok">✓ GERADO</span>
    <span class="res-fname">{fname}</span>
  </div>
  <div class="res-stats">
    <div class="rs"><span class="rv">{dur:.0f}s</span><span class="rl">Duração</span></div>
    <div class="rs"><span class="rv">{nc}</span><span class="rl">Cenas</span></div>
    <div class="rs"><span class="rv">{ni}/{nc}</span><span class="rl">Imagens</span></div>
    <div class="rs"><span class="rv">{na}/{nc}</span><span class="rl">Áudios</span></div>
    <div class="rs"><span class="rv">{size:.1f}MB</span><span class="rl">Tamanho</span></div>
    <div class="rs"><span class="rv">{elapsed:.0f}s</span><span class="rl">Tempo</span></div>
  </div>
  <div class="hook-box"><span class="hook-lbl">HOOK</span><span class="hook-txt">"{hook}"</span></div>
  <div class="scenes-box"><div class="scenes-lbl">SCRIPT</div>{scene_rows}</div>
  <div class="tags-row">{tags}</div>
</div>"""

def _diag_html(d: dict) -> str:
    def ok(v): return f'<span class="dv dv-ok">{"OK" if v else "FALHOU"}</span>'
    def val(v): return f'<span class="dv {"dv-ok" if v and v != "NOT SET" else "dv-err"}">{v}</span>'

    rows = f"""
<div class="diag-grid">
  <div class="diag-row"><span class="dk">FFmpeg</span>{ok(d.get("ffmpeg"))}</div>
  <div class="diag-row"><span class="dk">FFprobe</span>{ok(d.get("ffprobe"))}</div>
  <div class="diag-row"><span class="dk">edge-tts</span>{ok(d.get("edge_tts"))}</div>
  <div class="diag-row"><span class="dk">gTTS</span>{ok(d.get("gtts"))}</div>
  <div class="diag-row"><span class="dk">Pillow</span>{ok(d.get("pillow"))}</div>
  <div class="diag-row"><span class="dk">Pollinations</span>{ok(d.get("pollinations_reachable"))}</div>
  <div class="diag-row"><span class="dk">Disco escrita</span>{ok(d.get("disk_writable"))}</div>
  <div class="diag-row"><span class="dk">GROQ_API_KEY</span>{val(d["env_vars"].get("GROQ_API_KEY","NOT SET"))}</div>
  <div class="diag-row"><span class="dk">TTS_ENGINE</span>{val(d["env_vars"].get("TTS_ENGINE","not set"))}</div>
  <div class="diag-row"><span class="dk">PORT</span>{val(d["env_vars"].get("PORT","not set"))}</div>
</div>
<div class="diag-ts">Verificado: {d.get("timestamp","")}</div>"""

    if not d.get("groq_key_set"):
        rows += '<div class="diag-warn">⚠️ GROQ_API_KEY não definida — scripts em modo fallback (qualidade reduzida). Define em Railway → Variables.</div>'
    if not d.get("ffmpeg"):
        rows += '<div class="diag-warn">⚠️ FFmpeg não encontrado — geração de vídeo vai falhar.</div>'
    if not d.get("pollinations_reachable"):
        rows += '<div class="diag-warn">⚠️ Pollinations.ai inacessível — imagens em placeholder.</div>'
    if not d.get("edge_tts") and not d.get("gtts"):
        rows += '<div class="diag-warn">⚠️ Nenhum engine TTS disponível — áudio silencioso.</div>'

    return f'<div class="diag-card">{rows}</div>'

def _queue_html() -> str:
    if _video_queue is None:
        return '<div class="empty-state">Fila não iniciada. Gera um vídeo primeiro.</div>'
    jobs = _video_queue.get_all_jobs()
    if not jobs:
        return '<div class="empty-state">Fila vazia.</div>'

    status_cls = {"pending":"sq-pending","running":"sq-running","completed":"sq-done","failed":"sq-err","cancelled":"sq-cancel"}
    status_ico = {"pending":"⏳","running":"▶","completed":"✓","failed":"✗","cancelled":"○"}

    rows = ""
    for job in sorted(jobs, key=lambda x: x.get("created_at",""), reverse=True)[:15]:
        s   = job["status"]
        cls = status_cls.get(s,"")
        ico = status_ico.get(s,"?")
        jid = job["job_id"]
        cfg = job.get("config", {})
        theme = cfg.get("theme","?")
        dur   = cfg.get("duration","?")
        msg   = job.get("progress_message","")
        step  = job.get("progress_step",0)
        total = job.get("progress_total",6)
        pct   = int(step/max(total,1)*100)
        pb    = f'<div class="qpb"><div class="qpb-f" style="width:{pct}%"></div></div>' if s=="running" else ""
        rows += f'<div class="qrow {cls}"><span class="qi">{ico}</span><code class="qid">{jid}</code><span class="qth">{theme}·{dur}s</span><span class="qmsg">{msg}</span>{pb}</div>'

    return f'<div class="queue-list">{rows}</div>'

def _library_html() -> str:
    vids = sorted(VIDEOS_DIR.glob(f"*.{VIDEO_FORMAT}"), key=lambda x: x.stat().st_mtime, reverse=True)
    if not vids:
        return '<div class="empty-state">Nenhum vídeo gerado ainda.</div>'
    cards = ""
    for v in vids[:30]:
        sz  = v.stat().st_size / 1024 / 1024
        ts  = time.strftime("%d %b %H:%M", time.localtime(v.stat().st_mtime))
        nm  = v.stem[:30] + "…" if len(v.stem) > 30 else v.stem
        cards += f'<div class="vcard"><div class="vthumb">▶</div><div class="vinfo"><div class="vname" title="{v.name}">{nm}</div><div class="vmeta">{sz:.1f} MB · {ts}</div></div></div>'
    return f'<div class="vgrid">{cards}</div>'

# ── Generate ───────────────────────────────────────────────────────────────────

def generate_video_fn(theme_full, duration, voice_key, lang_key,
                      style, topic, add_music, music_vol,
                      progress=gr.Progress()):

    _current_step[0] = 0
    _current_msg[0]  = "A inicializar..."
    progress(0, desc="A inicializar agentes...")

    pipe, _ = get_pipeline()

    def on_progress(step, total, msg, job_id):
        _current_step[0] = step
        _current_msg[0]  = msg
        progress(step / total, desc=msg)

    theme_k = THEME_EMOJI_MAP.get(theme_full, "curiosidades")
    voice_k  = VOICE_MAP.get(voice_key, "pt_female")
    lang_k   = LANG_MAP.get(lang_key, "pt")
    dur_int  = int(duration)

    result = pipe.generate_video(
        theme=theme_k, duration=dur_int,
        voice_type=voice_k, language=lang_k,
        subtitle_style=style,
        topic=topic.strip() if topic and topic.strip() else None,
        add_music=add_music, music_volume=music_vol,
        progress_callback=on_progress,
    )

    progress(1.0, desc="Concluído!")

    video_path = result.get("video_path") if result["success"] else None
    steps      = _steps_html(7 if result["success"] else _current_step[0])
    info       = _result_html(result, dur_int)

    return video_path, steps, info

def run_diagnostics_fn():
    diag = get_system_diagnostics()
    return _diag_html(diag)

def queue_add_fn(theme_full, duration, voice_key, lang_key,
                 style, topic, add_music, music_vol, num_vids):
    _, q = get_pipeline()
    cfg = {
        "theme":          THEME_EMOJI_MAP.get(theme_full, "curiosidades"),
        "duration":       int(duration),
        "voice_type":     VOICE_MAP.get(voice_key, "pt_female"),
        "language":       LANG_MAP.get(lang_key, "pt"),
        "subtitle_style": style,
        "topic":          topic.strip() if topic and topic.strip() else None,
        "add_music":      add_music,
        "music_volume":   music_vol,
    }
    ids = []
    for _ in range(int(num_vids)):
        job = q.add_job(cfg.copy())
        ids.append(job.job_id)
    ids_str = " · ".join(f"<code>{i}</code>" for i in ids)
    return f'<div class="res-card ok-card"><div class="res-header"><span class="badge badge-ok">✓ {num_vids} JOBS CRIADOS</span></div><p style="margin-top:10px;opacity:.6;font-size:13px">{ids_str}</p></div>'

def queue_refresh_fn():
    return _queue_html()

def library_refresh_fn():
    return _library_html()

def read_log_fn(job_id: str) -> str:
    if not job_id or not job_id.strip():
        return "Introduz um Job ID para ver o log."
    log_file = LOGS_DIR / f"{job_id.strip()}_pipeline.log"
    if not log_file.exists():
        return f"Log não encontrado: {log_file}"
    try:
        lines = log_file.read_text(encoding="utf-8").split("\n")
        return "\n".join(lines[-80:])  # últimas 80 linhas
    except Exception as e:
        return f"Erro ao ler log: {e}"

# ── CSS ────────────────────────────────────────────────────────────────────────
CSS = """
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');

:root{
  --bg:#080810;--surf:#0f0f1a;--card:#141420;--border:#1e1e30;
  --acc:#ff2d55;--acc2:#bf5af2;--acc3:#0aff9d;--acc4:#ffd60a;
  --txt:#f0f0ff;--sub:#9090b0;--dim:#444466;
  --r:12px;--font:'Syne',sans-serif;--mono:'JetBrains Mono',monospace;
}

/* Base */
.gradio-container{background:var(--bg)!important;font-family:var(--font)!important;max-width:1320px!important;margin:0 auto!important;padding:0!important}
body,.dark{background:var(--bg)!important}
footer,.svelte-1gfkn6j{display:none!important}

/* Inputs */
label,.label-wrap{color:var(--sub)!important;font-family:var(--mono)!important;font-size:10px!important;letter-spacing:.12em!important;text-transform:uppercase!important}
input,textarea,select,.wrap{background:var(--card)!important;border:1px solid var(--border)!important;border-radius:var(--r)!important;color:var(--txt)!important;font-family:var(--font)!important}
input:focus,textarea:focus{border-color:var(--acc)!important;box-shadow:0 0 0 2px rgba(255,45,85,.12)!important;outline:none!important}
.block{background:transparent!important;border:none!important;padding:0!important}
ul.options{background:var(--card)!important;border:1px solid var(--border)!important;border-radius:var(--r)!important}
ul.options li{color:var(--txt)!important}
ul.options li:hover,ul.options li.selected{background:rgba(255,45,85,.1)!important;color:var(--acc)!important}
input[type=range]{accent-color:var(--acc)!important}
input[type=checkbox]{accent-color:var(--acc)!important}
.wrap.svelte-a4qna4{background:transparent!important;border:none!important}

/* Radio */
.wrap.svelte-1oiin9d,.svelte-1oiin9d{background:transparent!important}
input[type=radio]{accent-color:var(--acc)!important}
.radio-group .wrap{display:flex!important;gap:8px!important;flex-wrap:wrap!important}

/* Tabs */
.tabs{border:none!important;background:transparent!important}
.tab-nav{background:var(--surf)!important;border-bottom:1px solid var(--border)!important;padding:0 28px!important;border-radius:0!important;gap:0!important}
.tab-nav button{background:transparent!important;border:none!important;border-bottom:2px solid transparent!important;color:var(--sub)!important;font-family:var(--mono)!important;font-size:10px!important;letter-spacing:.15em!important;padding:18px 22px!important;border-radius:0!important;transition:all .2s!important;text-transform:uppercase!important}
.tab-nav button.selected{color:var(--acc)!important;border-bottom-color:var(--acc)!important}
.tab-nav button:hover{color:var(--txt)!important}
.tabitem{background:transparent!important;border:none!important;padding:32px 28px!important}

/* Buttons */
button.primary,.primary{background:linear-gradient(135deg,var(--acc),var(--acc2))!important;border:none!important;border-radius:var(--r)!important;color:#fff!important;font-family:var(--mono)!important;font-size:11px!important;font-weight:600!important;letter-spacing:.15em!important;text-transform:uppercase!important;padding:14px 28px!important;transition:all .2s!important;box-shadow:0 4px 24px rgba(255,45,85,.2)!important}
button.primary:hover{transform:translateY(-2px)!important;box-shadow:0 8px 32px rgba(255,45,85,.35)!important}
button.secondary{background:var(--card)!important;border:1px solid var(--border)!important;border-radius:var(--r)!important;color:var(--sub)!important;font-family:var(--mono)!important;font-size:10px!important;letter-spacing:.12em!important;text-transform:uppercase!important;transition:all .2s!important}
button.secondary:hover{border-color:var(--acc)!important;color:var(--acc)!important}

/* Progress */
.progress-bar{background:var(--border)!important;border-radius:99px!important}
.progress-bar>div{background:linear-gradient(90deg,var(--acc),var(--acc2))!important;border-radius:99px!important}

/* Video */
video{border-radius:var(--r)!important}
.video-container{background:var(--card)!important;border:1px solid var(--border)!important;border-radius:var(--r)!important}

/* ── HEADER ── */
.hdr{background:linear-gradient(180deg,rgba(255,45,85,.05) 0%,transparent 100%);border-bottom:1px solid var(--border);padding:36px 28px 28px;text-align:center}
.hdr-eyebrow{font-family:var(--mono);font-size:10px;letter-spacing:.35em;color:var(--dim);text-transform:uppercase;margin-bottom:14px}
.hdr-title{font-family:var(--font);font-size:clamp(2.2rem,5vw,4rem);font-weight:800;color:var(--txt);letter-spacing:-.03em;line-height:1;margin-bottom:10px}
.hdr-title em{color:var(--acc);font-style:normal}
.hdr-sub{font-family:var(--mono);font-size:11px;color:var(--sub);letter-spacing:.1em}
.hdr-pills{display:flex;gap:8px;justify-content:center;flex-wrap:wrap;margin-top:22px}
.pill{background:var(--card);border:1px solid var(--border);border-radius:99px;padding:5px 14px;font-family:var(--mono);font-size:9px;color:var(--sub);letter-spacing:.1em;text-transform:uppercase}
.pill.p-red{border-color:rgba(255,45,85,.35);color:var(--acc)}
.pill.p-grn{border-color:rgba(10,255,157,.25);color:var(--acc3)}
.pill.p-pur{border-color:rgba(191,90,242,.25);color:var(--acc2)}

/* ── SECTION LABEL ── */
.slabel{font-family:var(--mono);font-size:9px;letter-spacing:.22em;text-transform:uppercase;color:var(--dim);display:flex;align-items:center;gap:10px;margin-bottom:14px}
.slabel::after{content:'';flex:1;height:1px;background:var(--border)}

/* ── STEPS BAR ── */
.steps-bar{display:flex;gap:4px;align-items:center;margin-bottom:20px;flex-wrap:wrap}
.step-item{display:flex;align-items:center;gap:6px;padding:6px 12px;border-radius:8px;font-family:var(--mono);font-size:10px;border:1px solid var(--border);background:var(--card);color:var(--dim);letter-spacing:.06em;text-transform:uppercase;transition:all .3s}
.step-done{background:rgba(10,255,157,.06)!important;border-color:rgba(10,255,157,.2)!important;color:var(--acc3)!important}
.step-active{background:rgba(255,45,85,.08)!important;border-color:rgba(255,45,85,.3)!important;color:var(--acc)!important;animation:pulse 1.5s ease-in-out infinite}
@keyframes pulse{0%,100%{box-shadow:0 0 0 0 rgba(255,45,85,.3)}50%{box-shadow:0 0 0 6px rgba(255,45,85,0)}}
.step-ico{font-size:12px}
.step-lbl{font-size:9px}

/* ── CONFIG PANEL ── */
.cpanel{background:var(--card);border:1px solid var(--border);border-radius:var(--r);padding:24px 22px}
.cdivider{height:1px;background:var(--border);margin:18px 0}

/* ── RESULT CARD ── */
.res-card{background:var(--card);border:1px solid var(--border);border-radius:var(--r);padding:20px;animation:fadeUp .35s ease;font-family:var(--font)}
.ok-card{border-color:rgba(10,255,157,.15)}
.err-card{border-color:rgba(255,45,85,.25)}
@keyframes fadeUp{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}
.res-header{display:flex;align-items:center;gap:12px;margin-bottom:16px;flex-wrap:wrap}
.badge{font-family:var(--mono);font-size:9px;letter-spacing:.18em;padding:4px 10px;border-radius:6px;font-weight:600;text-transform:uppercase}
.badge-ok{background:rgba(10,255,157,.1);color:var(--acc3);border:1px solid rgba(10,255,157,.2)}
.badge-err{background:rgba(255,45,85,.1);color:var(--acc);border:1px solid rgba(255,45,85,.2)}
.res-fname{font-family:var(--mono);font-size:10px;color:var(--dim)}
.res-stats{display:grid;grid-template-columns:repeat(6,1fr);gap:1px;background:var(--border);border-radius:10px;overflow:hidden;margin-bottom:16px}
.rs{background:var(--surf);padding:12px 6px;text-align:center}
.rv{display:block;font-family:var(--mono);font-size:18px;font-weight:600;color:var(--txt)}
.rl{display:block;font-family:var(--mono);font-size:8px;letter-spacing:.1em;text-transform:uppercase;color:var(--sub);margin-top:2px}
.hook-box{display:flex;align-items:flex-start;gap:10px;background:rgba(191,90,242,.07);border:1px solid rgba(191,90,242,.15);border-radius:10px;padding:12px 14px;margin-bottom:14px}
.hook-lbl{font-family:var(--mono);font-size:8px;letter-spacing:.15em;color:var(--acc2);text-transform:uppercase;white-space:nowrap;padding-top:3px}
.hook-txt{font-size:14px;color:var(--txt);line-height:1.5}
.scenes-box{margin-bottom:12px}
.scenes-lbl{font-family:var(--mono);font-size:8px;letter-spacing:.15em;color:var(--sub);text-transform:uppercase;margin-bottom:8px}
.scene-row{display:flex;gap:10px;align-items:flex-start;padding:7px 0;border-bottom:1px solid var(--border)}
.scene-row:last-child{border:none}
.sn{font-family:var(--mono);font-size:10px;color:var(--acc);min-width:16px;padding-top:2px}
.st{font-size:13px;color:var(--txt);opacity:.8;line-height:1.4}
.tags-row{font-family:var(--mono);font-size:11px;color:var(--acc2);letter-spacing:.04em}
.err-msg{font-family:var(--mono);font-size:12px;color:var(--acc);background:rgba(255,45,85,.06);border-radius:8px;padding:12px 14px;margin:12px 0;word-break:break-all}
.err-hint{font-size:13px;color:var(--sub);line-height:1.8}
.err-hint code{background:var(--surf);padding:2px 7px;border-radius:5px;font-family:var(--mono);font-size:11px;color:var(--acc3)}
.err-hint strong{color:var(--txt)}

/* ── QUEUE ── */
.queue-list{display:flex;flex-direction:column;gap:4px}
.qrow{display:grid;grid-template-columns:24px 72px 1fr auto;gap:10px;align-items:center;background:var(--card);border:1px solid var(--border);border-radius:8px;padding:10px 14px;font-family:var(--mono);font-size:11px}
.sq-running{border-color:rgba(191,90,242,.3)!important}
.sq-done{border-color:rgba(10,255,157,.15)!important}
.sq-err{border-color:rgba(255,45,85,.2)!important}
.qi{font-size:13px;text-align:center}
.sq-running .qi{color:var(--acc2)}
.sq-done .qi{color:var(--acc3)}
.sq-err .qi{color:var(--acc)}
.sq-pending .qi{color:var(--dim)}
.qid{font-size:10px;color:var(--acc)}
.qth{color:var(--txt);font-size:10px}
.qmsg{color:var(--sub);font-size:10px;text-align:right}
.qpb{grid-column:1/-1;height:2px;background:var(--border);border-radius:99px}
.qpb-f{height:100%;background:linear-gradient(90deg,var(--acc),var(--acc2));border-radius:99px;transition:width .6s ease}
.empty-state{font-family:var(--mono);font-size:10px;color:var(--dim);letter-spacing:.1em;text-transform:uppercase;padding:28px;text-align:center;border:1px dashed var(--border);border-radius:var(--r)}

/* ── LIBRARY ── */
.vgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:12px}
.vcard{background:var(--card);border:1px solid var(--border);border-radius:var(--r);overflow:hidden;cursor:pointer;transition:all .2s}
.vcard:hover{border-color:var(--acc);transform:translateY(-2px)}
.vthumb{background:linear-gradient(135deg,#160820,#080815);height:110px;display:flex;align-items:center;justify-content:center;font-size:26px;color:var(--border)}
.vcard:hover .vthumb{color:var(--acc)}
.vinfo{padding:10px 12px}
.vname{font-family:var(--mono);font-size:9px;color:var(--txt);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-bottom:4px}
.vmeta{font-family:var(--mono);font-size:9px;color:var(--sub)}

/* ── DIAGNOSTICS ── */
.diag-card{background:var(--card);border:1px solid var(--border);border-radius:var(--r);padding:22px}
.diag-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:6px;margin-bottom:16px}
.diag-row{display:flex;justify-content:space-between;align-items:center;background:var(--surf);border-radius:8px;padding:9px 14px;font-family:var(--mono);font-size:10px}
.dk{color:var(--sub)}
.dv{padding:3px 8px;border-radius:5px;font-weight:600;font-size:9px;letter-spacing:.1em}
.dv-ok{background:rgba(10,255,157,.1);color:var(--acc3);border:1px solid rgba(10,255,157,.2)}
.dv-err{background:rgba(255,45,85,.1);color:var(--acc);border:1px solid rgba(255,45,85,.2)}
.diag-warn{background:rgba(255,214,10,.06);border:1px solid rgba(255,214,10,.2);border-radius:8px;padding:10px 14px;font-family:var(--mono);font-size:11px;color:var(--acc4);margin-top:8px;line-height:1.6}
.diag-ts{font-family:var(--mono);font-size:9px;color:var(--dim);margin-top:8px}

/* ── LOG VIEWER ── */
.log-out textarea{font-family:var(--mono)!important;font-size:10px!important;color:var(--acc3)!important;background:var(--surf)!important;line-height:1.5!important}

/* ── SETUP ── */
.setup-wrap{max-width:740px;margin:0 auto}
.setup-wrap h2{font-family:var(--font);font-size:20px;font-weight:700;color:var(--txt);margin:32px 0 10px;padding-bottom:8px;border-bottom:1px solid var(--border)}
.setup-wrap h3{font-family:var(--mono);font-size:10px;letter-spacing:.15em;color:var(--acc2);text-transform:uppercase;margin:18px 0 8px}
.setup-wrap p{color:var(--sub);font-size:14px;line-height:1.7}
.setup-wrap code{background:var(--surf);border:1px solid var(--border);border-radius:5px;padding:2px 7px;font-family:var(--mono);font-size:11px;color:var(--acc3)}
.setup-wrap pre{background:var(--surf);border:1px solid var(--border);border-radius:var(--r);padding:16px 18px;font-family:var(--mono);font-size:11px;color:var(--txt);overflow-x:auto;margin:10px 0;line-height:1.65}
.rmap{border:1px solid var(--border);border-radius:var(--r);overflow:hidden;margin-top:8px}
.ritem{display:flex;gap:14px;align-items:flex-start;padding:11px 16px;border-bottom:1px solid var(--border)}
.ritem:last-child{border:none}
.rdot{width:7px;height:7px;border-radius:50%;background:var(--border);margin-top:7px;flex-shrink:0}
.ritem.hot .rdot{background:var(--acc);box-shadow:0 0 8px var(--acc)}
.ritem.hot .rtxt{color:var(--txt)}
.rtxt{font-size:13px;color:var(--sub)}

/* ── FOOTER ── */
.ftr{border-top:1px solid var(--border);padding:16px 28px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px}
.ftr span{font-family:var(--mono);font-size:9px;color:var(--dim);letter-spacing:.1em;text-transform:uppercase}
"""

# ── App ────────────────────────────────────────────────────────────────────────
with gr.Blocks(title="TikTok Creator Studio") as app:

    gr.HTML("""
    <div class="hdr">
      <div class="hdr-eyebrow">▲ Creator Studio · Railway Deploy</div>
      <div class="hdr-title">TikTok <em>AI</em> Generator</div>
      <div class="hdr-sub">Pipeline Multi-Agente · Geração Autónoma · 2026</div>
      <div class="hdr-pills">
        <span class="pill p-red">6 Agentes IA</span>
        <span class="pill p-grn">100% Gratuito</span>
        <span class="pill p-pur">Imagens IA</span>
        <span class="pill">TTS Neural</span>
        <span class="pill">9:16 Vertical</span>
        <span class="pill">Legendas TikTok</span>
        <span class="pill">Batch Queue</span>
      </div>
    </div>
    """)

    with gr.Tabs():

        # ══ STUDIO ═══════════════════════════════════════════════════════════
        with gr.Tab("STUDIO"):
            with gr.Row(equal_height=False):

                # ─ Esquerda: configurações ───────────────────────────────────
                with gr.Column(scale=4, min_width=300):
                    gr.HTML('<div class="slabel">Conteúdo</div>')

                    theme_dd = gr.Dropdown(
                        choices=THEME_CHOICES, value=THEME_CHOICES[1],
                        label="Tema", container=True
                    )
                    topic_tb = gr.Textbox(
                        label="Tópico específico",
                        placeholder="Ex: factos sobre buracos negros  (vazio = IA decide)",
                        lines=2, max_lines=4
                    )

                    gr.HTML('<div class="slabel" style="margin-top:18px">Formato</div>')
                    with gr.Row():
                        dur_radio = gr.Radio(
                            choices=DUR_CHOICES, value=30,
                            label="Duração (s)"
                        )
                        style_dd = gr.Dropdown(
                            choices=STYLE_CHOICES, value="tiktok",
                            label="Legendas"
                        )

                    gr.HTML('<div class="slabel" style="margin-top:18px">Voz & Idioma</div>')
                    with gr.Row():
                        voice_dd = gr.Dropdown(
                            choices=VOICE_CHOICES, value=VOICE_CHOICES[0],
                            label="Voz"
                        )
                        lang_dd = gr.Dropdown(
                            choices=LANG_CHOICES, value=LANG_CHOICES[0],
                            label="Idioma"
                        )

                    gr.HTML('<div class="slabel" style="margin-top:18px">Áudio</div>')
                    with gr.Row():
                        music_cb  = gr.Checkbox(value=True, label="Música de fundo")
                        music_vol = gr.Slider(0.05, 0.5, value=0.15, step=0.05, label="Volume")

                    gr.HTML('<div style="margin-top:22px"></div>')
                    gen_btn = gr.Button("▶  GERAR VÍDEO", variant="primary", size="lg")

                # ─ Direita: output ──────────────────────────────────────────
                with gr.Column(scale=6):
                    gr.HTML('<div class="slabel">Pipeline</div>')
                    steps_html = gr.HTML(_steps_html(0))

                    gr.HTML('<div class="slabel" style="margin-top:4px">Preview</div>')
                    video_out = gr.Video(label="", show_label=False, height=460)

                    gr.HTML('<div class="slabel" style="margin-top:12px">Resultado</div>')
                    info_html = gr.HTML('<div class="empty-state">O teu vídeo aparece aqui após geração.</div>')

            gen_btn.click(
                fn=generate_video_fn,
                inputs=[theme_dd, dur_radio, voice_dd, lang_dd,
                        style_dd, topic_tb, music_cb, music_vol],
                outputs=[video_out, steps_html, info_html],
                show_progress=True,
            )

        # ══ BATCH ════════════════════════════════════════════════════════════
        with gr.Tab("BATCH"):
            with gr.Row():
                with gr.Column(scale=4):
                    gr.HTML('<div class="slabel">Configuração</div>')
                    b_theme = gr.Dropdown(choices=THEME_CHOICES, value=THEME_CHOICES[1], label="Tema")
                    b_topic = gr.Textbox(label="Tópico", placeholder="Vazio = IA decide", lines=1)
                    with gr.Row():
                        b_dur   = gr.Radio(choices=DUR_CHOICES, value=30, label="Duração")
                        b_style = gr.Dropdown(choices=STYLE_CHOICES, value="tiktok", label="Legendas")
                    with gr.Row():
                        b_voice = gr.Dropdown(choices=VOICE_CHOICES, value=VOICE_CHOICES[0], label="Voz")
                        b_lang  = gr.Dropdown(choices=LANG_CHOICES, value=LANG_CHOICES[0], label="Idioma")
                    with gr.Row():
                        b_music = gr.Checkbox(value=True, label="Música")
                        b_vol   = gr.Slider(0.05, 0.5, value=0.15, step=0.05, label="Volume")
                    b_num     = gr.Slider(minimum=1, maximum=10, value=3, step=1, label="Número de vídeos")
                    b_add_btn = gr.Button("➕  ADICIONAR À FILA", variant="primary")
                    b_result  = gr.HTML('<div class="empty-state">Configura e adiciona à fila.</div>')

                with gr.Column(scale=6):
                    gr.HTML('<div class="slabel">Estado da Fila</div>')
                    q_status  = gr.HTML('<div class="empty-state">Fila vazia.</div>')
                    q_refresh = gr.Button("↻  ATUALIZAR", variant="secondary", size="sm")

            b_add_btn.click(
                fn=queue_add_fn,
                inputs=[b_theme, b_dur, b_voice, b_lang, b_style, b_topic, b_music, b_vol, b_num],
                outputs=[b_result]
            )
            q_refresh.click(fn=queue_refresh_fn, outputs=[q_status])

        # ══ BIBLIOTECA ═══════════════════════════════════════════════════════
        with gr.Tab("BIBLIOTECA"):
            with gr.Row():
                gr.HTML('<div class="slabel" style="flex:1">Vídeos Gerados</div>')
                lib_btn = gr.Button("↻  ATUALIZAR", variant="secondary", size="sm")
            lib_out = gr.HTML('<div class="empty-state">Clica em Atualizar.</div>')
            lib_btn.click(fn=library_refresh_fn, outputs=[lib_out])

        # ══ DIAGNÓSTICO ══════════════════════════════════════════════════════
        with gr.Tab("DIAGNÓSTICO"):
            gr.HTML('<div class="slabel">Estado do Sistema</div>')
            gr.HTML('<p style="font-family:var(--mono);font-size:11px;color:var(--sub);margin-bottom:16px">Usa esta página para verificar se todos os componentes estão a funcionar antes de gerar vídeos.</p>')
            diag_btn = gr.Button("🔍  VERIFICAR SISTEMA AGORA", variant="primary")
            diag_out = gr.HTML('<div class="empty-state">Clica em Verificar para analisar o sistema.</div>')
            diag_btn.click(fn=run_diagnostics_fn, outputs=[diag_out])

            gr.HTML('<div class="slabel" style="margin-top:28px">Logs</div>')
            with gr.Row():
                log_id_tb  = gr.Textbox(label="Job ID", placeholder="Ex: a1b2c3d4", scale=3)
                log_btn    = gr.Button("📋  LER LOG", variant="secondary", scale=1)
            log_out = gr.Textbox(
                label="", show_label=False, lines=25,
                interactive=False, elem_classes=["log-out"]
            )
            log_btn.click(fn=read_log_fn, inputs=[log_id_tb], outputs=[log_out])

        # ══ SETUP ════════════════════════════════════════════════════════════
        with gr.Tab("SETUP"):
            gr.HTML("""
            <div class="setup-wrap">
              <h2>Instalação Rápida</h2>

              <h3>1 — Requisitos</h3>
              <pre>python --version   # 3.10+
ffmpeg -version    # obrigatório</pre>
              <p>FFmpeg: <code>sudo apt install ffmpeg</code> · <code>brew install ffmpeg</code></p>

              <h3>2 — Dependências</h3>
              <pre>pip install -r requirements.txt</pre>

              <h3>3 — LLM (escolhe um)</h3>
              <pre># Groq — grátis, rápido (recomendado para Railway)
# Cria conta: console.groq.com
export GROQ_API_KEY="gsk_..."

# Ollama — 100% local
ollama pull llama3 && ollama serve</pre>

              <h3>4 — Imagens</h3>
              <p>Pollinations.ai funciona automaticamente — zero configuração.</p>

              <h3>5 — Voz</h3>
              <pre>pip install edge-tts   # já incluído no requirements.txt</pre>

              <h3>6 — Railway: Variáveis de Ambiente</h3>
              <pre>GROQ_API_KEY = gsk_...        # obrigatório para scripts de qualidade
TTS_ENGINE   = edge-tts       # engine de voz
SD_USE_LOCAL = false          # sem SD local no Railway</pre>

              <h3>7 — Música de Fundo (Opcional)</h3>
              <p>Coloca ficheiros <code>.mp3</code> em <code>assets/music/</code></p>
              <p>Fontes: <code>pixabay.com/music</code> · <code>freemusicarchive.org</code></p>

              <h2>Roadmap</h2>
              <div class="rmap">
                <div class="ritem hot"><div class="rdot"></div><div class="rtxt">Upload automático TikTok via Creator API</div></div>
                <div class="ritem hot"><div class="rdot"></div><div class="rtxt">Trending topics em tempo real (Google Trends)</div></div>
                <div class="ritem"><div class="rdot"></div><div class="rtxt">Personagens consistentes com LoRA / IP-Adapter</div></div>
                <div class="ritem"><div class="rdot"></div><div class="rtxt">Scheduler — publica em horas de pico automaticamente</div></div>
                <div class="ritem"><div class="rdot"></div><div class="rtxt">Analytics de performance por vídeo</div></div>
                <div class="ritem"><div class="rdot"></div><div class="rtxt">Export multi-plataforma: Reels · Shorts · Snapchat</div></div>
              </div>
            </div>
            """)

    gr.HTML("""
    <div class="ftr">
      <span>TikTok Creator Studio · Open Source · 2026</span>
      <span>6-Agent Pipeline · FFmpeg · edge-tts · Pollinations.ai</span>
      <span>100% Free · No Paid APIs Required</span>
    </div>
    """)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    logger.info(f"Starting on port {port}")
    app.launch(
        server_name="0.0.0.0",
        server_port=port,
        share=False,
        css=CSS,
    )
