"""Tarayıcı oturumu ve sitelerin ortak kullandığı adım adım başvuru sihirbazı.

Giriş bilgileri programda saklanmaz: `python -m jobbot login <site>` ile açılan
tarayıcıda bir kez kendin giriş yaparsın, oturum `browser.profile_dir`
klasöründe kalır. CAPTCHA / güvenlik doğrulaması çıkarsa program durur ve
tarayıcıda senin çözmeni bekler; bunları atlatmaya çalışmaz.
"""

from __future__ import annotations

import random
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from ..mailer import render_letter
from ..sources import Job
from .forms import fill_form

BLOCK_URL_RE = re.compile(r"checkpoint|captcha|challenge|authwall|/login|/uas/|signin|giris", re.I)
BLOCK_TEXT_RE = re.compile(
    r"verify you are human|are you a robot|robot olmadığınızı|security check|güvenlik doğrulaması",
    re.I,
)


class Blocked(Exception):
    """Giriş yapılmamış ya da CAPTCHA çıktı ve çözülmedi."""


@dataclass
class Result:
    status: str          # applied | would_apply | manual | failed
    note: str = ""


def open_context(cfg: dict, playwright, headless: bool | None = None):
    b = cfg.get("browser", {})
    kwargs = {
        "user_data_dir": str(Path(b.get("profile_dir", "browser_profile")).resolve()),
        "headless": b.get("headless", False) if headless is None else headless,
        "viewport": {"width": 1280, "height": 900},
        "locale": b.get("locale", "tr-TR"),
    }
    if b.get("executable_path"):
        kwargs["executable_path"] = b["executable_path"]
    return playwright.chromium.launch_persistent_context(**kwargs)


def ensure_not_blocked(page, site: str):
    """Giriş/CAPTCHA sayfasındaysak kullanıcıdan çözmesini ister."""
    def blocked():
        if BLOCK_URL_RE.search(page.url):
            return True
        try:
            return bool(BLOCK_TEXT_RE.search(page.locator("body").inner_text(timeout=2000)))
        except Exception:
            return False

    if not blocked():
        return
    if not sys.stdin.isatty():
        raise Blocked(f"{site}: giriş/doğrulama gerekiyor. Önce: python -m jobbot login {site}")
    input(f"\n[{site}] Tarayıcıda giriş yapın veya doğrulamayı çözün, sonra Enter'a basın... ")
    page.wait_for_timeout(1500)
    if blocked():
        raise Blocked(f"{site}: doğrulama hâlâ çözülmedi")


def pause(cfg: dict, short: bool = False):
    lo, hi = cfg.get("browser", {}).get("delay_seconds", [20, 60])
    if short:
        lo, hi = min(lo, 1), min(hi, 3)
    time.sleep(random.uniform(lo, hi))


def click_first(scope, names: list[str], timeout: int = 1500) -> bool:
    """Adlarından biri eşleşen ilk görünür ve etkin düğmeye tıklar."""
    for name in names:
        btn = scope.get_by_role("button", name=re.compile(name, re.I))
        try:
            if btn.count() and btn.first.is_visible() and btn.first.is_enabled():
                btn.first.click(timeout=timeout)
                return True
        except Exception:
            continue
    return False


def has_button(scope, names: list[str]) -> bool:
    for name in names:
        btn = scope.get_by_role("button", name=re.compile(name, re.I))
        try:
            if btn.count() and btn.first.is_visible():
                return True
        except Exception:
            pass
    return False


def run_wizard(page, job: Job, cfg: dict, send: bool, *, root: str,
               next_names: list[str], submit_names: list[str],
               done_re: str, cancel=None, max_steps: int = 12) -> Result:
    """Çok adımlı başvuru formunu sonuna kadar doldurur.

    send=False ise son "Gönder" düğmesine basmadan iptal eder (deneme modu).
    """
    _, letter = render_letter(job, cfg)
    for _ in range(max_steps):
        page.wait_for_timeout(800)
        if re.search(done_re, page.locator("body").inner_text(), re.I):
            return Result("applied")
        missing = fill_form(page, root, cfg, cover_letter=letter)
        if missing:
            if cancel:
                cancel()
            return Result("manual", "doldurulamayan alanlar: " + "; ".join(missing[:5]))
        scope = page.locator(root).first
        if has_button(scope, submit_names):
            if not send:
                if cancel:
                    cancel()
                return Result("would_apply")
            click_first(scope, submit_names)
            page.wait_for_timeout(2000)
            if re.search(done_re, page.locator("body").inner_text(), re.I):
                return Result("applied")
            # Bazı siteler onay mesajı göstermez; gönder düğmesi kaybolduysa başarılı say
            if not has_button(page.locator(root).first, submit_names):
                return Result("applied")
            return Result("failed", "gönder düğmesine basıldı ama onay alınamadı")
        if not click_first(scope, next_names):
            if cancel:
                cancel()
            return Result("manual", "sonraki adım düğmesi bulunamadı")
        # Aynı adımda takıldıysak (doğrulama hatası) çık
        err = page.locator("[role=alert], .artdeco-inline-feedback--error, .error, .invalid-feedback")
        page.wait_for_timeout(500)
        try:
            if err.count() and err.first.is_visible() and err.first.inner_text().strip():
                msg = err.first.inner_text().strip()[:120]
                if cancel:
                    cancel()
                return Result("manual", f"form hatası: {msg}")
        except Exception:
            pass
    if cancel:
        cancel()
    return Result("manual", "çok fazla adım")
