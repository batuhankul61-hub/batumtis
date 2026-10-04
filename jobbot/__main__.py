"""jobbot komut satırı.

Kullanım:
    python -m jobbot fetch            # ilanları çek, puanla, kaydet
    python -m jobbot list             # uygun ilanları listele
    python -m jobbot apply            # deneme: kime ne gönderileceğini göster
    python -m jobbot apply --send     # gerçekten e-posta ile başvur
    python -m jobbot export           # elle başvurulacakları HTML/CSV yap
    python -m jobbot run --send       # hepsini sırayla yap
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
    remaining = max(0, limit - db.applied_today())
    delay = cfg.get("delay_seconds", [30, 90])

    to_email, manual = [], 0
    for job, _ in db.by_status("new"):
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
        p.add_argument("--send", action="store_true", help="e-postaları gerçekten gönder")
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
        cmd_export(cfg, db)
        cmd_status(db)


if __name__ == "__main__":
    sys.exit(main())
