"""File-system helpers for stored certificate PDFs."""

from __future__ import annotations

import re
import unicodedata


def slugify(value: str, max_length: int = 60) -> str:
    """Turn arbitrary text into a safe filename fragment.

    Example: "Manvitha Cheekati" -> "manvitha-cheekati"

    Non-ASCII characters are normalised and anything that is not a
    letter, digit, dash or underscore is replaced with a dash so the
    resulting path is safe on macOS/Linux/Windows.
    """

    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return value[:max_length] or "recipient"


def certificate_filename(job_id: int, certificate_id: int, recipient_name: str) -> str:
    """Build a unique, readable and collision-free file name."""

    return f"job{job_id}_cert{certificate_id}_{slugify(recipient_name)}.pdf"
