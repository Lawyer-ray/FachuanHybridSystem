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
VOICEDESIGN_MODEL = "mimo-v2.5-tts-voicedesign"
DEFAULT_STYLE_PROMPT = "一个中年女性邻居，说话亲切自然，语速稍慢，像在街坊聊天一样娓娓道来，带有生活气息和故事感"

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
        self._default_style_prompt = svc.get_value("MIMO_TTS_STYLE_PROMPT", "") or DEFAULT_STYLE_PROMPT

    def synthesize(
        self,
        text: str,
        voice: str | None = None,
        audio_format: str = "mp3",
        style_prompt: str | None = None,
    ) -> bytes:
        """Convert text to speech audio bytes.

        Args:
            text: Text to synthesize.
            voice: Voice name for builtin mode (冰糖/茉莉/苏打/白桦). Ignored in VoiceDesign mode.
            audio_format: Output format (mp3/wav/pcm/pcm16).
            style_prompt: Natural language voice description for VoiceDesign mode.
                If provided, uses mimo-v2.5-tts-voicedesign model.
                If None, falls back to builtin voice mode.

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

        # Determine mode: VoiceDesign if style_prompt is provided, otherwise builtin
        use_voicedesign = bool(style_prompt)
        model = VOICEDESIGN_MODEL if use_voicedesign else self._model
        voice = voice or self._default_voice
        if not style_prompt:
            style_prompt = self._default_style_prompt

        # Split long text into chunks
        chunks = self._split_text(text)
        logger.info(
            "TTS synthesis: %d chars -> %d chunks, mode=%s, model=%s",
            len(text), len(chunks), "voicedesign" if use_voicedesign else "builtin", model,
        )

        audio_parts: list[bytes] = []
        for i, chunk in enumerate(chunks):
            logger.info("Synthesizing chunk %d/%d (%d chars)", i + 1, len(chunks), len(chunk))
            if use_voicedesign:
                part = self._call_api_voicedesign(chunk, style_prompt, audio_format)
            else:
                part = self._call_api(chunk, voice, audio_format)
            audio_parts.append(part)

        return b"".join(audio_parts)

    def _call_api_voicedesign(self, text: str, style_prompt: str, audio_format: str) -> bytes:
        """Call MiMo TTS API in VoiceDesign mode."""
        url = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": VOICEDESIGN_MODEL,
            "messages": [
                {"role": "user", "content": style_prompt},
                {"role": "assistant", "content": text},
            ],
            "audio": {"format": audio_format},
            "stream": False,
        }
        return self._do_request(url, headers, payload)

    def _call_api(self, text: str, voice: str, audio_format: str) -> bytes:
        """Call the MiMo TTS API for a single text chunk (builtin voice mode)."""
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
        return self._do_request(url, headers, payload)

    @staticmethod
    def _do_request(url: str, headers: dict, payload: dict) -> bytes:
        """Execute TTS API request and return audio bytes."""

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
