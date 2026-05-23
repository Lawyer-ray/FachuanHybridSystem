from __future__ import annotations

import base64
import logging

import httpx

logger = logging.getLogger("apps.content_ops.tts")

# MiMo TTS available voices
TTS_VOICES: dict[str, str] = {
    "冰糖": "冰糖",
    "茉莉": "茉莉",
    "苏打": "苏打",
    "白桦": "白桦",
}

DEFAULT_VOICE = "冰糖"
DEFAULT_MODEL = "mimo-v2.5-tts"

# Single request text length limit (characters)
_CHUNK_SIZE = 500


class TTSService:
    """MiMo TTS service using the chat/completions endpoint."""

    def __init__(self) -> None:
        from apps.core.services.system_config_service import SystemConfigService

        svc = SystemConfigService()
        self._api_key = svc.get_value("OPENAI_COMPATIBLE_API_KEY", "")
        self._base_url = (
            svc.get_value("OPENAI_COMPATIBLE_BASE_URL", "").rstrip("/")
            or "https://token-plan-sgp.xiaomimimo.com/v1"
        )
        self._model = svc.get_value("MIMO_TTS_MODEL", "") or DEFAULT_MODEL
        self._default_voice = svc.get_value("MIMO_TTS_VOICE", "") or DEFAULT_VOICE

    def synthesize(
        self,
        text: str,
        voice: str | None = None,
        audio_format: str = "mp3",
    ) -> bytes:
        """Convert text to speech audio bytes.

        Args:
            text: Text to synthesize.
            voice: Voice name (冰糖/茉莉/苏打/白桦). Uses default if None.
            audio_format: Output format (mp3/wav/pcm/pcm16).

        Returns:
            Raw audio bytes.

        Raises:
            ValueError: If text is empty or API key is missing.
            RuntimeError: If the API call fails.
        """
        if not text.strip():
            raise ValueError("Text cannot be empty")
        if not self._api_key:
            raise ValueError("OPENAI_COMPATIBLE_API_KEY is not configured")

        voice = voice or self._default_voice

        # Split long text into chunks
        chunks = self._split_text(text)
        logger.info(
            "TTS synthesis: %d chars -> %d chunks, voice=%s, model=%s",
            len(text), len(chunks), voice, self._model,
        )

        audio_parts: list[bytes] = []
        for i, chunk in enumerate(chunks):
            logger.info("Synthesizing chunk %d/%d (%d chars)", i + 1, len(chunks), len(chunk))
            part = self._call_api(chunk, voice, audio_format)
            audio_parts.append(part)

        return b"".join(audio_parts)

    def _call_api(self, text: str, voice: str, audio_format: str) -> bytes:
        """Call the MiMo TTS API for a single text chunk."""
        url = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._model,
            "messages": [{"role": "assistant", "content": text}],
            "audio": {"format": audio_format, "voice": voice},
            "stream": False,
        }

        # Use transport-level SSL bypass to work around Python SSL handshake issues
        # with some CDN/proxy configurations (curl works fine, but httpx fails)
        transport = httpx.HTTPTransport(verify=False)
        try:
            with httpx.Client(transport=transport, timeout=120) as client:
                resp = client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.error("TTS API HTTP error: %s %s", e.response.status_code, e.response.text[:500])
            raise RuntimeError(f"TTS API error {e.response.status_code}: {e.response.text[:200]}") from e
        except httpx.RequestError as e:
            logger.error("TTS API request failed: %s", e)
            raise RuntimeError(f"TTS API request failed: {e}") from e

        data = resp.json()
        try:
            audio_b64 = data["choices"][0]["message"]["audio"]["data"]
        except (KeyError, IndexError) as e:
            logger.error("Unexpected TTS response structure: %s", str(data)[:500])
            raise RuntimeError("Unexpected TTS response: missing audio data") from e

        return base64.b64decode(audio_b64)

    @staticmethod
    def _split_text(text: str) -> list[str]:
        """Split text into chunks at sentence boundaries."""
        if len(text) <= _CHUNK_SIZE:
            return [text]

        chunks: list[str] = []
        current = ""

        # Split on Chinese sentence-ending punctuation
        for char in text:
            current += char
            if char in ("。", "！", "？", "；", "\n") and len(current) >= 50:
                chunks.append(current.strip())
                current = ""

        if current.strip():
            # If the remaining text is too long, force split
            while len(current) > _CHUNK_SIZE:
                # Try to find a natural break point
                split_at = current.rfind("，", 0, _CHUNK_SIZE)
                if split_at < _CHUNK_SIZE // 2:
                    split_at = _CHUNK_SIZE
                chunks.append(current[:split_at].strip())
                current = current[split_at:].strip()

            if current.strip():
                chunks.append(current.strip())

        return [c for c in chunks if c]
