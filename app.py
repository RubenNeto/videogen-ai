"""
Interface Web com Gradio
TikTok Video Generator - Interface Principal
"""

import gradio as gr
import logging
import sys
import threading
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from config.settings import THEMES, SUBTITLE_STYLES, VIDEO_FORMAT, VIDEOS_DIR
from pipeline import VideoGenerationPipeline
from job_queue.video_queue import VideoQueue, JobStatus

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
logger = logging.getLogger(__name__)

# Inicializa pipeline e fila (lazy para não bloquear startup)
pipeline = None
video_queue = None


def get_pipeline():
    global pipeline, video_queue
    if pipeline is None:
        pipeline = VideoGenerationPipeline()
        video_queue = VideoQueue(pipeline)
        video_queue.start(num_workers=2)
    return pipeline, video_queue


# ─── Funções de Interface ──────────────────────────────────────────────────────

def generate_single_video(
    theme, duration, voice_type, language,
    subtitle_style, topic, add_music, music_volume,
    progress=gr.Progress()
):
    """Gera um único vídeo com barra de progresso."""

    progress(0, desc="Inicializando...")
    pipe, _ = get_pipeline()

    steps_desc = [
        "📝 Gerando script viral...",
        "🎬 Dividindo em cenas...",
        "🎨 Gerando imagens com IA...",
        "🔊 Gerando narração de voz...",
        "💬 Criando legendas...",
        "🎥 Montando vídeo final...",
    ]

    current_step = [0]

    def on_progress(step, total, message, job_id):
        current_step[0] = step
        progress(step / total, desc=message)

    # Mapeamento de opções da UI para valores internos
    theme_map = {v["name"]: k for k, v in THEMES.items()}
    theme_key = theme_map.get(theme, "curiosidades")

    voice_map = {
        "🇵🇹 Feminina (PT)": "pt_female",
        "🇵🇹 Masculina (PT)": "pt_male",
        "🇬🇧 Feminine (EN)": "en_female",
        "🇬🇧 Masculine (EN)": "en_male",
        "🇪🇸 Femenina (ES)": "es_female",
        "🤖 Robótica": "robotic",
    }
    voice_key = voice_map.get(voice_type, "pt_female")

    lang_map = {
        "🇵🇹 Português": "pt",
        "🇬🇧 English": "en",
        "🇪🇸 Español": "es",
        "🇫🇷 Français": "fr",
    }
    lang_key = lang_map.get(language, "pt")

    result = pipe.generate_video(
        theme=theme_key,
        duration=int(duration),
        voice_type=voice_key,
        language=lang_key,
        subtitle_style=subtitle_style.lower(),
        topic=topic if topic.strip() else None,
        add_music=add_music,
        music_volume=music_volume,
        progress_callback=on_progress
    )

    progress(1.0, desc="✅ Concluído!")

    if result["success"]:
        video_path = result["video_path"]
        script = result.get("script", {})
        hook = script.get("hook", "")
        cenas = script.get("cenas", [])
        hashtags = " ".join(script.get("hashtags", []))

        info = f"""✅ **Vídeo gerado com sucesso!**

📊 **Estatísticas:**
- Duração: {result.get('duration_real', duration):.1f}s
- Cenas: {result.get('scenes_count', 0)}
- Tamanho: {result.get('size_mb', 0):.1f} MB
- Tempo de geração: {result.get('elapsed_seconds', 0):.1f}s

🎯 **Hook:** {hook}

📝 **Cenas:**
{chr(10).join(f"  {i+1}. {c.get('texto', '')}" for i, c in enumerate(cenas[:5]))}

#️⃣ **Hashtags:** {hashtags}

📁 **Ficheiro:** {result.get('video_name', '')}"""

        return video_path, info

    else:
        return None, f"❌ **Erro:** {result.get('error', 'Erro desconhecido')}\n\n💡 Verifica os logs em: {result.get('log_path', '')}"


def add_to_batch_queue(
    theme, duration, voice_type, language,
    subtitle_style, topic, add_music, music_volume, num_videos
):
    """Adiciona múltiplos vídeos à fila batch."""
    _, q = get_pipeline()

    theme_map = {v["name"]: k for k, v in THEMES.items()}
    theme_key = theme_map.get(theme, "curiosidades")

    voice_map = {
        "🇵🇹 Feminina (PT)": "pt_female",
        "🇵🇹 Masculina (PT)": "pt_male",
        "🇬🇧 Feminine (EN)": "en_female",
        "🇬🇧 Masculine (EN)": "en_male",
        "🤖 Robótica": "robotic",
    }

    lang_map = {
        "🇵🇹 Português": "pt",
        "🇬🇧 English": "en",
        "🇪🇸 Español": "es",
        "🇫🇷 Français": "fr",
    }

    config = {
        "theme": theme_map.get(theme, "curiosidades"),
        "duration": int(duration),
        "voice_type": voice_map.get(voice_type, "pt_female"),
        "language": lang_map.get(language, "pt"),
        "subtitle_style": subtitle_style.lower(),
        "topic": topic if topic.strip() else None,
        "add_music": add_music,
        "music_volume": music_volume,
    }

    job_ids = []
    for i in range(int(num_videos)):
        job = q.add_job(config.copy())
        job_ids.append(job.job_id)

    return f"✅ {num_videos} vídeos adicionados à fila!\nJob IDs: {', '.join(job_ids)}"


def get_queue_status():
    """Obtém status da fila para atualização periódica."""
    if video_queue is None:
        return "⏳ Aguardando inicialização..."

    jobs = video_queue.get_all_jobs()
    if not jobs:
        return "📭 Fila vazia"

    lines = [f"📊 **Status da Fila** ({len(jobs)} jobs totais)\n"]

    status_emoji = {
        "pending": "⏳",
        "running": "🔄",
        "completed": "✅",
        "failed": "❌",
        "cancelled": "🚫"
    }

    # Mostra apenas os últimos 10
    for job in sorted(jobs, key=lambda x: x.get("created_at", ""), reverse=True)[:10]:
        emoji = status_emoji.get(job["status"], "❓")
        jid = job["job_id"]
        theme = job.get("config", {}).get("theme", "?")
        duration = job.get("config", {}).get("duration", "?")
        msg = job.get("progress_message", "")

        if job["status"] == "running":
            step = job.get("progress_step", 0)
            total = job.get("progress_total", 6)
            lines.append(f"{emoji} `{jid}` | {theme} {duration}s | [{step}/{total}] {msg}")
        elif job["status"] == "completed":
            size = job.get("result", {}).get("size_mb", 0) if job.get("result") else 0
            lines.append(f"{emoji} `{jid}` | {theme} {duration}s | {size:.1f} MB")
        else:
            lines.append(f"{emoji} `{jid}` | {theme} {duration}s | {msg}")

    return "\n".join(lines)


def list_generated_videos():
    """Lista vídeos já gerados."""
    videos = sorted(VIDEOS_DIR.glob(f"*.{VIDEO_FORMAT}"), key=lambda x: x.stat().st_mtime, reverse=True)
    if not videos:
        return "📭 Nenhum vídeo gerado ainda"

    lines = [f"🎬 **{len(videos)} vídeos gerados:**\n"]
    for v in videos[:20]:
        size = v.stat().st_size / 1024 / 1024
        mtime = time.strftime("%d/%m %H:%M", time.localtime(v.stat().st_mtime))
        lines.append(f"• `{v.name}` | {size:.1f} MB | {mtime}")

    return "\n".join(lines)


# ─── Interface Gradio ──────────────────────────────────────────────────────────

theme_choices = [v["name"] for v in THEMES.values()]
voice_choices = [
    "🇵🇹 Feminina (PT)", "🇵🇹 Masculina (PT)",
    "🇬🇧 Feminine (EN)", "🇬🇧 Masculine (EN)",
    "🇪🇸 Femenina (ES)", "🤖 Robótica"
]
lang_choices = ["🇵🇹 Português", "🇬🇧 English", "🇪🇸 Español", "🇫🇷 Français"]
style_choices = ["TikTok", "Classic", "Neon", "Minimal"]
duration_choices = ["15", "30", "60"]

css = """
.gradio-container { max-width: 1200px !important; }
.video-output { min-height: 400px; }
footer { display: none !important; }
"""

with gr.Blocks(
    title="🎬 TikTok Video Generator",
    theme=gr.themes.Soft(
        primary_hue="violet",
        secondary_hue="pink",
    ),
    css=css
) as app:

    gr.HTML("""
    <div style="text-align:center; padding: 20px 0 10px">
        <h1 style="font-size:2.5em; margin:0">🎬 TikTok Video Generator</h1>
        <p style="color:#666; font-size:1.1em">Gera vídeos TikTok automáticos com IA · 100% Gratuito · Open Source</p>
        <div style="display:flex; gap:10px; justify-content:center; flex-wrap:wrap; margin-top:10px">
            <span style="background:#f0f0f0; padding:4px 12px; border-radius:20px; font-size:0.85em">🤖 Multi-Agente IA</span>
            <span style="background:#f0f0f0; padding:4px 12px; border-radius:20px; font-size:0.85em">🎨 Imagens Geradas por IA</span>
            <span style="background:#f0f0f0; padding:4px 12px; border-radius:20px; font-size:0.85em">🔊 TTS Gratuito</span>
            <span style="background:#f0f0f0; padding:4px 12px; border-radius:20px; font-size:0.85em">📱 Formato 9:16</span>
            <span style="background:#f0f0f0; padding:4px 12px; border-radius:20px; font-size:0.85em">💬 Legendas TikTok</span>
        </div>
    </div>
    """)

    with gr.Tabs():

        # ─── Tab 1: Geração Simples ────────────────────────────────────────
        with gr.Tab("🎬 Gerar Vídeo"):
            with gr.Row():
                with gr.Column(scale=1):
                    gr.Markdown("### ⚙️ Configurações")

                    theme_dd = gr.Dropdown(
                        choices=theme_choices,
                        value="Curiosidades",
                        label="🎯 Tema do Vídeo",
                    )

                    topic_tb = gr.Textbox(
                        label="💡 Tópico Específico (opcional)",
                        placeholder="Ex: 'curiosidades sobre o oceano profundo'",
                        lines=1
                    )

                    with gr.Row():
                        duration_dd = gr.Dropdown(
                            choices=duration_choices,
                            value="30",
                            label="⏱️ Duração (segundos)"
                        )
                        lang_dd = gr.Dropdown(
                            choices=lang_choices,
                            value="🇵🇹 Português",
                            label="🌍 Idioma"
                        )

                    voice_dd = gr.Dropdown(
                        choices=voice_choices,
                        value="🇵🇹 Feminina (PT)",
                        label="🎤 Tipo de Voz"
                    )

                    style_dd = gr.Dropdown(
                        choices=style_choices,
                        value="TikTok",
                        label="💬 Estilo de Legendas"
                    )

                    with gr.Row():
                        music_cb = gr.Checkbox(
                            value=True,
                            label="🎵 Música de Fundo"
                        )
                        music_vol = gr.Slider(
                            minimum=0.05, maximum=0.5,
                            value=0.15, step=0.05,
                            label="🔉 Volume Música"
                        )

                    gen_btn = gr.Button(
                        "🚀 GERAR VÍDEO",
                        variant="primary",
                        size="lg"
                    )

                with gr.Column(scale=1):
                    gr.Markdown("### 🎥 Resultado")
                    video_out = gr.Video(
                        label="Vídeo Gerado",
                        elem_classes=["video-output"]
                    )
                    info_out = gr.Markdown("*Configura as opções e clica em Gerar Vídeo*")

            gen_btn.click(
                fn=generate_single_video,
                inputs=[
                    theme_dd, duration_dd, voice_dd, lang_dd,
                    style_dd, topic_tb, music_cb, music_vol
                ],
                outputs=[video_out, info_out],
                show_progress=True
            )

        # ─── Tab 2: Batch ─────────────────────────────────────────────────
        with gr.Tab("📦 Geração em Lote"):
            gr.Markdown("""
            ### 📦 Geração em Lote (Batch)
            Adiciona múltiplos vídeos à fila de processamento.
            Os vídeos são gerados automaticamente em paralelo.
            """)

            with gr.Row():
                with gr.Column():
                    b_theme = gr.Dropdown(choices=theme_choices, value="Curiosidades", label="🎯 Tema")
                    b_topic = gr.Textbox(label="💡 Tópico (opcional)", placeholder="Deixa vazio para IA escolher")
                    b_duration = gr.Dropdown(choices=duration_choices, value="30", label="⏱️ Duração")
                    b_voice = gr.Dropdown(choices=voice_choices, value="🇵🇹 Feminina (PT)", label="🎤 Voz")
                    b_lang = gr.Dropdown(choices=lang_choices, value="🇵🇹 Português", label="🌍 Idioma")
                    b_style = gr.Dropdown(choices=style_choices, value="TikTok", label="💬 Legendas")
                    b_music = gr.Checkbox(value=True, label="🎵 Música")
                    b_vol = gr.Slider(0.05, 0.5, value=0.15, step=0.05, label="🔉 Volume")

                with gr.Column():
                    b_num = gr.Slider(
                        minimum=1, maximum=10, value=3, step=1,
                        label="🔢 Número de Vídeos"
                    )
                    b_add_btn = gr.Button("➕ Adicionar à Fila", variant="primary")
                    b_result = gr.Markdown("*Configura e adiciona à fila*")

                    gr.Markdown("---")
                    gr.Markdown("### 📊 Status da Fila")
                    queue_status = gr.Markdown("*Aguardando...*")
                    refresh_btn = gr.Button("🔄 Atualizar Status")

            b_add_btn.click(
                fn=add_to_batch_queue,
                inputs=[b_theme, b_duration, b_voice, b_lang, b_style, b_topic, b_music, b_vol, b_num],
                outputs=[b_result]
            )

            refresh_btn.click(fn=get_queue_status, outputs=[queue_status])

        # ─── Tab 3: Biblioteca ────────────────────────────────────────────
        with gr.Tab("📚 Biblioteca"):
            gr.Markdown("### 📚 Vídeos Gerados")
            list_btn = gr.Button("🔄 Atualizar Lista", variant="secondary")
            videos_list = gr.Markdown("*Clica em Atualizar para ver os vídeos*")
            list_btn.click(fn=list_generated_videos, outputs=[videos_list])

        # ─── Tab 4: Guia ─────────────────────────────────────────────────
        with gr.Tab("📖 Guia de Instalação"):
            gr.Markdown("""
            # 📖 Guia Rápido de Instalação

            ## 1. Requisitos Base
            ```bash
            # Python 3.10+
            python --version

            # FFmpeg (obrigatório)
            # Windows: https://ffmpeg.org/download.html
            # Linux: sudo apt install ffmpeg
            # Mac: brew install ffmpeg
            ffmpeg -version
            ```

            ## 2. Instalar Dependências Python
            ```bash
            pip install -r requirements.txt
            ```

            ## 3. Configurar LLM (Escolhe um)

            ### Opção A: Ollama (Recomendado - 100% Local)
            ```bash
            # Instala Ollama: https://ollama.ai
            ollama pull llama3
            ollama serve  # Deixa a correr
            ```

            ### Opção B: Groq (Gratuito, Rápido)
            ```bash
            # Cria conta em: https://console.groq.com
            export GROQ_API_KEY="gsk_..."
            ```

            ## 4. Configurar Imagens (Escolhe um)

            ### Opção A: Pollinations.ai (Zero configuração!)
            Funciona automaticamente sem qualquer configuração!

            ### Opção B: Stable Diffusion Local
            ```bash
            # Instala AUTOMATIC1111: https://github.com/AUTOMATIC1111/stable-diffusion-webui
            # Corre com: --api --listen
            export SD_API_URL=http://127.0.0.1:7860
            ```

            ## 5. Configurar Voz

            ### edge-tts (Recomendado - Zero configuração)
            ```bash
            pip install edge-tts
            # Funciona automaticamente!
            ```

            ## 6. Adicionar Música de Fundo (Opcional)
            ```
            Coloca ficheiros .mp3 em: assets/music/
            Descarrega música livre de direitos em:
            - https://pixabay.com/music/
            - https://freemusicarchive.org/
            ```

            ## 7. Correr a Aplicação
            ```bash
            python app.py
            # Abre: http://localhost:7860
            ```

            ## 🚀 Melhorias Futuras
            - [ ] Upload automático para TikTok (via TikTok API)
            - [ ] Sistema de trending topics (via Twitter/Google Trends)
            - [ ] Templates salvos e reutilizáveis
            - [ ] Geração com personagens consistentes (LoRA)
            - [ ] Efeitos de texto animados avançados
            - [ ] Integração com música viral (Suno AI)
            - [ ] Dashboard de analytics de performance
            - [ ] Scheduler automático (publica em horas de pico)
            """)

    gr.HTML("""
    <div style="text-align:center; padding:15px; color:#999; font-size:0.85em; border-top:1px solid #eee; margin-top:20px">
        🎬 TikTok Video Generator | 100% Open Source | Sem APIs Pagas Obrigatórias
    </div>
    """)


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 7860))
    logger.info(f"Iniciando TikTok Video Generator na porta {port}...")
    app.launch(
        server_name="0.0.0.0",
        server_port=port,
        share=False,
        show_api=False,
        favicon_path=None,
    )
