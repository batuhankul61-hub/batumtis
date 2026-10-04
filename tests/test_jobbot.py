from pathlib import Path
from unittest import mock

import pytest
import yaml

from jobbot import __main__ as cli
from jobbot import matcher, sources
from jobbot.mailer import build_message

ROOT = Path(__file__).resolve().parent.parent

REMOTIVE = {"jobs": [
    {"id": 1, "url": "https://remotive.com/1", "title": "Customer Support Specialist",
     "company_name": "Acme", "category": "Customer Service", "tags": ["support"],
     "job_type": "full_time", "candidate_required_location": "Worldwide",
     "salary": "", "publication_date": "2026-10-01",
     "description": "<p>Send your CV to <a href='mailto:jobs@acme.io'>us</a></p>"},
    {"id": 2, "url": "https://remotive.com/2", "title": "Senior Customer Support Lead",
     "company_name": "Big", "category": "Customer Service", "tags": [],
     "candidate_required_location": "Worldwide", "description": "customer support"},
    {"id": 3, "url": "https://remotive.com/3", "title": "Data Entry Clerk",
     "company_name": "USOnly", "category": "Data", "tags": [],
     "candidate_required_location": "USA only", "description": "data entry"},
]}
REMOTEOK = [
    {"legal": "notice"},
    {"id": "9", "position": "Virtual Assistant", "company": "Helper",
     "tags": ["assistant"], "location": "", "apply_url": "https://x.com/apply",
     "description": "virtual assistant, data entry. Apply on our site. noreply@helper.com"},
]
ARBEITNOW = {"data": [
    {"slug": "a", "title": "Data Entry", "company_name": "Onsite", "remote": False,
     "description": "", "url": "u", "tags": [], "location": "Berlin"},
    {"slug": "b", "title": "Customer Service Agent", "company_name": "EU Co",
     "remote": True, "description": "Email hr@euco.de", "url": "u2", "tags": [],
     "location": "Europe"},
]}


@pytest.fixture
def cfg(tmp_path):
    c = yaml.safe_load((ROOT / "config.example.yaml").read_text(encoding="utf-8"))
    cv = tmp_path / "cv.pdf"
    cv.write_bytes(b"%PDF-1.4 fake")
    c["profile"]["cv_path"] = str(cv)
    c["cover_letter_template"] = str(ROOT / "templates/cover_letter_en.txt")
    c["database"] = str(tmp_path / "t.db")
    c["export"] = {"html": str(tmp_path / "o.html"), "csv": str(tmp_path / "o.csv")}
    c["delay_seconds"] = [0, 0]
    p = tmp_path / "config.yaml"
    p.write_text(yaml.safe_dump(c, allow_unicode=True), encoding="utf-8")
    return c, str(p)


def all_jobs():
    return (sources.parse_remotive(REMOTIVE) + sources.parse_remoteok(REMOTEOK)
            + sources.parse_arbeitnow(ARBEITNOW))


def test_parsers():
    jobs = all_jobs()
    assert len(jobs) == 5  # remoteok uyarısı ve ofis işi atlandı
    assert jobs[0].company == "Acme"
    assert "mailto:jobs@acme.io" in jobs[0].description
    assert jobs[3].location == "Worldwide"


def test_matching_filters(cfg):
    c, _ = cfg
    titles = [j.title for j, _ in matcher.match(all_jobs(), c)]
    assert "Customer Support Specialist" in titles
    assert "Virtual Assistant" in titles
    assert "Customer Service Agent" in titles
    assert "Senior Customer Support Lead" not in titles  # exclude
    assert "Data Entry Clerk" not in titles              # USA only


def test_find_email():
    jobs = {j.company: j for j in all_jobs()}
    assert matcher.find_apply_email(jobs["Acme"]) == "jobs@acme.io"
    assert matcher.find_apply_email(jobs["Helper"]) is None  # noreply yok sayılır
    assert matcher.find_apply_email(jobs["EU Co"]) == "hr@euco.de"


def test_message(cfg):
    c, _ = cfg
    job = all_jobs()[0]
    msg = build_message(job, "jobs@acme.io", c)
    assert msg["To"] == "jobs@acme.io"
    assert "Customer Support Specialist" in msg["Subject"]
    body = msg.get_body(("plain",)).get_content()
    assert "Dear Hiring Team at Acme" in body and "$" not in body
    assert [a.get_filename() for a in msg.iter_attachments()] == ["cv.pdf"]


def test_end_to_end(cfg, monkeypatch, capsys):
    c, path = cfg
    monkeypatch.setattr(sources, "fetch_all", lambda names, log=print: all_jobs())
    monkeypatch.setenv("JOBBOT_SMTP_PASSWORD", "x")
    sent = []

    class FakeSMTP:
        def __init__(self, *a, **k): pass
        def starttls(self, **k): pass
        def login(self, u, p): pass
        def send_message(self, m): sent.append(m["To"])
        def quit(self): pass

    # Deneme modu hiçbir şey göndermez
    with mock.patch("smtplib.SMTP", FakeSMTP):
        cli.main(["-c", path, "run"])
    assert sent == []
    assert "DENEME MODU" in capsys.readouterr().out

    with mock.patch("smtplib.SMTP", FakeSMTP):
        cli.main(["-c", path, "run", "--send"])
    assert sorted(sent) == ["hr@euco.de", "jobs@acme.io"]

    # Tekrar çalışınca aynı ilanlara yeniden başvurmaz
    with mock.patch("smtplib.SMTP", FakeSMTP):
        cli.main(["-c", path, "run", "--send"])
    assert len(sent) == 2

    html = Path(c["export"]["html"]).read_text(encoding="utf-8")
    assert "Virtual Assistant" in html and "Acme" not in html
