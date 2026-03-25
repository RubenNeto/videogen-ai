"""
Agent 5: Voiceover — 100% free, no API key needed.
Primary: edge-tts (Microsoft Neural TTS)
Fallback: gTTS with correct tld per voice gender
Speed: +15% via FFmpeg atempo
"""
import asyncio
import logging
import os
import shutil
import uuid

logger = logging.getLogger(__name__)

# Microsoft Neural voices (edge-tts) — genuinely different male/female
EDGE_VOICES = {
    "male-uk":   "en-GB-RyanNeural",
    "male-us":   "en-US-GuyNeural",
    "male-au":   "en-AU-WilliamNeural",
    "female-us": "en-US-JennyNeural",
    "female-uk": "en-GB-SoniaNeural",
    "female-au": "en-AU-NatashaNeural",
}

# gTTS tld fallback — co.uk sounds more male than us
GTTS_CONFIG = {
    "male-uk":   {"tld": "co.uk"},
    "male-us":   {"tld": "com.au"},   # com.au sounds deeper/male
    "male-au":   {"tld": "com.au"},
    "female-us": {"tld": "us"},
    "female-uk": {"tld": "co.uk"},
    "female-au": {"tld": "com.au"},
}
DEFAULT = "male-uk"


class VoiceoverAgent:

    async def generate(self, script: dict, job_id: str = "", voice_id: str = DEFAULT) -> str:
        text = (script.get("full_script") or "").strip()
        if not text:
            raise ValueError("Empty script — cannot generate voiceover")

        voice_id   = voice_id or DEFAULT
        out_dir    = os.path.join(__import__('backend.utils.config', fromlist=['settings']).settings.TEMP_DIR, job_id)
        os.makedirs(out_dir, exist_ok=True)
        raw_path   = os.path.join(out_dir, f"raw_{uuid.uuid4().hex[:6]}.mp3")
        final_path = os.path.join(out_dir, f"voice_{uuid.uuid4().hex[:6]}.mp3")

        logger.info(f"[{job_id}] Voice: {voice_id} | {len(text)} chars")

        # Try edge-tts (Microsoft Neural, free, no key)
        if await self._edge_tts(text, raw_path, voice_id, job_id):
            logger.info(f"[{job_id}] edge-tts ✓ ({EDGE_VOICES.get(voice_id, voice_id)})")
        else:
            # Fallback: gTTS with correct tld
            cfg = GTTS_CONFIG.get(voice_id, {"tld": "co.uk"})
            logger.info(f"[{job_id}] gTTS fallback tld={cfg['tld']}")
            await self._gtts(text, raw_path, cfg["tld"])

        # Speed +15%
        await self._speed_up(raw_path, final_path)
        size = os.path.getsize(final_path) if os.path.exists(final_path) else 0
        logger.info(f"[{job_id}] Audio ready: {size//1024}KB")
        return final_path

    async def _edge_tts(self, text: str, out_path: str, voice_id: str, job_id: str) -> bool:
        try:
            import edge_tts
            voice = EDGE_VOICES.get(voice_id, EDGE_VOICES[DEFAULT])
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(out_path)
            ok = os.path.exists(out_path) and os.path.getsize(out_path) > 500
            if not ok:
                logger.warning(f"[{job_id}] edge-tts produced empty file")
            return ok
        except ImportError:
            logger.warning(f"[{job_id}] edge-tts not installed — using gTTS")
            return False
        except Exception as e:
            logger.warning(f"[{job_id}] edge-tts error: {e}")
            return False

    async def _gtts(self, text: str, out_path: str, tld: str):
        from gtts import gTTS
        def _run():
            gTTS(text=text, lang="en", tld=tld, slow=False).save(out_path)
        await asyncio.get_event_loop().run_in_executor(None, _run)

    async def _speed_up(self, raw: str, out: str):
        cmd = ["ffmpeg", "-y", "-i", raw, "-filter:a", "atempo=1.15", "-q:a", "2", out]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE
        )
        _, err = await proc.communicate()
        if proc.returncode != 0 or not os.path.exists(out) or os.path.getsize(out) < 100:
            logger.warning(f"speed_up failed: {err.decode()[-100:]} — using raw")
            shutil.copy(raw, out)
        else:
            try: os.remove(raw)
            except: pass
