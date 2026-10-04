"""LinkedIn (Kolay Başvuru), Indeed (Indeed Apply) ve Kariyer.net modülleri.

Not: Bu sitelerin sayfa yapısı sık değişir. Düğmeler CSS sınıflarıyla değil
görünen adlarıyla (Türkçe + İngilizce) bulunur; yine de bir şey kırılırsa
aşağıdaki ad listelerini güncellemek genelde yeterlidir.
"""

from __future__ import annotations

import re
from urllib.parse import quote_plus

from ..sources import Job
from .base import Result, click_first, ensure_not_blocked, has_button, run_wizard

# Arama sonuç sayfasındaki ilan linklerini toplar.
_CARDS_JS = r"""
([hrefRe, attr]) => {
  const re = new RegExp(hrefRe);
  const seen = new Map();
  const nodes = [...document.querySelectorAll('a[href]')];
  if (attr) nodes.push(...document.querySelectorAll(`[${attr}]`));
  for (const a of nodes) {
    let id = attr && a.getAttribute(attr);
    let href = a.getAttribute('href') || '';
    if (!id) { const m = href.match(re); if (!m) continue; id = m[1]; }
    if (seen.has(id)) continue;
    const card = a.closest('li, article, [data-job-id], .job_seen_beacon, .list-items') || a;
    const lines = card.innerText.split('\n').map(s => s.trim()).filter(Boolean);
    const title = (a.innerText.split('\n').map(s => s.trim()).filter(Boolean)[0]) || lines[0] || '';
    const rest = lines.filter(l => l !== title);
    seen.set(id, {id, href: a.href || href, title, company: rest[0] || '', location: rest[1] || ''});
  }
  return [...seen.values()];
}
"""


def _collect(page, site: str, href_re: str, attr: str | None = None) -> list[Job]:
    return [
        Job(source=site, id=c["id"], title=c["title"], company=c["company"],
            url=c["href"], location=c["location"])
        for c in page.evaluate(_CARDS_JS, [href_re, attr])
        if c["title"]
    ]


def _scroll(page, times: int = 6):
    for _ in range(times):
        page.mouse.wheel(0, 2500)
        page.wait_for_timeout(600)


def _search_urls(cfg: dict, site: str, build) -> list[str]:
    b = cfg.get("browser", {})
    custom = (b.get("search_urls") or {}).get(site)
    if custom:
        return list(custom)
    terms = b.get("search_terms") or cfg.get("filters", {}).get("keywords", [])
    return [build(quote_plus(t)) for t in terms]


def _remote_ok(cfg: dict, text: str) -> bool:
    if not cfg.get("browser", {}).get("require_remote_text", True):
        return True
    return bool(re.search(r"remote|uzaktan|evden|home office|work from home|hybrid-remote", text, re.I))


# ---------------------------------------------------------------------------
class LinkedIn:
    name = "linkedin"
    base = "https://www.linkedin.com"
    login_url = "https://www.linkedin.com/login"

    APPLY = [r"easy apply", r"kolay başvuru"]
    NEXT = [r"continue to next step", r"^next$", r"review", r"ileri", r"sonraki", r"incele", r"gözden geçir"]
    SUBMIT = [r"submit application", r"başvuruyu gönder", r"başvuru gönder"]
    DONE = r"application was sent|your application was sent|başvurunuz gönderildi|başvurunuz .*gönderildi"
    ROOT = ".jobs-easy-apply-modal, [role=dialog]"

    def search(self, page, cfg) -> list[Job]:
        b = cfg.get("browser", {})
        loc = quote_plus(b.get("linkedin_location", "Türkiye"))
        jobs: dict[str, Job] = {}
        for url in _search_urls(
            cfg, self.name,
            # f_WT=2: uzaktan, f_AL=true: yalnızca Kolay Başvuru, sortBy=DD: en yeni
            lambda kw: f"{self.base}/jobs/search/?keywords={kw}&location={loc}&f_WT=2&f_AL=true&sortBy=DD",
        ):
            for p in range(b.get("max_pages", 2)):
                page.goto(f"{url}&start={25 * p}", wait_until="domcontentloaded")
                ensure_not_blocked(page, self.name)
                page.wait_for_timeout(2000)
                _scroll(page)
                found = _collect(page, self.name, r"/jobs/view/(\d+)", "data-job-id")
                for j in found:
                    j.url = f"{self.base}/jobs/view/{j.id}/"
                    jobs.setdefault(j.id, j)
                if not found:
                    break
        return list(jobs.values())

    def _cancel(self, page):
        def cancel():
            if click_first(page, [r"dismiss", r"kapat", r"close"]):
                page.wait_for_timeout(600)
                click_first(page, [r"discard", r"vazgeç", r"^sil$", r"^at$"])
        return cancel

    def apply(self, page, job: Job, cfg, send: bool) -> Result:
        page.goto(job.url, wait_until="domcontentloaded")
        ensure_not_blocked(page, self.name)
        page.wait_for_timeout(2500)
        text = page.locator("body").inner_text()
        job.description = text[:20000]
        if re.search(r"\bApplied\b|Başvuruldu|Başvurdunuz", text) and not has_button(page, self.APPLY):
            return Result("applied", "zaten başvurulmuş")
        if not click_first(page, self.APPLY):
            return Result("manual", "Kolay Başvuru düğmesi yok (şirket sitesinden başvurulmalı)")
        page.wait_for_timeout(1500)
        return run_wizard(page, job, cfg, send, root=self.ROOT, next_names=self.NEXT,
                          submit_names=self.SUBMIT, done_re=self.DONE, cancel=self._cancel(page))


# ---------------------------------------------------------------------------
class Indeed:
    name = "indeed"

    APPLY = [r"apply now", r"hemen başvur", r"şimdi başvur", r"^başvur$", r"easily apply", r"kolay başvur"]
    NEXT = [r"^continue", r"^devam", r"ileri", r"^next", r"review your application", r"başvurunu gözden geçir"]
    SUBMIT = [r"submit your application", r"başvurunu gönder", r"başvurunuzu gönder", r"^submit$", r"^gönder$"]
    DONE = r"application has been submitted|your application has been|başvurunuz gönderildi|başvurun gönderildi|başvurunuz iletildi"

    def __init__(self, domain: str = "tr.indeed.com"):
        self.base = f"https://{domain}"
        self.login_url = "https://secure.indeed.com/auth"

    def search(self, page, cfg) -> list[Job]:
        b = cfg.get("browser", {})
        jobs: dict[str, Job] = {}
        # sc=0kf:attr(DSQF7); -> "Uzaktan" filtresi
        for url in _search_urls(
            cfg, self.name,
            lambda kw: f"{self.base}/jobs?q={kw}&sc=0kf%3Aattr%28DSQF7%29%3B&sort=date",
        ):
            for p in range(b.get("max_pages", 2)):
                page.goto(f"{url}&start={10 * p}", wait_until="domcontentloaded")
                ensure_not_blocked(page, self.name)
                page.wait_for_timeout(2000)
                found = _collect(page, self.name, r"[?&]jk=([0-9a-f]{16})", "data-jk")
                for j in found:
                    j.url = f"{self.base}/viewjob?jk={j.id}"
                    jobs.setdefault(j.id, j)
                if not found:
                    break
        return list(jobs.values())

    def apply(self, page, job: Job, cfg, send: bool) -> Result:
        page.goto(job.url, wait_until="domcontentloaded")
        ensure_not_blocked(page, self.name)
        page.wait_for_timeout(2000)
        text = page.locator("body").inner_text()
        job.description = text[:20000]
        if not _remote_ok(cfg, text):
            return Result("skipped", "ilan metninde uzaktan çalışma geçmiyor")
        if re.search(r"you applied|başvurdunuz|başvuru yapıldı", text, re.I):
            return Result("applied", "zaten başvurulmuş")
        btn_scope = page.locator("#indeedApplyButton, [data-testid*=apply], body").first
        if not has_button(btn_scope, self.APPLY):
            return Result("manual", "Indeed üzerinden başvuru yok (şirket sitesinden başvurulmalı)")
        try:
            with page.context.expect_page(timeout=6000) as new:
                click_first(btn_scope, self.APPLY)
            target = new.value
            target.wait_for_load_state("domcontentloaded")
        except Exception:
            target = page  # aynı sekmede açıldı
        target.wait_for_timeout(2500)
        if "indeed." not in target.url:
            return Result("manual", f"şirket sitesine yönlendirdi: {target.url[:80]}")
        try:
            return run_wizard(target, job, cfg, send, root="body", next_names=self.NEXT,
                              submit_names=self.SUBMIT, done_re=self.DONE)
        finally:
            if target is not page:
                target.close()


# ---------------------------------------------------------------------------
class Kariyer:
    name = "kariyer"
    base = "https://www.kariyer.net"
    login_url = "https://www.kariyer.net/giris"

    APPLY = [r"^başvur$", r"hemen başvur", r"kolay başvur", r"başvuru yap"]
    NEXT = [r"^devam", r"ileri", r"sonraki"]
    SUBMIT = [r"başvuruyu tamamla", r"başvuruyu gönder", r"başvurumu gönder", r"^gönder$"]
    DONE = r"başvurunuz alındı|başvurunuz gönderildi|başvurunuz iletildi|başvurunuz başarıyla|başvuru yaptınız|başvurdunuz"

    def search(self, page, cfg) -> list[Job]:
        b = cfg.get("browser", {})
        jobs: dict[str, Job] = {}
        for url in _search_urls(cfg, self.name, lambda kw: f"{self.base}/is-ilanlari?kw={kw}"):
            for p in range(1, b.get("max_pages", 2) + 1):
                sep = "&" if "?" in url else "?"
                page.goto(f"{url}{sep}cp={p}", wait_until="domcontentloaded")
                ensure_not_blocked(page, self.name)
                page.wait_for_timeout(2000)
                found = _collect(page, self.name, r"/is-ilani/[^?#]*-(\d+)(?:[?#]|$)")
                for j in found:
                    jobs.setdefault(j.id, j)
                if not found:
                    break
        return list(jobs.values())

    def apply(self, page, job: Job, cfg, send: bool) -> Result:
        page.goto(job.url, wait_until="domcontentloaded")
        ensure_not_blocked(page, self.name)
        page.wait_for_timeout(2000)
        text = page.locator("body").inner_text()
        job.description = text[:20000]
        if not _remote_ok(cfg, text):
            return Result("skipped", "ilan metninde uzaktan çalışma geçmiyor")
        if re.search(self.DONE, text, re.I):
            return Result("applied", "zaten başvurulmuş")
        if not has_button(page, self.APPLY):
            return Result("manual", "başvur düğmesi bulunamadı")
        if not send:
            # Kariyer.net'te "Başvur" tek tıkla başvurabildiği için deneme modunda basılmaz
            return Result("would_apply")
        click_first(page, self.APPLY)
        page.wait_for_timeout(2500)
        if re.search(self.DONE, page.locator("body").inner_text(), re.I):
            return Result("applied")
        dialog = page.locator("[role=dialog]:visible, .modal.show, .modal:visible")
        root = "[role=dialog]:visible, .modal.show, .modal:visible" if dialog.count() else "main, body"
        return run_wizard(page, job, cfg, send, root=root, next_names=self.NEXT,
                          submit_names=self.SUBMIT + self.APPLY, done_re=self.DONE)


def get_sites(cfg: dict) -> dict:
    b = cfg.get("browser", {})
    all_sites = {
        "linkedin": LinkedIn(),
        "indeed": Indeed(b.get("indeed_domain", "tr.indeed.com")),
        "kariyer": Kariyer(),
    }
    return {n: all_sites[n] for n in b.get("sites", []) if n in all_sites}

