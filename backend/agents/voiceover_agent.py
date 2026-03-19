"""
Agent 5: Voiceover Agent
- Voz selecionada pelo utilizador (male-uk, male-us, female-us, etc.)
- Velocidade +15% via FFmpeg atempo
- Primary: ElevenLabs (se configurado)
- Fallback: gTTS com locale correto
"""
import asyncio
import logging
import os
import uuid
import httpx
from backend.utils.config import settings

logger = logging.getLogger(__name__)

# Mapeamento voice_id -> configuração gTTS
VOICE_CONFIG = {
    "male-uk":    {"tld": "co.uk",   "pitch_adj": "-5%",  "el_id": "pNInz6obpgDQGcFmaJgB"},  # Adam
    "male-us":    {"tld": "us",      "pitch_adj": "-3%",  "el_id": "TxGEqnHWrfWFTfGW9XjX"},  # Josh
    "male-au":    {"tld": "com.au",  "pitch_adj": "-4%",  "el_id": "pNInz6obpgDQGcFmaJgB"},  # Adam (AU)
    "female-us":  {"tld": "us",      "pitch_adj": "+2%",  "el_id": "21m00Tcm4TlvDq8ikWAM"},  # Rachel
    "female-uk":  {"tld": "co.uk",   "pitch_adj": "+3%",  "el_id": "AZnzlk1XvdvUeBnXmlld"},  # Domi
    "female-in":  {"tld": "co.in",   "pitch_adj": "+2%",  "el_id": "21m00Tcm4TlvDq8ikWAM"},  # Rachel
}
DEFAULT_VOICE = "male-uk"

ELEVENLABS_URL = "https://api.elevenlabs.io/v1"

TONE_SETTINGS = {
    "energetic":  {"stability": 0.35, "similarity_boost": 0.80, "style": 0.5},
    "calm":       {"stability": 0.70, "similarity_boost": 0.90, "style": 0.1},
    "urgent":     {"stability": 0.25, "similarity_boost": 0.80, "style": 0.6},
    "funny":      {"stability": 0.30, "similarity_boost": 0.75, "style": 0.7},
    "inspiring":  {"stability": 0.50, "similarity_boost": 0.85, "style": 0.4},
    "serious":    {"stability": 0.65, "similarity_boost": 0.85, "style": 0.2},
}


class VoiceoverAgent:

    async def generate(self, script: dict, job_id: str = "", voice_id: str = DEFAULT_VOICE) -> str:
        text = script.get("full_script", "")
        if not text:
            raise ValueError("Empty script")

        tone     = script.get("tone", "energetic")
        cfg      = VOICE_CONFIG.get(voice_id, VOICE_CONFIG[DEFAULT_VOICE])
        out_dir  = os.path.join(settings.TEMP_DIR, job_id)
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"voice_{uuid.uuid4().hex[:8]}.mp3")

        logger.info(f"[{job_id}] Voice: {voice_id} | tone: {tone} | {len(text)} chars")

        # ElevenLabs (se configurado)
        if settings.has_elevenlabs:
            try:
                el_voice = settings.ELEVENLABS_VOICE_ID or cfg["el_id"]
                await self._elevenlabs(text, tone, out_path, el_voice)
                # Acelerar +15%
                out_path = await self._speed_up(out_path, out_dir)
                logger.info(f"[{job_id}] ElevenLabs ✓ ({voice_id})")
                return out_path
            except Exception as e:
                logger.warning(f"[{job_id}] ElevenLabs failed: {e}")

        # gTTS fallback gratuito
        raw_path = out_path.replace(".mp3", "_raw.mp3")
        await self._gtts(text, raw_path, cfg["tld"])
        out_path = await self._speed_up(raw_path, out_dir)
        logger.info(f"[{job_id}] gTTS ✓ ({voice_id} tld={cfg['tld']})")
        return out_path

    async def _elevenlabs(self, text: str, tone: str, out_path: str, voice_id: str):
        vs = TONE_SETTINGS.get(tone, TONE_SETTINGS["energetic"])
        async with httpx.AsyncClient(timeout=60) as http:
            resp = await http.post(
                f"{ELEVENLABS_URL}/text-to-speech/{voice_id}",
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

    async def _gtts(self, text: str, out_path: str, tld: str):
        from gtts import gTTS
        def _run():
            tts = gTTS(text=text, lang="en", tld=tld, slow=False)
            tts.save(out_path)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _run)

    async def _speed_up(self, raw_path: str, out_dir: str) -> str:
        """Aumenta velocidade 15% via FFmpeg atempo=1.15"""
        out_path = os.path.join(out_dir, f"voice_fast_{uuid.uuid4().hex[:6]}.mp3")
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

        if proc.returncode != 0 or not os.path.exists(out_path):
            logger.warning(f"Speed-up failed: {stderr.decode()[-200:]} — using raw")
            return raw_path

        # Limpar raw
        try:
            os.remove(raw_path)
        except Exception:
            pass

        return out_path
