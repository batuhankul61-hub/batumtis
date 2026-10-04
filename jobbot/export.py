"""Elle başvurulması gereken ilanları HTML/CSV olarak dışa aktarır."""

from __future__ import annotations

import csv
import html

from .mailer import render_letter


def export_csv(rows, path: str):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["puan", "durum", "baslik", "sirket", "konum", "maas", "link", "kaynak"])
        for job, row in rows:
            w.writerow([row["score"], row["status"], job.title, job.company,
                        job.location, job.salary, job.url, job.source])


def export_html(rows, path: str, cfg: dict):
    items = []
    for job, row in rows:
        _, letter = render_letter(job, cfg)
        e = html.escape
        items.append(f"""
<article>
  <h2><a href="{e(job.url)}" target="_blank" rel="noopener">{e(job.title)}</a></h2>
  <p class="meta">{e(job.company)} · {e(job.location or '-')} · {e(job.salary or 'maaş belirtilmemiş')}
     · puan {row['score']} · {e(job.source)} · <b>{e(row['status'])}</b>
     {('<br><small>' + e(row['note']) + '</small>') if row['note'] else ''}</p>
  <details><summary>Ön yazı (kopyala)</summary><textarea readonly>{e(letter)}</textarea></details>
</article>""")
    page = f"""<!doctype html>
<html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Başvuru Listesi</title>
<style>
body{{font-family:system-ui,sans-serif;max-width:860px;margin:0 auto;padding:16px;background:#fafafa;color:#222}}
article{{background:#fff;border:1px solid #ddd;border-radius:8px;padding:12px 16px;margin:12px 0}}
h2{{font-size:1.1rem;margin:0 0 4px}} .meta{{color:#666;font-size:.9rem;margin:0 0 8px}}
textarea{{width:100%;min-height:220px;box-sizing:border-box;font:inherit}}
</style></head><body>
<h1>Elle başvurulacak ilanlar ({len(rows)})</h1>
<p>Bu ilanların e-posta adresi yok; linke tıklayıp ön yazıyı yapıştırarak başvurun.
Başvurduktan sonra: <code>python -m jobbot mark &lt;anahtar&gt; applied</code></p>
{''.join(items)}
</body></html>"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(page)
