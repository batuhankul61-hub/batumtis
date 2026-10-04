"""Ön yazı oluşturma ve e-posta ile başvuru gönderme."""

from __future__ import annotations

import mimetypes
import os
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path
from string import Template

from .sources import Job


def render_letter(job: Job, cfg: dict) -> tuple[str, str]:
    """(konu, metin) döndürür. Şablonda $name, $title, $company vb. kullanılabilir."""
    p = cfg["profile"]
    values = {
        "name": p.get("name", ""),
        "email": p.get("email", ""),
        "phone": p.get("phone", ""),
        "linkedin": p.get("linkedin", ""),
        "portfolio": p.get("portfolio", ""),
        "summary": p.get("summary", ""),
        "title": job.title,
        "company": job.company or "your company",
        "url": job.url,
    }
    tpl_path = Path(cfg.get("cover_letter_template", "templates/cover_letter_en.txt"))
    body = Template(tpl_path.read_text(encoding="utf-8")).safe_substitute(values)
    subject = Template(
        cfg.get("email_subject", "Application for $title - $name")
    ).safe_substitute(values)
    return subject, body


def build_message(job: Job, to: str, cfg: dict) -> EmailMessage:
    p = cfg["profile"]
    subject, body = render_letter(job, cfg)
    msg = EmailMessage()
    msg["From"] = f'{p.get("name", "")} <{p["email"]}>'
    msg["To"] = to
    msg["Subject"] = subject
    msg["Reply-To"] = p["email"]
    msg.set_content(body)

    cv = p.get("cv_path")
    if cv:
        path = Path(cv)
        if not path.exists():
            raise FileNotFoundError(f"CV dosyası bulunamadı: {cv}")
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        maintype, subtype = ctype.split("/", 1)
        msg.add_attachment(
            path.read_bytes(), maintype=maintype, subtype=subtype, filename=path.name
        )
    return msg


class Mailer:
    def __init__(self, cfg: dict):
        s = cfg["smtp"]
        self.host = s["host"]
        self.port = int(s.get("port", 587))
        self.user = s["user"]
        self.password = os.environ.get(s.get("password_env", "JOBBOT_SMTP_PASSWORD"))
        if not self.password:
            raise RuntimeError(
                f"SMTP şifresi bulunamadı. '{s.get('password_env', 'JOBBOT_SMTP_PASSWORD')}' "
                "ortam değişkenini ayarlayın."
            )
        self._smtp = None

    def __enter__(self):
        ctx = ssl.create_default_context()
        if self.port == 465:
            self._smtp = smtplib.SMTP_SSL(self.host, self.port, context=ctx)
        else:
            self._smtp = smtplib.SMTP(self.host, self.port)
            self._smtp.starttls(context=ctx)
        self._smtp.login(self.user, self.password)
        return self

    def send(self, msg: EmailMessage):
        self._smtp.send_message(msg)

    def __exit__(self, *exc):
        if self._smtp:
            self._smtp.quit()
