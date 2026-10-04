"""Uzaktan iş ilanı kaynakları.

Her kaynak, ortak formatta Job nesneleri döndürür. Hepsi herkese açık
JSON API'leridir; giriş (login) gerektirmez.
"""

from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass, field
from html.parser import HTMLParser

USER_AGENT = "Mozilla/5.0 (jobbot; kisisel is arama araci)"


@dataclass
class Job:
    source: str
    id: str
    title: str
    company: str
    url: str
    description: str = ""
    tags: list[str] = field(default_factory=list)
    location: str = ""
    job_type: str = ""
    salary: str = ""
    published: str = ""

    @property
    def key(self) -> str:
        return f"{self.source}:{self.id}"


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self.links: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in ("br", "p", "li", "div", "h1", "h2", "h3", "h4"):
            self.parts.append("\n")
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)

    def handle_data(self, data):
        self.parts.append(data)


def html_to_text(html: str) -> str:
    """HTML'i düz metne çevirir; mailto: linklerini de metne ekler."""
    if not html:
        return ""
    parser = _TextExtractor()
    parser.feed(html)
    text = "".join(parser.parts)
    mailtos = [l for l in parser.links if l.lower().startswith("mailto:")]
    if mailtos:
        text += "\n" + "\n".join(mailtos)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def _get_json(url: str, timeout: int = 30):
    req = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _salary(lo, hi) -> str:
    if lo and hi:
        return f"{lo}-{hi}"
    return str(lo or hi or "")


# --- Ayrıştırıcılar (ağdan bağımsız, test edilebilir) -----------------------

def parse_remotive(data) -> list[Job]:
    return [
        Job(
            source="remotive",
            id=str(j.get("id")),
            title=j.get("title", ""),
            company=j.get("company_name", ""),
            url=j.get("url", ""),
            description=html_to_text(j.get("description", "")),
            tags=list(j.get("tags") or []) + [j.get("category", "")],
            location=j.get("candidate_required_location", ""),
            job_type=j.get("job_type", ""),
            salary=j.get("salary", ""),
            published=j.get("publication_date", ""),
        )
        for j in data.get("jobs", [])
    ]


def parse_remoteok(data) -> list[Job]:
    # İlk eleman yasal uyarı metnidir, "id" alanı yoktur.
    return [
        Job(
            source="remoteok",
            id=str(j.get("id")),
            title=j.get("position", ""),
            company=j.get("company", ""),
            url=j.get("apply_url") or j.get("url", ""),
            description=html_to_text(j.get("description", "")),
            tags=list(j.get("tags") or []),
            location=j.get("location", "") or "Worldwide",
            salary=_salary(j.get("salary_min"), j.get("salary_max")),
            published=j.get("date", ""),
        )
        for j in data
        if isinstance(j, dict) and j.get("id")
    ]


def parse_arbeitnow(data) -> list[Job]:
    return [
        Job(
            source="arbeitnow",
            id=str(j.get("slug")),
            title=j.get("title", ""),
            company=j.get("company_name", ""),
            url=j.get("url", ""),
            description=html_to_text(j.get("description", "")),
            tags=list(j.get("tags") or []),
            location=j.get("location", ""),
            job_type=", ".join(j.get("job_types") or []),
            published=str(j.get("created_at", "")),
        )
        for j in data.get("data", [])
        if j.get("remote")  # yalnızca uzaktan olanlar
    ]


def parse_jobicy(data) -> list[Job]:
    return [
        Job(
            source="jobicy",
            id=str(j.get("id")),
            title=j.get("jobTitle", ""),
            company=j.get("companyName", ""),
            url=j.get("url", ""),
            description=html_to_text(j.get("jobDescription", "")),
            tags=_as_list(j.get("jobIndustry")) + _as_list(j.get("jobLevel")),
            location=j.get("jobGeo", ""),
            job_type=", ".join(_as_list(j.get("jobType"))),
            salary=_salary(j.get("annualSalaryMin"), j.get("annualSalaryMax")),
            published=j.get("pubDate", ""),
        )
        for j in data.get("jobs", [])
    ]


def parse_himalayas(data) -> list[Job]:
    return [
        Job(
            source="himalayas",
            id=str(j.get("guid") or j.get("applicationLink")),
            title=j.get("title", ""),
            company=j.get("companyName", ""),
            url=j.get("applicationLink") or j.get("guid", ""),
            description=html_to_text(j.get("description", "")),
            tags=_as_list(j.get("categories")),
            location=", ".join(_as_list(j.get("locationRestrictions"))) or "Worldwide",
            job_type=j.get("employmentType", ""),
            salary=_salary(j.get("minSalary"), j.get("maxSalary")),
            published=str(j.get("pubDate", "")),
        )
        for j in data.get("jobs", [])
    ]


def _as_list(v) -> list[str]:
    if not v:
        return []
    if isinstance(v, list):
        return [str(x) for x in v]
    return [str(v)]


# --- Ağ üzerinden çekme ------------------------------------------------------

SOURCES = {
    "remotive": ("https://remotive.com/api/remote-jobs", parse_remotive),
    "remoteok": ("https://remoteok.com/api", parse_remoteok),
    "arbeitnow": ("https://www.arbeitnow.com/api/job-board-api", parse_arbeitnow),
    "jobicy": ("https://jobicy.com/api/v2/remote-jobs?count=100", parse_jobicy),
    "himalayas": ("https://himalayas.app/jobs/api?limit=100", parse_himalayas),
}


def fetch_all(names: list[str], log=print) -> list[Job]:
    jobs: list[Job] = []
    for name in names:
        if name not in SOURCES:
            log(f"[uyarı] bilinmeyen kaynak: {name}")
            continue
        url, parser = SOURCES[name]
        try:
            found = parser(_get_json(url))
            log(f"[{name}] {len(found)} ilan alındı")
            jobs.extend(found)
        except Exception as e:  # bir kaynak çökse de diğerleri devam etsin
            log(f"[{name}] hata: {e}")
    return jobs
