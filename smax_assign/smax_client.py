"""SMAX (Service Anywhere) REST API icin ortak istemci fonksiyonlari.

Hem assign_requests.py hem route_requests.py bu modulu kullanir.
"""

import json
import os
import getpass

import requests

PAGE_SIZE = 250
BULK_CHUNK_SIZE = 20


def build_session(insecure: bool = False) -> requests.Session:
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "Accept": "application/json"})
    if insecure:
        s.verify = False
        requests.packages.urllib3.disable_warnings()  # type: ignore[attr-defined]
    return s


def prompt_credentials(username: str = None):
    """Kullanici adi ve sifreyi ortam degiskeni / etkilesimli soru ile alir."""
    username = username or os.environ.get("SMAX_USERNAME")
    if not username:
        username = input("SMAX kullanici adi (e-posta): ").strip()
    password = os.environ.get("SMAX_PASSWORD") or getpass.getpass("SMAX sifresi: ")
    return username, password


def login(session: requests.Session, base_url: str, tenant: str,
          username: str, password: str) -> None:
    """SMAX kimlik dogrulamasi: token alir ve LWSSO cerezine yazar."""
    url = f"{base_url}/auth/authentication-endpoint/authenticate/login?TENANTID={tenant}"
    resp = session.post(url, json={"login": username, "password": password}, timeout=60)
    if resp.status_code != 200 or not resp.text.strip():
        raise SystemExit(
            f"Giris basarisiz (HTTP {resp.status_code}). Kullanici adi/sifreyi kontrol edin.\n"
            f"{resp.text[:500]}"
        )
    session.cookies.set("LWSSO_COOKIE_KEY", resp.text.strip())
    session.cookies.set("TENANTID", tenant)


def ems_get(session: requests.Session, base_url: str, tenant: str,
            entity: str, params: dict) -> dict:
    url = f"{base_url}/rest/{tenant}/ems/{entity}"
    resp = session.get(url, params=params, timeout=120)
    if resp.status_code != 200:
        raise SystemExit(f"EMS sorgusu basarisiz (HTTP {resp.status_code}): {resp.text[:500]}")
    return resp.json()


def fetch_all(session: requests.Session, base_url: str, tenant: str,
              entity: str, layout: str, filter_expr: str = "") -> list:
    """Filtreye uyan tum kayitlari sayfa sayfa ceker."""
    results = []
    skip = 0
    while True:
        params = {"layout": layout, "size": PAGE_SIZE, "skip": skip, "meta": "TotalCount"}
        if filter_expr:
            params["filter"] = filter_expr
        data = ems_get(session, base_url, tenant, entity, params)
        entities = data.get("entities", [])
        results.extend(entities)
        total = data.get("meta", {}).get("total_count")
        skip += len(entities)
        if not entities or (total is not None and skip >= total):
            break
    return results


def find_person_id(session: requests.Session, base_url: str, tenant: str, email: str) -> str:
    """E-posta (veya Upn) uzerinden Person kaydinin Id'sini bulur."""
    for field in ("Email", "Upn"):
        data = ems_get(session, base_url, tenant, "Person",
                       {"filter": f"{field}='{email}'", "layout": "Id,Name,Email", "size": 5})
        entities = data.get("entities", [])
        if entities:
            props = entities[0]["properties"]
            print(f"Kisi bulundu: Id={props['Id']} Name={props.get('Name')} Email={props.get('Email')}")
            return str(props["Id"])
    raise SystemExit(f"'{email}' icin Person kaydi bulunamadi.")


def bulk_update(session: requests.Session, base_url: str, tenant: str,
                entity_type: str, updates: list) -> int:
    """updates: [{'Id': '123', 'AlanAdi': 'deger'}, ...] seklinde property sozlukleri.

    Basariyla guncellenen kayit sayisini dondurur.
    """
    url = f"{base_url}/rest/{tenant}/ems/bulk"
    done = 0
    for i in range(0, len(updates), BULK_CHUNK_SIZE):
        chunk = updates[i:i + BULK_CHUNK_SIZE]
        body = {
            "entities": [{"entity_type": entity_type, "properties": props} for props in chunk],
            "operation": "UPDATE",
        }
        resp = session.post(url, data=json.dumps(body), timeout=120)
        if resp.status_code != 200:
            raise SystemExit(
                f"Toplu guncelleme basarisiz (HTTP {resp.status_code}): {resp.text[:1000]}\n"
                f"Su ana kadar {done} kayit guncellendi."
            )
        for ent in resp.json().get("entity_result_list", []):
            rid = ent.get("entity", {}).get("properties", {}).get("Id")
            if ent.get("completion_status") != "OK":
                print(f"  UYARI: {rid} guncellenemedi: {ent.get('completion_status')} - "
                      f"{json.dumps(ent.get('errorDetails', ''), ensure_ascii=False)[:200]}")
            else:
                done += 1
        print(f"Ilerleme: {done}/{len(updates)}")
    return done


def show_sample(session: requests.Session, base_url: str, tenant: str,
                entity: str = "Request") -> None:
    """Alan adlarini dogrulamak icin tek bir kaydi tum alanlariyla yazdirir."""
    data = ems_get(session, base_url, tenant, entity, {"layout": "FULL_LAYOUT", "size": 1})
    entities = data.get("entities", [])
    if not entities:
        print(f"Hic {entity} kaydi bulunamadi.")
        return
    print(json.dumps(entities[0]["properties"], indent=2, ensure_ascii=False))
