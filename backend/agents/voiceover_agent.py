"""
Agent 5: Voiceover Agent
Primary: ElevenLabs (realistic US voice)
Fallback: gTTS (Google Text-to-Speech — free, no API key needed)
"""
import logging
import os
import uuid
import httpx
from backend.utils.config import settings

logger = logging.getLogger(__name__)


class VoiceoverAgent:

    ELEVENLABS_URL = "https://api.elevenlabs.io/v1"

    # Voice personality mapped to tone
    TONE_SETTINGS = {
        "energetic":  {"stability": 0.3, "similarity_boost": 0.8, "style": 0.5},
        "calm":       {"stability": 0.7, "similarity_boost": 0.9, "style": 0.1},
        "urgent":     {"stability": 0.25, "similarity_boost": 0.8, "style": 0.6},
        "funny":      {"stability": 0.3, "similarity_boost": 0.75, "style": 0.7},
        "inspiring":  {"stability": 0.5, "similarity_boost": 0.85, "style": 0.4},
        "serious":    {"stability": 0.65, "similarity_boost": 0.85, "style": 0.2},
    }

    async def generate(self, script: dict, job_id: str = "") -> str:
        """Convert script to audio. Returns MP3 file path."""
        text = script.get("full_script", "")
        if not text:
            raise ValueError("Empty script — cannot generate voiceover")

        tone = script.get("tone", "energetic")
        out_dir = os.path.join(settings.TEMP_DIR, job_id)
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"voice_{uuid.uuid4().hex[:8]}.mp3")

        logger.info(f"[{job_id}] Voiceover: {len(text)} chars, tone={tone}")

        if settings.has_elevenlabs:
            try:
                await self._elevenlabs(text, tone, out_path)
                logger.info(f"[{job_id}] Voiceover: ElevenLabs ✓")
                return out_path
            except Exception as e:
                logger.warning(f"[{job_id}] ElevenLabs failed: {e}. Falling back to gTTS...")

        # Free fallback — no API key required
        await self._gtts(text, out_path)
        logger.info(f"[{job_id}] Voiceover: gTTS fallback ✓")
        return out_path

    async def _elevenlabs(self, text: str, tone: str, out_path: str):
        settings_data = self.TONE_SETTINGS.get(tone, self.TONE_SETTINGS["energetic"])
        async with httpx.AsyncClient(timeout=60) as http:
            resp = await http.post(
                f"{self.ELEVENLABS_URL}/text-to-speech/{settings.ELEVENLABS_VOICE_ID}",
                headers={
                    "xi-api-key": settings.ELEVENLABS_API_KEY,
                    "Content-Type": "application/json",
                    "Accept": "audio/mpeg",
                },
                json={
                    "text": text,
                    "model_id": "eleven_turbo_v2",
                    "voice_settings": {**settings_data, "use_speaker_boost": True},
                },
            )
            resp.raise_for_status()
            with open(out_path, "wb") as f:
                f.write(resp.content)

    async def _gtts(self, text: str, out_path: str):
        """Free Google TTS — no API key. Requires gtts package."""
        import asyncio
        from gtts import gTTS
        def _run():
            tts = gTTS(text=text, lang="en", tld="us", slow=False)
            tts.save(out_path)
        await asyncio.get_event_loop().run_in_executor(None, _run)
