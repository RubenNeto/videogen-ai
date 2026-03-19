"""
Agent 5: Voiceover Agent
- Voz masculina
- Velocidade aumentada (+15%)
- Primary: ElevenLabs (se configurado)
- Fallback: gTTS com voz masculina + pydub para acelerar
"""
import asyncio
import logging
import os
import uuid
import httpx
from backend.utils.config import settings

logger = logging.getLogger(__name__)


class VoiceoverAgent:

    ELEVENLABS_URL = "https://api.elevenlabs.io/v1"
    # Adam — voz masculina natural do ElevenLabs (ID público)
    MALE_VOICE_ID = "pNInz6obpgDQGcFmaJgB"

    TONE_SETTINGS = {
        "energetic":  {"stability": 0.35, "similarity_boost": 0.8,  "style": 0.5},
        "calm":       {"stability": 0.70, "similarity_boost": 0.9,  "style": 0.1},
        "urgent":     {"stability": 0.25, "similarity_boost": 0.8,  "style": 0.6},
        "funny":      {"stability": 0.30, "similarity_boost": 0.75, "style": 0.7},
        "inspiring":  {"stability": 0.50, "similarity_boost": 0.85, "style": 0.4},
        "serious":    {"stability": 0.65, "similarity_boost": 0.85, "style": 0.2},
    }

    async def generate(self, script: dict, job_id: str = "") -> str:
        text = script.get("full_script", "")
        if not text:
            raise ValueError("Empty script")

        tone = script.get("tone", "energetic")
        out_dir = os.path.join(settings.TEMP_DIR, job_id)
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"voice_{uuid.uuid4().hex[:8]}.mp3")

        logger.info(f"[{job_id}] Voiceover: {len(text)} chars, tone={tone}")

        if settings.has_elevenlabs:
            try:
                voice_id = settings.ELEVENLABS_VOICE_ID or self.MALE_VOICE_ID
                await self._elevenlabs(text, tone, out_path, voice_id)
                logger.info(f"[{job_id}] ElevenLabs ✓ (male voice)")
                return out_path
            except Exception as e:
                logger.warning(f"[{job_id}] ElevenLabs failed: {e}. Using gTTS...")

        # Fallback gratuito — voz masculina + velocidade aumentada
        await self._gtts_male_fast(text, out_path)
        logger.info(f"[{job_id}] gTTS male+fast ✓")
        return out_path

    async def _elevenlabs(self, text: str, tone: str, out_path: str, voice_id: str):
        vs = self.TONE_SETTINGS.get(tone, self.TONE_SETTINGS["energetic"])
        async with httpx.AsyncClient(timeout=60) as http:
            resp = await http.post(
                f"{self.ELEVENLABS_URL}/text-to-speech/{voice_id}",
                headers={
                    "xi-api-key": settings.ELEVENLABS_API_KEY,
                    "Content-Type": "application/json",
                    "Accept": "audio/mpeg",
                },
                json={
                    "text": text,
                    "model_id": "eleven_turbo_v2",
                    "voice_settings": {**vs, "use_speaker_boost": True},
                },
            )
            resp.raise_for_status()
            with open(out_path, "wb") as f:
                f.write(resp.content)

    async def _gtts_male_fast(self, text: str, out_path: str):
        """
        gTTS com voz masculina (com tld='co.uk' soa mais grave)
        + FFmpeg para aumentar velocidade 15%.
        """
        from gtts import gTTS

        raw_path = out_path.replace(".mp3", "_raw.mp3")

        def _generate():
            # tld='co.uk' produz voz mais grave/masculina no gTTS
            tts = gTTS(text=text, lang="en", tld="co.uk", slow=False)
            tts.save(raw_path)

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _generate)

        # Aumentar velocidade 15% com FFmpeg (atempo=1.15)
        cmd = [
            "ffmpeg", "-y", "-i", raw_path,
            "-filter:a", "atempo=1.15",
            "-q:a", "2",
            out_path,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            # Se FFmpeg falhar, usa o raw sem alterar velocidade
            logger.warning(f"Speed adjustment failed, using raw: {stderr.decode()[-200:]}")
            import shutil
            shutil.copy(raw_path, out_path)

        # Limpar ficheiro raw
        try:
            os.remove(raw_path)
        except Exception:
            pass
