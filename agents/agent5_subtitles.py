"""
Agente 5: Gerador de Legendas Sincronizadas
Cria legendas estilo TikTok sincronizadas com o áudio
"""

import logging
import subprocess
import json
import re
from pathlib import Path
from typing import List, Dict, Optional
import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent.parent))
from config.settings import SUBTITLE_STYLES, FONTS_DIR

logger = logging.getLogger(__name__)


class SubtitleAgent:
    """Agente responsável por criar legendas sincronizadas estilo TikTok."""

    def __init__(self):
        logger.info("SubtitleAgent inicializado")

    def generate_subtitles(
        self,
        scene: dict,
        style: str = "tiktok",
        job_id: str = ""
    ) -> Optional[List[Dict]]:
        """
        Gera dados de legenda para uma cena.

        Args:
            scene: Cena com texto e duração
            style: Estilo das legendas ('tiktok', 'classic', 'neon', 'minimal')
            job_id: ID do job

        Returns:
            Lista de segmentos de legenda com timing
        """
        text = scene.get("texto", "")
        duration = scene.get("duracao_real", scene.get("duracao", 5))
        scene_num = scene.get("numero", 1)

        subtitle_style = SUBTITLE_STYLES.get(style, SUBTITLE_STYLES["tiktok"])
        words_per_line = subtitle_style.get("words_per_line", 4)
        uppercase = subtitle_style.get("uppercase", True)

        if uppercase:
            text = text.upper()

        # Divide texto em palavras
        words = text.split()
        if not words:
            return []

        # Cria grupos de palavras (linhas)
        lines = []
        for i in range(0, len(words), words_per_line):
            lines.append(" ".join(words[i:i + words_per_line]))

        # Calcula timing para cada linha
        time_per_line = duration / max(len(lines), 1)
        segments = []

        for i, line in enumerate(lines):
            start = i * time_per_line
            end = (i + 1) * time_per_line

            # Adiciona offset baseado no áudio (se disponível)
            segments.append({
                "text": line,
                "start": round(start, 3),
                "end": round(end, 3),
                "words": line.split(),
                "line_index": i,
                "total_lines": len(lines),
            })

        logger.info(f"[{job_id}] Cena {scene_num}: {len(segments)} segmentos de legenda")
        return segments

    def transcribe_audio(self, audio_path: Path, job_id: str = "") -> Optional[List[Dict]]:
        """
        Transcreve áudio real usando Whisper para legendas precisas.
        Requer: pip install openai-whisper

        Args:
            audio_path: Path para o ficheiro de áudio
            job_id: ID do job

        Returns:
            Lista de segmentos com timing preciso
        """
        try:
            import whisper
            logger.info(f"[{job_id}] Transcrevendo com Whisper: {audio_path}")

            model = whisper.load_model("base")  # Usa modelo base (leve)
            result = model.transcribe(
                str(audio_path),
                word_timestamps=True,
                fp16=False
            )

            segments = []
            for seg in result.get("segments", []):
                for word_info in seg.get("words", []):
                    segments.append({
                        "text": word_info["word"].strip().upper(),
                        "start": word_info["start"],
                        "end": word_info["end"],
                    })

            return segments

        except ImportError:
            logger.info("Whisper não instalado, usando timing automático")
            return None
        except Exception as e:
            logger.warning(f"Erro no Whisper: {e}")
            return None

    def create_ass_subtitle_file(
        self,
        all_scenes_subtitles: List[tuple],
        style: str,
        output_path: Path,
        job_id: str = ""
    ) -> Path:
        """
        Cria ficheiro .ASS (Advanced SubStation Alpha) com efeitos TikTok.
        O formato ASS suporta animações, cores e posicionamento avançado.

        Args:
            all_scenes_subtitles: Lista de (offset_segundos, lista_segmentos)
            style: Nome do estilo
            output_path: Onde salvar o ficheiro .ASS
            job_id: ID do job

        Returns:
            Path para o ficheiro .ASS criado
        """
        subtitle_style = SUBTITLE_STYLES.get(style, SUBTITLE_STYLES["tiktok"])

        font_size = subtitle_style["font_size"]
        font_color = self._hex_to_ass(subtitle_style["font_color"])
        stroke_color = self._hex_to_ass(subtitle_style["stroke_color"])
        stroke_width = subtitle_style["stroke_width"]
        y_offset = subtitle_style["y_offset"]
        bold = 1 if subtitle_style.get("bold", True) else 0
        highlight_color = self._hex_to_ass(subtitle_style.get("highlight_color", "#FFD700"))

        # Posição Y em pixels (1920 de altura)
        y_pos = int(1920 * y_offset)
        x_center = 540  # Centro horizontal (1080 / 2)

        # Cabeçalho ASS
        ass_content = f"""[Script Info]
Title: TikTok Generated Subtitles
ScriptType: v4.00+
WrapStyle: 0
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial Black,{font_size},{font_color},&H00FFFFFF,{stroke_color},&H80000000,{bold},0,0,0,100,100,0,0,1,{stroke_width},2,2,50,50,50,1
Style: Highlight,Arial Black,{font_size},{highlight_color},&H00FFFFFF,{stroke_color},&H80000000,{bold},0,0,0,100,100,0,0,1,{stroke_width},2,2,50,50,50,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        # Adiciona cada segmento de legenda
        for scene_offset, segments in all_scenes_subtitles:
            for seg in segments:
                start = scene_offset + seg["start"]
                end = scene_offset + seg["end"]

                start_str = self._seconds_to_ass_time(start)
                end_str = self._seconds_to_ass_time(end)

                text = seg["text"]

                # Efeitos TikTok: pop-in animation
                # {\fad(50,50)} - fade in/out rápido
                # {\pos(x,y)} - posição
                # {\t(\fscy120)} - scale up animation
                effect = (
                    f"{{\\pos({x_center},{y_pos})\\fad(50,50)"
                    f"\\t(0,80,\\fscy115)\\t(80,160,\\fscy100)}}"
                )

                ass_content += f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{effect}{text}\n"

        # Salva ficheiro
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(ass_content)

        logger.info(f"[{job_id}] Ficheiro de legendas criado: {output_path}")
        return output_path

    def _seconds_to_ass_time(self, seconds: float) -> str:
        """Converte segundos para formato de tempo ASS (H:MM:SS.cs)."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        centisecs = int((seconds - int(seconds)) * 100)
        return f"{hours}:{minutes:02d}:{secs:02d}.{centisecs:02d}"

    def _hex_to_ass(self, hex_color: str) -> str:
        """Converte cor hex (#RRGGBB) para formato ASS (&H00BBGGRR)."""
        hex_color = hex_color.lstrip("#")
        if len(hex_color) == 6:
            r = hex_color[0:2]
            g = hex_color[2:4]
            b = hex_color[4:6]
            return f"&H00{b}{g}{r}"
        return "&H00FFFFFF"

    def process_all_scenes(
        self, scenes: list, style: str, subtitle_path: Path, job_id: str = ""
    ) -> Path:
        """
        Processa todas as cenas e cria o ficheiro de legendas completo.

        Args:
            scenes: Lista de todas as cenas (com áudio gerado)
            style: Estilo de legenda
            subtitle_path: Onde salvar o .ASS
            job_id: ID do job

        Returns:
            Path para o ficheiro .ASS
        """
        all_subtitles = []
        current_offset = 0.0

        for scene in scenes:
            # Tenta transcrição real com Whisper primeiro
            whisper_segs = None
            if scene.get("audio_path"):
                whisper_segs = self.transcribe_audio(scene["audio_path"], job_id)

            # Usa timing automático se Whisper falhou
            if whisper_segs:
                segments = whisper_segs
            else:
                segments = self.generate_subtitles(scene, style, job_id) or []

            scene["subtitle_data"] = segments
            all_subtitles.append((current_offset, segments))

            # Avança offset pelo tempo real da cena
            duration = scene.get("duracao_real", scene.get("duracao", 5))
            current_offset += duration

        # Cria ficheiro ASS unificado
        return self.create_ass_subtitle_file(all_subtitles, style, subtitle_path, job_id)
