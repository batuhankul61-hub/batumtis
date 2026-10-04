"""jobbot komut satırı.

Kullanım:
    python -m jobbot fetch            # ilanları çek, puanla, kaydet
    python -m jobbot list             # uygun ilanları listele
    python -m jobbot apply            # deneme: kime ne gönderileceğini göster
    python -m jobbot apply --send     # gerçekten e-posta ile başvur
    python -m jobbot export           # elle başvurulacakları HTML/CSV yap
    python -m jobbot run --send       # hepsini sırayla yap (tarayıcı siteleri dahil)
    python -m jobbot login linkedin   # LinkedIn/Indeed/Kariyer.net'e bir kez giriş yap
    python -m jobbot mark KEY applied # bir ilanın durumunu elle değiştir
    python -m jobbot status           # özet
"""

from __future__ import annotations

import argparse
import random
import sys
import time

import yaml

from . import matcher, sources
from .db import DB
from .export import export_csv, export_html
from .mailer import Mailer, build_message


def load_config(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


API_SOURCES = set(sources.SOURCES)


def cmd_fetch(cfg, db: DB):
    jobs = sources.fetch_all(cfg.get("sources", list(sources.SOURCES)))
    new = matched = 0
    for job, s in matcher.match(jobs, cfg):
        matched += 1
        if db.upsert(job, s):
            new += 1
    print(f"Toplam {len(jobs)} ilan, {matched} uygun, {new} yeni.")


def cmd_list(cfg, db: DB):
    for job, row in db.by_status("new", "manual"):
        print(f"[{row['score']:>2}] {row['status']:<7} {job.title} — {job.company} "
              f"({job.location})\n      {job.url}\n      anahtar: {job.key}")


def cmd_apply(cfg, db: DB, send: bool):
    limit = cfg.get("daily_limit", 20)
    remaining = max(0, limit - sum(db.applied_today(s) for s in API_SOURCES))
    delay = cfg.get("delay_seconds", [30, 90])

    to_email, manual = [], 0
    for job, _ in db.by_status("new"):
        if job.source not in API_SOURCES:
            continue  # tarayıcı siteleri ayrı işlenir
        email = matcher.find_apply_email(job)
        if email:
            to_email.append((job, email))
        else:
            db.set_status(job.key, "manual", note="e-posta yok, elle başvurulmalı")
            manual += 1
    print(f"{manual} ilan elle başvuru listesine eklendi (export ile bakın).")

    if not to_email:
        print("E-posta ile başvurulabilecek yeni ilan yok.")
        return
    to_email = to_email[:remaining]
    if not to_email:
        print(f"Günlük limit ({limit}) doldu.")
        return

    if not send:
        print(f"\nDENEME MODU — {len(to_email)} başvuru gönderilecekti:")
        for job, email in to_email:
            print(f"  -> {email:<35} {job.title} — {job.company}")
        print("\nGerçekten göndermek için: python -m jobbot apply --send")
        return

    with Mailer(cfg) as mailer:
        for i, (job, email) in enumerate(to_email):
            try:
                mailer.send(build_message(job, email, cfg))
                db.set_status(job.key, "applied", apply_email=email)
                print(f"[gönderildi] {email} — {job.title} @ {job.company}")
            except Exception as e:
                db.set_status(job.key, "failed", apply_email=email, note=str(e))
                print(f"[HATA] {email}: {e}")
            if i < len(to_email) - 1:
                time.sleep(random.uniform(*delay))  # spam gibi görünmemek için


# --- Tarayıcı siteleri (LinkedIn, Indeed, Kariyer.net) -----------------------

def _playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("Playwright kurulu değil: pip install playwright && playwright install chromium")
    return sync_playwright()


def cmd_login(cfg, site_name: str):
    from .browser.base import open_context
    from .browser.sites import Indeed, Kariyer, LinkedIn

    site = {"linkedin": LinkedIn(), "kariyer": Kariyer(),
            "indeed": Indeed(cfg.get("browser", {}).get("indeed_domain", "tr.indeed.com"))}[site_name]
    with _playwright() as p:
        ctx = open_context(cfg, p, headless=False)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(site.login_url)
        input(f"Tarayıcıda {site_name} hesabınıza giriş yapın, bitince buraya dönüp Enter'a basın... ")
        ctx.close()
    print("Oturum kaydedildi.")


def cmd_browser(cfg, db: DB, send: bool, do_search: bool = True, do_apply: bool = True):
    from .browser.base import Blocked, open_context, pause
    from .browser.sites import get_sites

    sites = get_sites(cfg)
    if not sites:
        return
    b = cfg.get("browser", {})
    min_score = cfg.get("filters", {}).get("min_score", 3)
    search_cfg = {**cfg, "filters": {**cfg.get("filters", {}), "required_keywords": []}}

    with _playwright() as p:
        ctx = open_context(cfg, p)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            for name, site in sites.items():
                try:
                    if do_search:
                        found = site.search(page, cfg)
                        new = 0
                        for job in found:
                            s = matcher.score(job, search_cfg, base=min_score, check_location=False)
                            if s >= min_score and db.upsert(job, s):
                                new += 1
                        print(f"[{name}] {len(found)} ilan bulundu, {new} yeni.")
                    if not do_apply:
                        continue
                    limit = b.get("daily_limit", {}).get(name, 25) if isinstance(
                        b.get("daily_limit"), dict) else b.get("daily_limit", 25)
                    remaining = max(0, limit - db.applied_today(name))
                    queue = [j for j, _ in db.by_status("new") if j.source == name]
                    if not queue:
                        continue
                    if remaining == 0:
                        print(f"[{name}] günlük limit ({limit}) doldu.")
                        continue
                    done = 0
                    for job in queue:
                        if done >= remaining:
                            break
                        try:
                            res = site.apply(page, job, cfg, send)
                        except Blocked:
                            raise
                        except Exception as e:
                            res = None
                            db.set_status(job.key, "failed", note=str(e)[:200])
                            print(f"[{name}][HATA] {job.title}: {e}")
                        if res:
                            db.update_job(job)
                            if res.status == "would_apply":
                                print(f"[{name}] (deneme) başvurulabilir: {job.title} — {job.company}")
                            else:
                                db.set_status(job.key, res.status, note=res.note)
                                print(f"[{name}] {res.status}: {job.title} — {job.company}"
                                      + (f" ({res.note})" if res.note else ""))
                            if res.status == "applied" and not res.note:
                                done += 1
                        pause(cfg, short=not send)
                except Blocked as e:
                    print(f"[{name}] durdu: {e}")
        finally:
            ctx.close()


def cmd_export(cfg, db: DB):
    rows = db.by_status("manual", "new")
    out = cfg.get("export", {})
    html_path = out.get("html", "basvurular.html")
    csv_path = out.get("csv", "basvurular.csv")
    export_html(rows, html_path, cfg)
    export_csv(rows, csv_path)
    print(f"{len(rows)} ilan yazıldı: {html_path}, {csv_path}")


def cmd_status(db: DB):
    c = db.counts()
    labels = {"new": "yeni", "applied": "başvuruldu", "manual": "elle başvurulacak",
              "skipped": "atlandı", "failed": "hata"}
    for k, v in c.items():
        print(f"{labels.get(k, k):<20} {v}")
    print(f"{'bugün başvurulan':<20} {db.applied_today()}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="jobbot", description="Uzaktan iş başvuru botu")
    ap.add_argument("-c", "--config", default="config.yaml")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("fetch")
    sub.add_parser("list")
    sub.add_parser("export")
    sub.add_parser("status")
    for name in ("apply", "run"):
        p = sub.add_parser(name)
        p.add_argument("--send", action="store_true", help="başvuruları gerçekten gönder")
        p.add_argument("--no-browser", action="store_true",
                       help="LinkedIn/Indeed/Kariyer.net'i atla")
    lg = sub.add_parser("login")
    lg.add_argument("site", choices=["linkedin", "indeed", "kariyer"])
    m = sub.add_parser("mark")
    m.add_argument("key")
    m.add_argument("status", choices=["applied", "skipped", "manual", "new"])
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    db = DB(cfg.get("database", "jobbot.db"))

    if args.cmd == "fetch":
        cmd_fetch(cfg, db)
    elif args.cmd == "list":
        cmd_list(cfg, db)
    elif args.cmd == "apply":
        cmd_apply(cfg, db, args.send)
        if not args.no_browser:
            cmd_browser(cfg, db, args.send, do_search=False)
    elif args.cmd == "login":
        cmd_login(cfg, args.site)
    elif args.cmd == "export":
        cmd_export(cfg, db)
    elif args.cmd == "status":
        cmd_status(db)
    elif args.cmd == "mark":
        db.set_status(args.key, args.status)
        print(f"{args.key} -> {args.status}")
    elif args.cmd == "run":
        cmd_fetch(cfg, db)
        cmd_apply(cfg, db, args.send)
        if not args.no_browser:
            cmd_browser(cfg, db, args.send)
        cmd_export(cfg, db)
        cmd_status(db)


if __name__ == "__main__":
    sys.exit(main())
