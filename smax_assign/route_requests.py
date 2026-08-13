#!/usr/bin/env python3
"""SMAX taleplerini is kurallarina gore dogru tedarikciye yonlendirir.

Ornek kural: Sercan Bey'in sorumlulugundaki lokasyonlarda klima talepleri
Proasist'e degil Ulusal'a yonlendirilir.

Kullanim:
    # 1) Alan adlarini kesfet (routing_rules.json'i doldurmak icin)
    python route_requests.py --show-sample

    # 2) Kurallari uygula ama hicbir sey degistirme (rapor)
    python route_requests.py --dry-run

    # 3) Gercek yonlendirme
    python route_requests.py --yes
"""

import argparse
import csv
import os
import sys

import routing
from smax_client import (build_session, bulk_update, fetch_all, login,
                         prompt_credentials, show_sample)

DEFAULT_ACTIVE_STATUSES = [
    "RequestStatusReady",
    "RequestStatusInProgress",
    "RequestStatusPending",
    "RequestStatusSuspended",
]

BASE_LAYOUT = ["Id", "DisplayLabel", "Description", "Status", "Category", "Service", "Location"]


def build_layout(config: routing.RulesConfig) -> str:
    """Kurallarin ihtiyac duydugu tum alanlari layout'a ekler."""
    fields = list(BASE_LAYOUT)
    for area in config.areas.values():
        fields.extend(area.get("match_fields") or [area.get("match_field", "Location")])
    for rule in config.rules:
        spec = rule.get("when", {}).get("any_keyword_in", {})
        fields.extend(spec.get("fields", []))
    for vendor in config.vendors.values():
        if vendor.get("field") and not vendor["field"].startswith("<<"):
            fields.append(vendor["field"])
    seen, ordered = set(), []
    for f in fields:
        if f and not f.startswith("<<") and f not in seen:
            seen.add(f)
            ordered.append(f)
    return ",".join(ordered)


def write_report(decisions: list, path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["TalepId", "Baslik", "Karar", "MevcutTedarikci",
                         "HedefTedarikci", "Kural", "Aciklama"])
        for d in decisions:
            writer.writerow([d.request_id, d.label, d.action, d.current_vendor,
                             d.target_vendor, d.rule_name, d.reason])
    print(f"Rapor yazildi: {path}")


def main() -> None:
    p = argparse.ArgumentParser(description="SMAX taleplerini kurallara gore yonlendirir.")
    p.add_argument("--base-url", default=os.environ.get("SMAX_BASE_URL", "https://flodesk.flo.com.tr"))
    p.add_argument("--tenant", default=os.environ.get("SMAX_TENANT", "316651941"))
    p.add_argument("--username", default=os.environ.get("SMAX_USERNAME"))
    p.add_argument("--rules", default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                   "routing_rules.json"))
    p.add_argument("--filter", dest="filter_expr", default=None,
                   help="EMS filtresi. Varsayilan: yalnizca acik statuler")
    p.add_argument("--all", action="store_true", help="Kapalilar dahil tum talepler")
    p.add_argument("--report", default=None, help="Karar raporunu CSV olarak yaz")
    p.add_argument("--dry-run", action="store_true", help="Hicbir sey degistirme")
    p.add_argument("--yes", action="store_true", help="Onay sorusunu atla")
    p.add_argument("--insecure", action="store_true", help="TLS dogrulamasini kapat")
    p.add_argument("--show-sample", action="store_true",
                   help="Bir talebi tum alanlariyla yazdir ve cik")
    args = p.parse_args()

    config = routing.RulesConfig.load(args.rules)

    username, password = prompt_credentials(args.username)
    base_url = args.base_url.rstrip("/")
    session = build_session(args.insecure)
    login(session, base_url, args.tenant, username, password)
    print("Giris basarili.")

    if args.show_sample:
        show_sample(session, base_url, args.tenant, "Request")
        return

    problems = config.validate()
    if problems:
        print("\nYapilandirma eksik — routing_rules.json dosyasini doldurun:")
        for p_ in problems:
            print(f"  - {p_}")
        if not args.dry_run:
            raise SystemExit("\nEksikler giderilmeden gercek guncelleme yapilmaz. "
                             "Once --dry-run ile deneyin.")
        print("(--dry-run oldugu icin devam ediliyor; eslesme sonuclari eksik olabilir.)\n")

    if args.filter_expr:
        filter_expr = args.filter_expr
    elif args.all:
        filter_expr = ""
    else:
        filter_expr = "(" + " or ".join(f"Status='{s}'" for s in DEFAULT_ACTIVE_STATUSES) + ")"

    layout = build_layout(config)
    print(f"Talepler cekiliyor... (filtre: {filter_expr or 'YOK'})")
    entities = fetch_all(session, base_url, args.tenant, "Request", layout, filter_expr)
    print(f"Toplam {len(entities)} talep incelendi.\n")

    decisions = routing.evaluate_all(entities, config)
    to_update = [d for d in decisions if d.needs_update]
    already = [d for d in decisions if d.action == "already_correct"]

    for d in to_update:
        print(f"  #{d.request_id}  {d.current_vendor or '(yonlendirme yok)'} -> {d.target_vendor}"
              f"  |  {d.label[:60]}")
        print(f"      {d.reason}")

    print(f"\nOzet: {len(to_update)} talep guncellenecek, "
          f"{len(already)} talep zaten dogru, "
          f"{len(decisions) - len(to_update) - len(already)} talep kural disi.")

    if args.report:
        write_report(decisions, args.report)

    if not to_update:
        print("Guncellenecek talep yok.")
        return

    if args.dry_run:
        print("DRY-RUN: Hicbir degisiklik yapilmadi.")
        return

    if not args.yes:
        answer = input("Devam edilsin mi? (evet/hayir): ").strip().lower()
        if answer not in ("evet", "e", "yes", "y"):
            print("Iptal edildi.")
            return

    updates = [{"Id": d.request_id, d.field: d.value} for d in to_update]
    done = bulk_update(session, base_url, args.tenant, "Request", updates)
    print(f"Tamamlandi: {done}/{len(updates)} talep yonlendirildi.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\nIptal edildi.")
