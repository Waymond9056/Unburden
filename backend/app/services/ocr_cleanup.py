"""Deterministic cleanup for Tesseract output from camera / screen captures.

Digital-text PDFs never hit this path. We only apply a small regex map of known
OCR typos so retrieval / NLI see cleaner clinical wording.
"""

from __future__ import annotations

import re

_DETERMINISTIC_FIXES = (
    (re.compile(r"\batient\b", re.I), "Patient"),
    (re.compile(r"\bsollection\b", re.I), "Collection"),
    (re.compile(r"\bADsolute\b", re.I), "Absolute"),
    (re.compile(r"\bsxample\b", re.I), "example"),
    (re.compile(r"\bJrGering\b", re.I), "Ordering"),
    (re.compile(r"cells/yL\b", re.I), "cells/µL"),
    (re.compile(r"cells/uL\b", re.I), "cells/µL"),
    (re.compile(r"threshold of =300"), "threshold of ≥300"),
    (re.compile(r"threshold of = 300"), "threshold of ≥300"),
)


def cleanup_ocr_text(text: str) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return ""

    for pattern, replacement in _DETERMINISTIC_FIXES:
        cleaned = pattern.sub(replacement, cleaned)

    # Drop lone junk lines of 1–2 odd symbols (FaceTime chrome leftovers).
    lines = []
    for line in cleaned.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if len(stripped) <= 2 and not stripped.isalnum():
            continue
        lines.append(line.rstrip())
    return "\n".join(lines).strip()
