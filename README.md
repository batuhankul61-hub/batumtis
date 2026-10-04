# batumtis — Uzaktan İş Başvuru Botu

Herkese açık uzaktan iş sitelerinden ilanları çeker, profiline göre puanlar ve:

- **İlanda e-posta adresi varsa** → CV'n ekli, kişiselleştirilmiş ön yazıyla **otomatik e-posta başvurusu** gönderir.
- **E-posta yoksa** (başvuru formu varsa) → ilanı, hazır ön yazısıyla birlikte `basvurular.html` listesine koyar; linke tıklayıp yapıştırırsın.
- Aynı ilana **iki kez başvurmaz**, günlük limit ve başvurular arası bekleme uygular.

Kaynaklar:
- **E-posta ile:** Remotive, RemoteOK, Arbeitnow (yalnızca uzaktan), Jobicy, Himalayas
- **Tarayıcı ile:** LinkedIn (Kolay Başvuru), Indeed (Indeed üzerinden başvuru), Kariyer.net

Tarayıcı ile çalışan sitelerde program sitede uzaktan ilanları arar, ilanı açar, başvuru
formundaki soruları `config.yaml` içindeki `answers` bölümüne göre doldurur ve gönderir.
Cevabını bilmediği zorunlu bir soru çıkarsa **yanlış cevap uydurmaz**; başvuruyu yarıda
bırakır ve ilanı, eksik soruyla birlikte `basvurular.html` listesine ekler.

## Kurulum

```bash
pip install -r requirements.txt
cp config.example.yaml config.yaml   # sonra kendi bilgilerini gir
cp /yol/cv.pdf cv.pdf
```

`config.yaml` içinde düzenlemen gerekenler:
- `profile`: ad, e-posta, telefon, kısa tanıtım (`summary`), CV yolu
- `filters.keywords`: aradığın işler (ör. `customer support`, `python`, `translator`)
- `filters.exclude_keywords`: istemediklerin (ör. `senior`)
- `filters.allowed_locations`: başvurabileceğin bölgeler

### Gmail ile gönderim
1. Google hesabında 2 adımlı doğrulamayı aç.
2. https://myaccount.google.com/apppasswords adresinden bir **uygulama şifresi** oluştur.
3. Şifreyi dosyaya değil, ortam değişkenine yaz:
   ```bash
   export JOBBOT_SMTP_PASSWORD="xxxx xxxx xxxx xxxx"
   ```

### LinkedIn / Indeed / Kariyer.net
```bash
pip install playwright && playwright install chromium
python -m jobbot login linkedin    # açılan tarayıcıda giriş yap, Enter'a bas
python -m jobbot login indeed
python -m jobbot login kariyer
```
Şifren programa verilmez; oturum `browser_profile/` klasöründe kalır.
CAPTCHA / güvenlik doğrulaması çıkarsa program durur ve tarayıcıda çözmeni bekler.
LinkedIn ve Indeed'de profilinde CV'nin yüklü olması gerekir.

`config.yaml` içindeki `answers` bölümünü kendine göre doldur (telefon, deneyim yılı,
maaş beklentisi, İngilizce seviyesi vb.). İlk denemeden sonra `basvurular.html`'deki
"doldurulamayan alanlar" notlarına bakıp yeni cevaplar ekledikçe otomatik başvuru oranı artar.

## Kullanım

```bash
python -m jobbot run            # deneme: ilanları çeker, kime ne gideceğini gösterir, GÖNDERMEZ
python -m jobbot run --send     # gerçekten başvurur
python -m jobbot status         # özet
python -m jobbot list           # bekleyen ilanlar
python -m jobbot mark remotive:123 applied   # elle başvurduğunu işaretle
```

İlk seferde mutlaka `--send` olmadan çalıştır ve listeyi kontrol et.
Her gün otomatik çalışması için (Linux/macOS) `crontab -e`:
```
0 10 * * * cd /yol/batumtis && JOBBOT_SMTP_PASSWORD=... python3 -m jobbot run --send >> jobbot.log 2>&1
```

## ⚠️ Riskler
- LinkedIn ve Indeed kullanım şartları otomatik başvuruyu yasaklar; hesabın kısıtlanabilir
  veya kapatılabilir. Riski azaltmak için günlük limitleri (`browser.daily_limit`) düşük tut,
  bekleme sürelerini kısaltma.
- Bu sitelerin sayfa tasarımı sık değişir. Bir şey çalışmazsa `jobbot/browser/sites.py`
  içindeki düğme adı listelerinin güncellenmesi gerekebilir.
- Program gerçek sitelerde test edilmedi (yalnızca sahte sayfalarla). İlk çalıştırmayı
  mutlaka `--send` olmadan ve görünür tarayıcıyla yapıp ne yaptığını izle.
- `python -m jobbot run --no-browser` yalnızca e-posta kaynaklarını kullanır.

## Test
```bash
python -m pytest -q
```
