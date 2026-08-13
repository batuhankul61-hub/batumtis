"""Talep yonlendirme kural motoru (saf mantik — ag baglantisi gerektirmez).

Is kurali ornegi:
    Sercan Bey'in sorumlulugundaki lokasyonlarda KLIMA talepleri
    Proasist'e yonlendirilmez; Ulusal'a yonlendirilir.

Kurallar routing_rules.json dosyasindan okunur, boylece yeni bir kural
eklemek icin kod degistirmek gerekmez.
"""

import json
from dataclasses import dataclass, field

# Turkce karakterleri ASCII'ye indirger; "KLİMA", "Klima", "klima" hepsi eslesir.
_TR_MAP = str.maketrans({
    "ı": "i", "İ": "i", "I": "i",
    "ş": "s", "Ş": "s",
    "ğ": "g", "Ğ": "g",
    "ü": "u", "Ü": "u",
    "ö": "o", "Ö": "o",
    "ç": "c", "Ç": "c",
})


def norm(value) -> str:
    """Karsilastirma icin metni normalize eder (Turkce duyarli, kucuk harf)."""
    return str(value or "").translate(_TR_MAP).lower().strip()


def is_placeholder(value) -> bool:
    """routing_rules.json'daki '<<...>>' sablon degerlerini (ve bosu) tespit eder."""
    text = str(value or "").strip()
    return not text or (text.startswith("<<") and text.endswith(">>"))


@dataclass
class Decision:
    """Bir talep icin kural motorunun karari."""
    action: str            # "no_match" | "already_correct" | "reroute" | "route"
    request_id: str = ""
    label: str = ""
    rule_name: str = ""
    target_vendor: str = ""
    current_vendor: str = ""
    field: str = ""
    value: str = ""
    reason: str = ""

    @property
    def needs_update(self) -> bool:
        return self.action in ("reroute", "route")


@dataclass
class RulesConfig:
    vendors: dict = field(default_factory=dict)
    areas: dict = field(default_factory=dict)
    rules: list = field(default_factory=list)

    @classmethod
    def load(cls, path: str) -> "RulesConfig":
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return cls(
            vendors=data.get("vendors", {}),
            areas=data.get("areas", {}),
            rules=data.get("rules", []),
        )

    def validate(self) -> list:
        """Yapilandirmadaki eksikleri (doldurulmamis Id'ler, sablon degerleri) listeler."""
        problems = []
        for name, v in self.vendors.items():
            if is_placeholder(v.get("field")):
                problems.append(
                    f"Tedarikci '{name}': 'field' doldurulmamis — yonlendirme alaninin "
                    f"SMAX'taki adini yazin (ornegin ExpertGroup)."
                )
            if is_placeholder(v.get("value")):
                problems.append(
                    f"Tedarikci '{name}': 'value' doldurulmamis — SMAX'taki grup/tedarikci "
                    f"Id'sini yazin."
                )
        for name, a in self.areas.items():
            values = [v for v in a.get("values", []) if not is_placeholder(v)]
            if not values:
                problems.append(
                    f"Sorumluluk alani '{name}': 'values' doldurulmamis — lokasyon listesini girin."
                )
        for r in self.rules:
            target = r.get("then", {}).get("route_to")
            if target and target not in self.vendors:
                problems.append(f"Kural '{r.get('name')}': '{target}' tedarikcisi tanimli degil.")
            area = r.get("when", {}).get("area")
            if area and area not in self.areas:
                problems.append(f"Kural '{r.get('name')}': '{area}' sorumluluk alani tanimli degil.")
        return problems


def _prop(props: dict, name: str) -> str:
    """Bir alanin degerini duz metne cevirir (SMAX bazen sozluk/liste dondurur)."""
    value = props.get(name)
    if isinstance(value, dict):
        value = value.get("DisplayLabel") or value.get("Name") or value.get("Id") or ""
    elif isinstance(value, list):
        value = " ".join(str(_prop({"x": v}, "x")) for v in value)
    return str(value or "")


def matches_area(props: dict, area: dict) -> bool:
    """Talep, verilen sorumluluk alanindaki bir lokasyona ait mi?"""
    values = [norm(v) for v in area.get("values", []) if not is_placeholder(v)]
    if not values:
        return False
    fields = area.get("match_fields") or [area.get("match_field", "Location")]
    for f in fields:
        haystack = norm(_prop(props, f))
        if not haystack:
            continue
        for v in values:
            # Tam eslesme veya kod/isim icerme (ornegin "MAGAZA-001 - Ankara")
            if haystack == v or v in haystack:
                return True
    return False


def matches_keywords(props: dict, spec: dict) -> bool:
    """Belirtilen alanlarin herhangi birinde anahtar kelimelerden biri geciyor mu?"""
    keywords = [norm(k) for k in spec.get("keywords", []) if str(k).strip()]
    if not keywords:
        return False
    blob = " ".join(norm(_prop(props, f)) for f in spec.get("fields", []))
    return any(k in blob for k in keywords)


def current_vendor_name(props: dict, config: RulesConfig) -> str:
    """Talebin su an hangi tedarikciye yonlendirildigini (varsa) bulur."""
    for name, vendor in config.vendors.items():
        field_name = vendor.get("field")
        if is_placeholder(field_name):
            continue
        current = norm(_prop(props, field_name))
        if not current:
            continue
        if not is_placeholder(vendor.get("value")) and current == norm(vendor["value"]):
            return name
        for alias in vendor.get("aliases", []) + [name]:
            if norm(alias) and norm(alias) in current:
                return name
    return ""


def evaluate(props: dict, config: RulesConfig) -> Decision:
    """Bir talebi kurallara gore degerlendirir ve karari dondurur."""
    request_id = str(props.get("Id", ""))
    label = _prop(props, "DisplayLabel")
    current = current_vendor_name(props, config)

    for rule in config.rules:
        when = rule.get("when", {})

        area_name = when.get("area")
        if area_name:
            area = config.areas.get(area_name, {})
            if not matches_area(props, area):
                continue

        keyword_spec = when.get("any_keyword_in")
        if keyword_spec and not matches_keywords(props, keyword_spec):
            continue

        then = rule.get("then", {})
        target = then.get("route_to")
        if not target:
            continue
        vendor = config.vendors.get(target, {})

        if current == target:
            return Decision(
                action="already_correct", request_id=request_id, label=label,
                rule_name=rule.get("name", ""), target_vendor=target, current_vendor=current,
                reason=f"Zaten {target} uzerinde.",
            )

        forbidden = then.get("forbid", [])
        if current and current in forbidden:
            reason = (f"{rule.get('name')}: {current} yerine {target} olmali "
                      f"({current} bu alanda klima islerine bakmiyor).")
        elif current:
            reason = f"{rule.get('name')}: {current} -> {target}."
        else:
            reason = f"{rule.get('name')}: yonlendirme yok -> {target}."

        return Decision(
            action="reroute" if current else "route",
            request_id=request_id, label=label, rule_name=rule.get("name", ""),
            target_vendor=target, current_vendor=current,
            field=vendor.get("field", ""), value=str(vendor.get("value", "")),
            reason=reason,
        )

    return Decision(action="no_match", request_id=request_id, label=label,
                    current_vendor=current, reason="Hicbir kural eslesmedi.")


def evaluate_all(entities: list, config: RulesConfig) -> list:
    """EMS'ten gelen entity listesini degerlendirir."""
    return [evaluate(e.get("properties", e), config) for e in entities]
