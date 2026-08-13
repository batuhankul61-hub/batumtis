#!/usr/bin/env python3
"""SMAX (Service Anywhere) talep atama otomasyonu.

FLO SMAX ortamindaki (https://flodesk.flo.com.tr/saw/...) talepleri (Request)
REST API uzerinden toplu olarak belirtilen kisiye atar.

Kullanim ornegi:
    export SMAX_PASSWORD='sifreniz'
    python assign_requests.py --username kullanici@flo.com.tr --dry-run

Once mutlaka --dry-run ile calistirip nelerin degisecegini gorun.
Gercek atama icin --dry-run bayragini kaldirip --yes ekleyin.

Tedarikci yonlendirmesi (ornegin klima taleplerinin Ulusal'a gitmesi) icin
bu script degil route_requests.py kullanilir.
"""

import argparse
import os
import sys

from smax_client import (build_session, bulk_update, fetch_all, find_person_id,
                         login, prompt_credentials, show_sample)

DEFAULT_ACTIVE_STATUSES = [
    "RequestStatusReady",
    "RequestStatusInProgress",
    "RequestStatusPending",
    "RequestStatusSuspended",
]


def main() -> None:
    p = argparse.ArgumentParser(description="SMAX taleplerini toplu olarak bir kisiye atar.")
    p.add_argument("--base-url", default=os.environ.get("SMAX_BASE_URL", "https://flodesk.flo.com.tr"))
    p.add_argument("--tenant", default=os.environ.get("SMAX_TENANT", "316651941"))
    p.add_argument("--username", default=os.environ.get("SMAX_USERNAME"),
                   help="SMAX giris e-postasi")
    p.add_argument("--assignee-email", default=None,
                   help="Taleplerin atanacagi kisinin e-postasi (varsayilan: giris yapan kullanici)")
    p.add_argument("--assign-field", default="AssignedPerson",
                   help="Atama alaninin adi (varsayilan: AssignedPerson; ortama gore "
                        "OwnedByPerson olabilir — --show-sample ile dogrulayin)")
    p.add_argument("--filter", dest="filter_expr", default=None,
                   help="EMS filtre ifadesi. Varsayilan: yalnizca acik statuler")
    p.add_argument("--all", action="store_true",
                   help="Statu filtresi uygulamadan TUM talepleri hedefle")
    p.add_argument("--dry-run", action="store_true",
                   help="Hicbir sey degistirme, sadece ne yapilacagini goster")
    p.add_argument("--yes", action="store_true", help="Onay sorusunu atla")
    p.add_argument("--insecure", action="store_true",
                   help="TLS sertifika dogrulamasini kapat (ic ag sertifikasi icin)")
    p.add_argument("--show-sample", action="store_true",
                   help="Tek bir talebi tum alanlariyla yazdir (alan adi kesfi icin) ve cik")
    args = p.parse_args()

    username, password = prompt_credentials(args.username)
    base_url = args.base_url.rstrip("/")
    session = build_session(args.insecure)
    login(session, base_url, args.tenant, username, password)
    print("Giris basarili.")

    if args.show_sample:
        show_sample(session, base_url, args.tenant, "Request")
        return

    assignee_email = args.assignee_email or username
    person_id = find_person_id(session, base_url, args.tenant, assignee_email)

    if args.filter_expr:
        filter_expr = args.filter_expr
    elif args.all:
        filter_expr = ""
    else:
        filter_expr = "(" + " or ".join(f"Status='{s}'" for s in DEFAULT_ACTIVE_STATUSES) + ")"

    layout = f"Id,DisplayLabel,Status,{args.assign_field}"
    print(f"Talepler cekiliyor... (filtre: {filter_expr or 'YOK - tum talepler'})")
    entities = fetch_all(session, base_url, args.tenant, "Request", layout, filter_expr)
    print(f"Toplam {len(entities)} talep bulundu.")

    to_assign = []
    for e in entities:
        props = e["properties"]
        if str(props.get(args.assign_field) or "") == person_id:
            continue  # zaten atanmis
        to_assign.append(str(props["Id"]))
        print(f"  #{props['Id']}  [{props.get('Status')}]  {props.get('DisplayLabel', '')[:80]}")

    if not to_assign:
        print("Atanacak talep yok (hepsi zaten bu kisiye atanmis olabilir).")
        return

    print(f"\n{len(to_assign)} talep '{assignee_email}' (Person Id={person_id}) uzerine atanacak.")
    if args.dry_run:
        print("DRY-RUN: Hicbir degisiklik yapilmadi.")
        return

    if not args.yes:
        answer = input("Devam edilsin mi? (evet/hayir): ").strip().lower()
        if answer not in ("evet", "e", "yes", "y"):
            print("Iptal edildi.")
            return

    updates = [{"Id": rid, args.assign_field: person_id} for rid in to_assign]
    done = bulk_update(session, base_url, args.tenant, "Request", updates)
    print(f"Tamamlandi: {done}/{len(updates)} talep atandi.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\nIptal edildi.")
