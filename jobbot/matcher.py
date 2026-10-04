"""İlanları kullanıcının profiline göre puanlar ve filtreler."""

from __future__ import annotations

import re

from .sources import Job

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
IGNORED_EMAIL_PARTS = ("noreply", "no-reply", "donotreply", "example.", "privacy", "gdpr")


def _contains(text: str, word: str) -> bool:
    return re.search(r"(?<!\w)" + re.escape(word.lower()) + r"(?!\w)", text) is not None


def score(job: Job, cfg: dict, base: int = 0, check_location: bool = True) -> int:
    """0 = uygun değil. Başlıktaki eşleşme 3, etiket 2, açıklama 1 puan.

    base: sitenin kendi aramasından gelen ilanlar zaten anahtar kelimeyle
    eşleştiği için verilen taban puan.
    """
    f = cfg.get("filters", {})
    title = job.title.lower()
    tags = " ".join(job.tags).lower()
    desc = job.description.lower()
    everything = f"{title} {tags} {desc}"

    for word in f.get("exclude_keywords", []):
        if _contains(title, word) or _contains(tags, word):
            return 0

    allowed = [l.lower() for l in f.get("allowed_locations", [])]
    loc = (job.location or "").lower()
    if check_location and allowed and loc and not any(a in loc for a in allowed):
        return 0

    for word in f.get("required_keywords", []):
        if not _contains(everything, word):
            return 0

    total = base
    for word in f.get("keywords", []):
        if _contains(title, word):
            total += 3
        elif _contains(tags, word):
            total += 2
        elif _contains(desc, word):
            total += 1
    return total


def match(jobs: list[Job], cfg: dict) -> list[tuple[Job, int]]:
    min_score = cfg.get("filters", {}).get("min_score", 3)
    scored = [(j, score(j, cfg)) for j in jobs]
    result = [(j, s) for j, s in scored if s >= min_score]
    result.sort(key=lambda x: x[1], reverse=True)
    return result


def find_apply_email(job: Job) -> str | None:
    """İlan metninde başvuru e-postası varsa döndürür."""
    for email in EMAIL_RE.findall(job.description):
        e = email.lower().rstrip(".")
        if not any(p in e for p in IGNORED_EMAIL_PARTS):
            return e
    return None
