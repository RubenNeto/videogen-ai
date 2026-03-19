"""
Agent 5: Voiceover Agent
- Primary: edge-tts (Microsoft Neural TTS — grátis, sem chave, vozes genuinamente masculinas/femininas)
- Fallback: gTTS (Google TTS)
- Velocidade +15% via FFmpeg
"""
import asyncio
import logging
import os
import uuid
from backend.utils.config import settings

logger = logging.getLogger(__name__)

# edge-tts voice names — genuinamente diferentes, neural, gratuito
VOICE_MAP = {
    "male-uk":    "en-GB-RyanNeural",       # Masculino britânico, grave e claro
    "male-us":    "en-US-GuyNeural",         # Masculino americano, voz de narrador
    "male-au":    "en-AU-WilliamNeural",     # Masculino australiano
    "female-us":  "en-US-JennyNeural",       # Feminino americano, natural
    "female-uk":  "en-GB-SoniaNeural",       # Feminino britânico
    "female-au":  "en-AU-NatashaNeural",     # Feminino australiano
}
DEFAULT_VOICE = "male-uk"

# gTTS fallback tld por voice_id
GTTS_TLD = {
    "male-uk":   "co.uk",
    "male-us":   "us",
    "male-au":   "com.au",
    "female-us": "us",
    "female-uk": "co.uk",
    "female-au": "com.au",
}


class VoiceoverAgent:

    async def generate(self, script: dict, job_id: str = "", voice_id: str = DEFAULT_VOICE) -> str:
        text = script.get("full_script", "")
        if not text:
            raise ValueError("Empty script")

        out_dir = os.path.join(settings.TEMP_DIR, job_id)
        os.makedirs(out_dir, exist_ok=True)

        edge_voice = VOICE_MAP.get(voice_id, VOICE_MAP[DEFAULT_VOICE])
        logger.info(f"[{job_id}] Voice: {voice_id} → {edge_voice} | {len(text)} chars")

        raw_path = os.path.join(out_dir, f"voice_raw_{uuid.uuid4().hex[:8]}.mp3")
        final_path = os.path.join(out_dir, f"voice_{uuid.uuid4().hex[:8]}.mp3")

        # 1. Tentar edge-tts (Microsoft Neural)
        try:
            await self._edge_tts(text, raw_path, edge_voice)
            logger.info(f"[{job_id}] edge-tts ✓ ({edge_voice})")
        except Exception as e:
            logger.warning(f"[{job_id}] edge-tts failed: {e} — using gTTS")
            tld = GTTS_TLD.get(voice_id, "co.uk")
            await self._gtts(text, raw_path, tld)
            logger.info(f"[{job_id}] gTTS fallback ✓ (tld={tld})")

        # 2. Acelerar +15%
        await self._speed_up(raw_path, final_path)
        logger.info(f"[{job_id}] Audio ready: {os.path.getsize(final_path)//1024}KB")
        return final_path

    async def _edge_tts(self, text: str, out_path: str, voice: str):
        """Microsoft Edge TTS — grátis, sem chave, vozes neurais reais."""
        import edge_tts
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(out_path)
        if not os.path.exists(out_path) or os.path.getsize(out_path) < 1000:
            raise RuntimeError("edge-tts produced empty file")

    async def _gtts(self, text: str, out_path: str, tld: str):
        from gtts import gTTS
        def _run():
            tts = gTTS(text=text, lang="en", tld=tld, slow=False)
            tts.save(out_path)
        await asyncio.get_event_loop().run_in_executor(None, _run)

    async def _speed_up(self, raw: str, out: str):
        """Aumentar velocidade 15% com FFmpeg atempo=1.15."""
        cmd = ["ffmpeg", "-y", "-i", raw, "-filter:a", "atempo=1.15", "-q:a", "2", out]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0 or not os.path.exists(out) or os.path.getsize(out) < 100:
            logger.warning(f"speed_up failed ({proc.returncode}), copying raw")
            import shutil
            shutil.copy(raw, out)
        else:
            try:
                os.remove(raw)
            except Exception:
                pass
