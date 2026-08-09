#!/usr/bin/env python3
"""SMAX (Service Anywhere) talep atama otomasyonu.

FLO SMAX ortamindaki (https://flodesk.flo.com.tr/saw/...) talepleri (Request)
REST API uzerinden toplu olarak belirtilen kisiye atar.

Kullanim ornegi:
    export SMAX_PASSWORD='sifreniz'
    python assign_requests.py \
        --base-url https://flodesk.flo.com.tr \
        --tenant 316651941 \
        --username kullanici@flo.com.tr \
        --dry-run

Once mutlaka --dry-run ile calistirip nelerin degisecegini gorun.
Gercek atama icin --dry-run bayragini kaldirip --yes ekleyin.
"""

import argparse
import getpass
import json
import os
import sys
import urllib.parse

import requests

DEFAULT_ACTIVE_STATUSES = [
    "RequestStatusReady",
    "RequestStatusInProgress",
    "RequestStatusPending",
    "RequestStatusSuspended",
]

PAGE_SIZE = 250
BULK_CHUNK_SIZE = 20


def build_session(insecure: bool) -> requests.Session:
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "Accept": "application/json"})
    if insecure:
        s.verify = False
        requests.packages.urllib3.disable_warnings()  # type: ignore[attr-defined]
    return s


def login(session: requests.Session, base_url: str, tenant: str, username: str, password: str) -> None:
    """SMAX kimlik dogrulamasi: token alir ve LWSSO cerezine yazar."""
    url = f"{base_url}/auth/authentication-endpoint/authenticate/login?TENANTID={tenant}"
    resp = session.post(url, json={"login": username, "password": password}, timeout=60)
    if resp.status_code != 200 or not resp.text.strip():
        raise SystemExit(
            f"Giris basarisiz (HTTP {resp.status_code}). Kullanici adi/sifreyi kontrol edin.\n{resp.text[:500]}"
        )
    token = resp.text.strip()
    session.cookies.set("LWSSO_COOKIE_KEY", token)
    session.cookies.set("TENANTID", tenant)


def ems_get(session: requests.Session, base_url: str, tenant: str, entity: str, params: dict) -> dict:
    url = f"{base_url}/rest/{tenant}/ems/{entity}"
    resp = session.get(url, params=params, timeout=120)
    if resp.status_code != 200:
        raise SystemExit(f"EMS sorgusu basarisiz (HTTP {resp.status_code}): {resp.text[:500]}")
    return resp.json()


def find_person_id(session: requests.Session, base_url: str, tenant: str, email: str) -> str:
    """E-posta (veya Upn) uzerinden Person kaydinin Id'sini bulur."""
    for field in ("Email", "Upn"):
        data = ems_get(
            session, base_url, tenant, "Person",
            {"filter": f"{field}='{email}'", "layout": "Id,Name,Email", "size": 5},
        )
        entities = data.get("entities", [])
        if entities:
            props = entities[0]["properties"]
            print(f"Kisi bulundu: Id={props['Id']} Name={props.get('Name')} Email={props.get('Email')}")
            return str(props["Id"])
    raise SystemExit(
        f"'{email}' icin Person kaydi bulunamadi. --assignee-email ile dogru adresi verin."
    )


def fetch_requests(session: requests.Session, base_url: str, tenant: str,
                   filter_expr: str, assign_field: str) -> list:
    """Filtreye uyan tum talepleri sayfa sayfa ceker."""
    results = []
    skip = 0
    while True:
        params = {
            "layout": f"Id,DisplayLabel,Status,{assign_field}",
            "size": PAGE_SIZE,
            "skip": skip,
            "meta": "TotalCount",
        }
        if filter_expr:
            params["filter"] = filter_expr
        data = ems_get(session, base_url, tenant, "Request", params)
        entities = data.get("entities", [])
        results.extend(entities)
        total = data.get("meta", {}).get("total_count")
        skip += len(entities)
        if not entities or (total is not None and skip >= total):
            break
    return results


def bulk_assign(session: requests.Session, base_url: str, tenant: str,
                request_ids: list, person_id: str, assign_field: str) -> None:
    url = f"{base_url}/rest/{tenant}/ems/bulk"
    done = 0
    for i in range(0, len(request_ids), BULK_CHUNK_SIZE):
        chunk = request_ids[i:i + BULK_CHUNK_SIZE]
        body = {
            "entities": [
                {"entity_type": "Request", "properties": {"Id": rid, assign_field: person_id}}
                for rid in chunk
            ],
            "operation": "UPDATE",
        }
        resp = session.post(url, data=json.dumps(body), timeout=120)
        if resp.status_code != 200:
            raise SystemExit(
                f"Toplu guncelleme basarisiz (HTTP {resp.status_code}): {resp.text[:1000]}\n"
                f"Su ana kadar {done} talep atandi."
            )
        result = resp.json()
        for ent in result.get("entity_result_list", []):
            status = ent.get("completion_status")
            rid = ent.get("entity", {}).get("properties", {}).get("Id")
            if status != "OK":
                print(f"  UYARI: Talep {rid} guncellenemedi: {status} - "
                      f"{json.dumps(ent.get('errorDetails', ''), ensure_ascii=False)[:200]}")
            else:
                done += 1
        print(f"Ilerleme: {done}/{len(request_ids)}")
    print(f"Tamamlandi: {done}/{len(request_ids)} talep atandi.")


def show_sample(session: requests.Session, base_url: str, tenant: str) -> None:
    """Alan adlarini dogrulamak icin tek bir talebi tum alanlariyla yazdirir."""
    data = ems_get(session, base_url, tenant, "Request",
                   {"layout": "FULL_LAYOUT", "size": 1})
    entities = data.get("entities", [])
    if not entities:
        print("Hic talep bulunamadi.")
        return
    print(json.dumps(entities[0]["properties"], indent=2, ensure_ascii=False))


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

    if not args.username:
        args.username = input("SMAX kullanici adi (e-posta): ").strip()
    password = os.environ.get("SMAX_PASSWORD") or getpass.getpass("SMAX sifresi: ")

    base_url = args.base_url.rstrip("/")
    session = build_session(args.insecure)
    login(session, base_url, args.tenant, args.username, password)
    print("Giris basarili.")

    if args.show_sample:
        show_sample(session, base_url, args.tenant)
        return

    assignee_email = args.assignee_email or args.username
    person_id = find_person_id(session, base_url, args.tenant, assignee_email)

    if args.filter_expr:
        filter_expr = args.filter_expr
    elif args.all:
        filter_expr = ""
    else:
        filter_expr = "(" + " or ".join(f"Status='{s}'" for s in DEFAULT_ACTIVE_STATUSES) + ")"

    print(f"Talepler cekiliyor... (filtre: {filter_expr or 'YOK - tum talepler'})")
    entities = fetch_requests(session, base_url, args.tenant, filter_expr, args.assign_field)
    print(f"Toplam {len(entities)} talep bulundu.")

    to_assign = []
    for e in entities:
        props = e["properties"]
        current = str(props.get(args.assign_field) or "")
        if current == person_id:
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

    bulk_assign(session, base_url, args.tenant, to_assign, person_id, args.assign_field)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\nIptal edildi.")
