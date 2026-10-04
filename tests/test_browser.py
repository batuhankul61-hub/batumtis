"""Tarayıcı modüllerinin testleri.

Gerçek sitelere bağlanılmaz: linkedin.com / tr.indeed.com / kariyer.net
istekleri Playwright ile yakalanıp aşağıdaki sahte sayfalarla yanıtlanır.
"""

import glob
import os
from pathlib import Path

import pytest
import yaml

pw = pytest.importorskip("playwright.sync_api")

from jobbot import __main__ as cli  # noqa: E402
from jobbot.browser import base  # noqa: E402
from jobbot.db import DB  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def _chromium():
    if os.environ.get("JOBBOT_CHROMIUM"):
        return os.environ["JOBBOT_CHROMIUM"]
    found = glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome")
    return found[0] if found else None


WIZARD_JS = """
<script>
let step = 0;
function show(i){ document.querySelectorAll('.step').forEach((s,k)=>s.style.display=k===i?'block':'none'); }
function next(){
  const req = [...document.querySelectorAll('.step')[step].querySelectorAll('[required]')];
  if (req.some(e => (e.type==='radio' ? !document.querySelector(`[name=${e.name}]:checked`) : !e.value))) {
    document.getElementById('err').innerText = 'Please enter a valid answer'; return; }
  document.getElementById('err').innerText = ''; step++; show(step); }
function submitApp(){ window.__submitted = (window.__submitted||0)+1;
  document.body.innerHTML = '<h1>Your application was sent to Acme!</h1>'; }
</script>
"""

LI_SEARCH = """<html><body><ul>
<li><a href="/jobs/view/111/?trk=x">Customer Support Specialist</a><div>Acme</div><div>Türkiye (Remote)</div></li>
<li><a href="/jobs/view/222/">Customer Support Agent</a><div>Weird Co</div><div>Remote</div></li>
<li><a href="/jobs/view/333/">Senior Customer Support Lead</a><div>Big</div><div>Remote</div></li>
</ul></body></html>"""

LI_JOB_OK = """<html><body><h1>Customer Support Specialist</h1><p>Acme · Remote</p>
<button aria-label="Easy Apply to Customer Support Specialist" onclick="document.getElementById('m').style.display='block'">Easy Apply</button>
<div id="m" role="dialog" style="display:none">
 <div id="err" role="alert"></div>
 <div class="step"><label for="ph">Mobile phone number</label><input id="ph" required>
   <button onclick="next()">Next</button></div>
 <div class="step" style="display:none">
   <label for="y">How many years of experience do you have with customer support?</label><input id="y" type="number" required>
   <fieldset><legend>Are you legally authorized to work in Türkiye?</legend>
     <label><input type="radio" name="auth" value="y" required>Yes</label>
     <label><input type="radio" name="auth" value="n">No</label></fieldset>
   <label for="en">English level</label><select id="en" required><option>Select an option</option><option>Native</option><option>Professional</option></select>
   <button onclick="next()">Review</button></div>
 <div class="step" style="display:none"><button onclick="submitApp()">Submit application</button></div>
 <button aria-label="Dismiss" onclick="document.getElementById('m').style.display='none'">x</button>
</div>""" + WIZARD_JS + "</body></html>"

LI_JOB_UNKNOWN = """<html><body><h1>Customer Support Agent</h1>
<button onclick="document.getElementById('m').style.display='block'">Easy Apply</button>
<div id="m" role="dialog" style="display:none"><div id="err"></div>
 <div class="step"><label for="c">What is your favourite colour?</label><input id="c" required>
 <button onclick="next()">Next</button></div>
 <button aria-label="Dismiss" onclick="window.__dismissed=1;document.getElementById('m').style.display='none'">x</button>
</div>""" + WIZARD_JS + "</body></html>"

KARIYER_SEARCH = """<html><body>
<div class="list-items"><a href="/is-ilani/acme-musteri-temsilcisi-uzaktan-555">Customer Support Temsilcisi</a><span>Acme AŞ</span></div>
<div class="list-items"><a href="/is-ilani/ofis-customer-support-666">Customer Support (Ofis)</a><span>Ofis AŞ</span></div>
</body></html>"""
KARIYER_JOB_REMOTE = """<html><body><h1>Customer Support Temsilcisi</h1><p>Çalışma şekli: Uzaktan</p>
<button onclick="window.__applied=1;document.body.innerHTML='<p>Başvurunuz alındı</p>'">Başvur</button></body></html>"""
KARIYER_JOB_OFFICE = """<html><body><h1>Customer Support</h1><p>Çalışma şekli: Ofisten, İstanbul</p>
<button>Başvur</button></body></html>"""

INDEED_SEARCH = """<html><body>
<div class="job_seen_beacon"><a data-jk="aaaaaaaaaaaaaaaa" href="/rc/clk?jk=aaaaaaaaaaaaaaaa">Customer Support Rep</a><span>Indy</span></div>
<div class="job_seen_beacon"><a data-jk="bbbbbbbbbbbbbbbb" href="/rc/clk?jk=bbbbbbbbbbbbbbbb">Customer Support External</a><span>Ext</span></div>
</body></html>"""
INDEED_JOB_A = """<html><body><h1>Customer Support Rep</h1><p>Remote</p>
<button id="indeedApplyButton" onclick="location.href='/apply/a'">Hemen başvur</button></body></html>"""
INDEED_APPLY = """<html><body><div id="err"></div>
<div class="step"><label for="n">Ad Soyad</label><input id="n" value="Ad Soyad">
 <label for="t">Telefon</label><input id="t" required><button onclick="next()">Devam</button></div>
<div class="step" style="display:none"><button onclick="submitApp()">Başvurunu gönder</button></div>
""" + WIZARD_JS.replace("Your application was sent to Acme!", "Başvurunuz gönderildi") + "</body></html>"
INDEED_JOB_B = """<html><body><h1>Customer Support External</h1><p>Remote</p>
<a href="https://ext.example.com/apply">Şirket sitesinde başvur</a></body></html>"""


def _route(route):
    url = route.request.url
    pages = {
        "linkedin.com/jobs/search": LI_SEARCH,
        "linkedin.com/jobs/view/111": LI_JOB_OK,
        "linkedin.com/jobs/view/222": LI_JOB_UNKNOWN,
        "kariyer.net/is-ilanlari": KARIYER_SEARCH,
        "kariyer.net/is-ilani/acme": KARIYER_JOB_REMOTE,
        "kariyer.net/is-ilani/ofis": KARIYER_JOB_OFFICE,
        "indeed.com/jobs": INDEED_SEARCH,
        "indeed.com/viewjob?jk=aaaa": INDEED_JOB_A,
        "indeed.com/viewjob?jk=bbbb": INDEED_JOB_B,
        "indeed.com/apply/a": INDEED_APPLY,
    }
    for key, body in pages.items():
        if key in url:
            # 2. sayfa istekleri boş dönsün
            if ("start=25" in url or "start=10" in url or "cp=2" in url):
                body = "<html><body></body></html>"
            return route.fulfill(status=200, content_type="text/html; charset=utf-8", body=body)
    return route.fulfill(status=404, body="not found")


@pytest.fixture
def setup(tmp_path, monkeypatch):
    exe = _chromium()
    if not exe and not os.environ.get("JOBBOT_TEST_DEFAULT_BROWSER"):
        pytest.skip("Chromium bulunamadı")
    c = yaml.safe_load((ROOT / "config.example.yaml").read_text(encoding="utf-8"))
    c["profile"]["cv_path"] = ""
    c["cover_letter_template"] = str(ROOT / "templates/cover_letter_en.txt")
    c["database"] = str(tmp_path / "t.db")
    c["export"] = {"html": str(tmp_path / "o.html"), "csv": str(tmp_path / "o.csv")}
    c["filters"]["keywords"] = ["customer support"]
    c["browser"].update(profile_dir=str(tmp_path / "prof"), headless=True,
                        executable_path=exe, max_pages=2, delay_seconds=[0, 0],
                        search_terms=["customer support"])
    c["answers"]["years of experience"] = "3"

    real_open = base.open_context

    def open_with_routes(cfg, p, headless=None):
        ctx = real_open(cfg, p, headless=True)
        ctx.route("**/*", _route)
        return ctx

    monkeypatch.setattr(base, "open_context", open_with_routes)
    monkeypatch.setattr(cli.sources, "fetch_all", lambda names, log=print: [])
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(c, allow_unicode=True), encoding="utf-8")
    return c, str(path)


def statuses(c):
    db = DB(c["database"])
    return {r["key"]: (r["status"], r["note"]) for r in db.conn.execute("SELECT * FROM jobs")}


def test_dry_run_submits_nothing(setup, capsys):
    c, path = setup
    cli.main(["-c", path, "run"])
    out = capsys.readouterr().out
    st = statuses(c)
    assert "linkedin:333" not in st                      # "senior" elendi
    assert st["linkedin:111"][0] == "new"                 # deneme: gönderilmedi
    assert "(deneme) başvurulabilir: Customer Support Specialist" in out
    assert st["linkedin:222"][0] == "manual"
    assert "favourite colour" in st["linkedin:222"][1]
    assert st["kariyer:555"][0] == "new"                  # deneme modunda Başvur'a basılmaz
    assert st["kariyer:666"][0] == "skipped"              # uzaktan değil
    assert st["indeed:aaaaaaaaaaaaaaaa"][0] == "new"
    assert st["indeed:bbbbbbbbbbbbbbbb"][0] == "manual"


def test_send_applies(setup, capsys):
    c, path = setup
    cli.main(["-c", path, "run", "--send"])
    st = statuses(c)
    assert st["linkedin:111"][0] == "applied"
    assert st["linkedin:222"][0] == "manual"
    assert st["kariyer:555"][0] == "applied"
    assert st["indeed:aaaaaaaaaaaaaaaa"][0] == "applied"
    assert st["indeed:bbbbbbbbbbbbbbbb"][0] == "manual"

    # İkinci çalıştırmada tekrar başvurmaz
    cli.main(["-c", path, "run", "--send"])
    out = capsys.readouterr().out
    assert out.count("applied: Customer Support Specialist") == 1

    html = Path(c["export"]["html"]).read_text(encoding="utf-8")
    assert "Customer Support Agent" in html and "favourite colour" in html
