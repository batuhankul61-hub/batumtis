"""Başvuru formlarını config'teki cevaplarla dolduran genel form doldurucu.

Site bağımsızdır: alanların etiketini (label / aria-label / placeholder /
fieldset legend) okur ve `answers` sözlüğündeki kalıplarla eşleştirir.
Doldurulamayan zorunlu alan kalırsa listesini döndürür; çağıran taraf o
başvuruyu yarıda bırakıp "elle başvurulacak" olarak işaretler.
"""

from __future__ import annotations

import re

# Tarayıcıda çalışır: kapsayıcıdaki görünür form alanlarını etiketleriyle döndürür.
_COLLECT_JS = r"""
(root) => {
  const visible = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
  const clean = s => (s || '').replace(/\s+/g, ' ').trim();
  const labelOf = el => {
    if (el.getAttribute('aria-label')) return el.getAttribute('aria-label');
    const lb = el.getAttribute('aria-labelledby');
    if (lb) { const t = lb.split(' ').map(i => document.getElementById(i))
                 .filter(Boolean).map(e => e.innerText).join(' '); if (t) return t; }
    if (el.id) { const l = root.ownerDocument.querySelector(`label[for="${CSS.escape(el.id)}"]`);
                 if (l) return l.innerText; }
    const wrap = el.closest('label'); if (wrap) return wrap.innerText;
    return el.getAttribute('placeholder') || el.name || '';
  };
  // Önceki adımlardan kalan işaretleri temizle (aynı id iki elemana gitmesin)
  root.ownerDocument.querySelectorAll('[data-jobbot]').forEach(e => e.removeAttribute('data-jobbot'));
  const out = []; const seenRadio = new Set(); let n = 0;
  for (const el of root.querySelectorAll('input, select, textarea')) {
    const type = (el.getAttribute('type') || el.tagName).toLowerCase();
    if (['hidden', 'submit', 'button', 'reset', 'image'].includes(type)) continue;
    if (type !== 'file' && !visible(el)) continue;
    if (el.disabled || el.readOnly) continue;
    const id = 'jb' + (n++); el.setAttribute('data-jobbot', id);
    const fs = el.closest('fieldset');
    const legend = fs && fs.querySelector('legend') ? fs.querySelector('legend').innerText : '';
    let label = clean(labelOf(el));
    let required = el.required || el.getAttribute('aria-required') === 'true' || /\*\s*$/.test(label);
    if (type === 'radio') {
      const group = el.name || legend;
      if (seenRadio.has(group)) continue; seenRadio.add(group);
      const radios = fs ? [...fs.querySelectorAll('input[type=radio]')]
                        : [...root.querySelectorAll(`input[type=radio][name="${CSS.escape(el.name)}"]`)];
      radios.forEach((r, i) => r.setAttribute('data-jobbot', id + '_' + i));
      out.push({id, type, label: clean(legend) || label,
                required: required || radios.some(r => r.required) || !!(fs && fs.querySelector('[aria-required=true], [required]')),
                filled: radios.some(r => r.checked),
                options: radios.map(r => clean(labelOf(r)))});
      continue;
    }
    if (legend && !label) label = clean(legend);
    const opts = el.tagName === 'SELECT' ? [...el.options].map(o => clean(o.text)) : [];
    let filled;
    if (type === 'checkbox') filled = el.checked;
    else if (el.tagName === 'SELECT') filled = el.selectedIndex > 0 ||
         (el.selectedIndex === 0 && !/select|seç|choose|--/i.test(opts[0] || ''));
    else if (type === 'file') filled = el.files.length > 0;
    else filled = clean(el.value) !== '';
    out.push({id, type, label, required, filled, options: opts});
  }
  return out;
}
"""


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower()).strip(" *:")


def find_answer(label: str, answers: dict) -> str | None:
    """answers: {"phone|telefon": "+90...", ...}  (sıra önemlidir, ilk eşleşen kazanır)"""
    lab = _norm(label)
    if not lab:
        return None
    for pattern, value in answers.items():
        for alt in str(pattern).split("|"):
            alt = alt.strip().lower()
            if alt and alt in lab:
                return str(value)
    return None


def _pick_option(options: list[str], wanted: str) -> int | None:
    w = _norm(wanted)
    norm = [_norm(o) for o in options]
    for i, o in enumerate(norm):
        if o == w:
            return i
    for i, o in enumerate(norm):
        if o and (w in o or o in w):
            return i
    return None


def fill_form(page, root_selector: str, cfg: dict, cover_letter: str = "") -> list[str]:
    """Formu doldurur. Doldurulamayan zorunlu alanların etiketlerini döndürür."""
    answers = dict(cfg.get("answers") or {})
    profile = cfg.get("profile", {})
    root = page.locator(root_selector).first
    fields = root.evaluate(_COLLECT_JS)
    missing: list[str] = []

    for f in fields:
        if f["filled"]:
            continue
        loc = page.locator(f'[data-jobbot="{f["id"]}"]').first
        label, ftype = f["label"], f["type"]
        lab = _norm(label)
        value = find_answer(label, answers)
        ok = False
        try:
            if ftype == "file":
                cv = profile.get("cv_path")
                if cv and re.search(r"resume|cv|özgeçmiş|ozgecmis|upload|yükle", lab or "cv"):
                    loc.set_input_files(cv)
                    ok = True
            elif ftype == "radio":
                idx = _pick_option(f["options"], value) if value else None
                if idx is not None:
                    page.locator(f'[data-jobbot="{f["id"]}_{idx}"]').check(force=True)
                    ok = True
            elif ftype == "checkbox":
                if value and _norm(value) in ("yes", "evet", "true", "1"):
                    loc.check(force=True)
                    ok = True
            elif ftype == "select":
                idx = _pick_option(f["options"], value) if value else None
                if idx is not None:
                    loc.select_option(index=idx)
                    ok = True
            elif ftype == "textarea" and value is None and cover_letter and re.search(
                r"cover|letter|ön yazı|on yazi|message|mesaj|why|neden", lab
            ):
                loc.fill(cover_letter)
                ok = True
            elif value is not None:
                loc.fill(value)
                ok = True
        except Exception:
            ok = False
        if not ok and f["required"]:
            missing.append(label or f"({ftype})")
    return missing
