"""
Agent 5: Voiceover
- Primary: edge-tts (Microsoft Neural — grátis, genuinamente masculino/feminino)
- Fallback: gTTS
- Speed +15% via FFmpeg
"""
import asyncio
import logging
import os
import shutil
import uuid
from backend.utils.config import settings

logger = logging.getLogger(__name__)

# Microsoft Neural voices — genuinamente diferentes por género
VOICE_MAP = {
    "male-uk":   "en-GB-RyanNeural",
    "male-us":   "en-US-GuyNeural",
    "male-au":   "en-AU-WilliamNeural",
    "female-us": "en-US-JennyNeural",
    "female-uk": "en-GB-SoniaNeural",
    "female-au": "en-AU-NatashaNeural",
}
DEFAULT_VOICE = "male-uk"

GTTS_TLD = {
    "male-uk":   "co.uk",
    "male-us":   "com",
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

        voice_id = voice_id or DEFAULT_VOICE
        edge_voice = VOICE_MAP.get(voice_id, VOICE_MAP[DEFAULT_VOICE])
        tld        = GTTS_TLD.get(voice_id, "co.uk")

        out_dir  = os.path.join(settings.TEMP_DIR, job_id)
        os.makedirs(out_dir, exist_ok=True)
        raw_path   = os.path.join(out_dir, f"raw_{uuid.uuid4().hex[:6]}.mp3")
        final_path = os.path.join(out_dir, f"voice_{uuid.uuid4().hex[:6]}.mp3")

        logger.info(f"[{job_id}] Voice: {voice_id} → {edge_voice} | {len(text)} chars")

        # Try edge-tts first
        edge_ok = await self._try_edge_tts(text, raw_path, edge_voice, job_id)

        if not edge_ok:
            # Fallback to gTTS
            logger.warning(f"[{job_id}] edge-tts failed, using gTTS tld={tld}")
            await self._gtts(text, raw_path, tld)

        # Speed up +15%
        await self._speed_up(raw_path, final_path)
        logger.info(f"[{job_id}] Audio: {os.path.getsize(final_path)//1024}KB")
        return final_path

    async def _try_edge_tts(self, text: str, out_path: str, voice: str, job_id: str) -> bool:
        """Returns True if successful."""
        try:
            import edge_tts
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(out_path)
            if os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
                logger.info(f"[{job_id}] edge-tts ✓ ({voice})")
                return True
            logger.warning(f"[{job_id}] edge-tts produced empty file")
            return False
        except ImportError:
            logger.warning(f"[{job_id}] edge-tts not installed")
            return False
        except Exception as e:
            logger.warning(f"[{job_id}] edge-tts error: {e}")
            return False

    async def _gtts(self, text: str, out_path: str, tld: str):
        from gtts import gTTS
        def _run():
            tts = gTTS(text=text, lang="en", tld=tld, slow=False)
            tts.save(out_path)
        await asyncio.get_event_loop().run_in_executor(None, _run)

    async def _speed_up(self, raw: str, out: str):
        """+15% speed via FFmpeg atempo."""
        cmd = ["ffmpeg", "-y", "-i", raw, "-filter:a", "atempo=1.15", "-q:a", "2", out]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0 or not os.path.exists(out) or os.path.getsize(out) < 100:
            logger.warning(f"speed_up failed, copying raw")
            shutil.copy(raw, out)
        else:
            try:
                os.remove(raw)
            except Exception:
                pass
