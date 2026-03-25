"""
Agente 2: Divisor de Cenas
Processa e otimiza a divisão do script em cenas individuais
"""

import logging
from typing import List, Dict
import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent.parent))

logger = logging.getLogger(__name__)


class SceneSplitterAgent:
    """Agente que divide e otimiza cenas para produção de vídeo."""

    def __init__(self):
        logger.info("SceneSplitterAgent inicializado")

    def process_scenes(self, script: dict, duration: int, job_id: str = "") -> List[Dict]:
        """
        Processa o script e retorna lista de cenas otimizadas.

        Args:
            script: Script gerado pelo Agent 1
            duration: Duração total desejada em segundos
            job_id: ID do job para logging

        Returns:
            Lista de cenas com todos os metadados necessários
        """
        logger.info(f"[{job_id}] Processando {len(script.get('cenas', []))} cenas")

        cenas_raw = script.get("cenas", [])
        hook = script.get("hook", "")
        cta = script.get("call_to_action", "")

        # Injeta hook na primeira cena se não estiver lá
        if cenas_raw and hook and hook not in cenas_raw[0].get("texto", ""):
            # Prepende o hook ao texto da primeira cena
            if len(cenas_raw[0]["texto"]) + len(hook) < 100:
                cenas_raw[0]["texto"] = hook + " " + cenas_raw[0]["texto"]
            else:
                # Cria cena separada para o hook
                hook_scene = {
                    "numero": 0,
                    "texto": hook,
                    "duracao": 3,
                    "descricao_visual": cenas_raw[0].get("descricao_visual", "dramatic opening shot"),
                    "emocao": "surpresa",
                    "is_hook": True
                }
                cenas_raw.insert(0, hook_scene)

        # Ajusta durações para bater com o total
        total_atual = sum(c.get("duracao", 5) for c in cenas_raw)
        if total_atual != duration and total_atual > 0:
            fator = duration / total_atual
            for cena in cenas_raw:
                cena["duracao"] = max(2, round(cena["duracao"] * fator))

        # Ajuste final para garantir total exato
        total_final = sum(c.get("duracao", 5) for c in cenas_raw)
        diff = duration - total_final
        if diff != 0 and cenas_raw:
            cenas_raw[-1]["duracao"] = max(2, cenas_raw[-1]["duracao"] + diff)

        # Processa cada cena
        cenas_processadas = []
        for i, cena in enumerate(cenas_raw):
            cena_proc = self._process_single_scene(
                cena, i, len(cenas_raw), script, job_id
            )
            cenas_processadas.append(cena_proc)

        logger.info(f"[{job_id}] {len(cenas_processadas)} cenas processadas. Duração total: {sum(c['duracao'] for c in cenas_processadas)}s")
        return cenas_processadas

    def _process_single_scene(
        self, cena: dict, index: int, total: int, script: dict, job_id: str
    ) -> Dict:
        """Processa uma cena individual e adiciona metadados de produção."""
        duracao = max(2, cena.get("duracao", 5))

        # Calcula número de palavras faladas por segundo (ritmo TikTok)
        texto = cena.get("texto", "")
        palavras = len(texto.split())
        palavras_por_segundo = palavras / max(duracao, 1)

        # Se ritmo muito rápido, trunca o texto
        MAX_PALAVRAS_SEG = 2.8  # ritmo máximo confortável
        if palavras_por_segundo > MAX_PALAVRAS_SEG:
            max_palavras = int(MAX_PALAVRAS_SEG * duracao)
            texto = " ".join(texto.split()[:max_palavras]) + "..."

        # Tipo de transição com base na posição
        if index == 0:
            transicao = "fade_in"
        elif index == total - 1:
            transicao = "fade_out"
        else:
            transicao = self._choose_transition(cena.get("emocao", ""))

        # Efeito de câmara com base na emoção
        camera_effect = self._choose_camera_effect(cena.get("emocao", ""), index)

        # Prompt visual melhorado
        visual_prompt = self._enhance_visual_prompt(
            cena.get("descricao_visual", ""),
            cena.get("emocao", ""),
            script.get("titulo", "")
        )

        return {
            "numero": index + 1,
            "texto": texto,
            "texto_original": cena.get("texto", texto),
            "duracao": duracao,
            "descricao_visual": visual_prompt,
            "emocao": cena.get("emocao", "curiosidade"),
            "transicao_entrada": transicao,
            "camera_effect": camera_effect,
            "is_hook": cena.get("is_hook", False),
            "is_last": index == total - 1,
            "palavras_por_segundo": round(palavras_por_segundo, 2),
            # Ficheiros que serão gerados
            "image_path": None,
            "audio_path": None,
            "subtitle_data": None,
        }

    def _choose_transition(self, emocao: str) -> str:
        """Escolhe transição com base na emoção da cena."""
        transitions = {
            "surpresa": "zoom_in",
            "curiosidade": "slide_left",
            "motivação": "zoom_in",
            "alegria": "slide_right",
            "suspense": "cross_dissolve",
            "tristeza": "fade",
            "raiva": "cut",
        }
        return transitions.get(emocao.lower(), "cross_dissolve")

    def _choose_camera_effect(self, emocao: str, index: int) -> str:
        """Escolhe efeito de câmara para dynamismo."""
        effects = {
            "surpresa": "zoom_in_slow",
            "curiosidade": "pan_right",
            "motivação": "zoom_out_slow",
            "alegria": "bounce",
            "suspense": "zoom_in_slow",
            "default": ["ken_burns", "pan_left", "pan_right", "zoom_in_slow", "zoom_out_slow"]
        }
        if emocao.lower() in effects:
            return effects[emocao.lower()]
        # Alterna efeitos para variedade
        default_effects = effects["default"]
        return default_effects[index % len(default_effects)]

    def _enhance_visual_prompt(self, prompt: str, emocao: str, titulo: str) -> str:
        """Melhora o prompt visual para melhor qualidade de imagem."""
        # Adiciona qualidade base
        quality_tags = "masterpiece, best quality, ultra-detailed, sharp focus, 8k uhd"

        # Adiciona estilo com base na emoção
        emotion_styles = {
            "surpresa": "dramatic lighting, strong contrast",
            "curiosidade": "intriguing composition, mysterious atmosphere",
            "motivação": "epic composition, golden hour lighting, inspiring",
            "alegria": "vibrant colors, warm lighting, joyful",
            "suspense": "dark moody lighting, tension, cinematic",
            "tristeza": "soft lighting, melancholic, desaturated",
            "raiva": "high contrast, red tones, powerful",
        }
        emotion_style = emotion_styles.get(emocao.lower(), "cinematic, professional")

        # Formato vertical obrigatório
        format_tags = "vertical composition, portrait orientation, 9:16 aspect ratio"

        # Evita elementos indesejados
        negative_hint = ""  # Será usado como negative prompt separado

        enhanced = f"{prompt}, {emotion_style}, {format_tags}, {quality_tags}"
        return enhanced

    def get_negative_prompt(self) -> str:
        """Retorna negative prompt padrão para qualidade."""
        return (
            "blurry, low quality, distorted, watermark, text, signature, "
            "cropped, out of frame, extra limbs, deformed, ugly, bad anatomy, "
            "nsfw, violent, gore, horizontal orientation, landscape format"
        )
