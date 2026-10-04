# batumtis — Uzaktan İş Başvuru Botu

Herkese açık uzaktan iş sitelerinden ilanları çeker, profiline göre puanlar ve:

- **İlanda e-posta adresi varsa** → CV'n ekli, kişiselleştirilmiş ön yazıyla **otomatik e-posta başvurusu** gönderir.
- **E-posta yoksa** (başvuru formu varsa) → ilanı, hazır ön yazısıyla birlikte `basvurular.html` listesine koyar; linke tıklayıp yapıştırırsın.
- Aynı ilana **iki kez başvurmaz**, günlük limit ve başvurular arası bekleme uygular.

Kaynaklar: Remotive, RemoteOK, Arbeitnow (yalnızca uzaktan), Jobicy, Himalayas.

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

## Neden LinkedIn / Kariyer.net / Indeed yok?
Bu siteler otomatik başvuru botlarını kullanım şartlarıyla yasaklıyor ve hesabı kapatabiliyor;
ayrıca CAPTCHA ile engelliyorlar. Bot bu yüzden yalnızca açık API sunan uzaktan iş sitelerini kullanır.

## Test
```bash
python -m pytest -q
```
