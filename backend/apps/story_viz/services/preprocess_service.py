from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass
class PreprocessResult:
    cleaned_text: str
    source_hash: str


class JudgmentPreprocessService:
    def preprocess(self, *, source_text: str, viz_type: str) -> PreprocessResult:
        text = (source_text or "").strip()
        text = "\n".join(line.strip() for line in text.splitlines() if line.strip())
        if len(text) > 12000:
            text = text[:12000]

        raw = f"{viz_type}\n{text}".encode()
        source_hash = hashlib.sha256(raw).hexdigest()
        return PreprocessResult(cleaned_text=text, source_hash=source_hash)
