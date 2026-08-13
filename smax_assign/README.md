# SMAX Talep Otomasyonu

FLO SMAX (Service Anywhere — `https://flodesk.flo.com.tr/saw/...`) üzerindeki
talepleri REST API ile toplu yöneten iki araç:

| Script | Ne yapar |
|---|---|
| `assign_requests.py` | Talepleri toplu olarak bir **kişiye** atar |
| `route_requests.py` | Talepleri iş kurallarına göre doğru **tedarikçiye** yönlendirir |

## Kurulum

```bash
pip install -r requirements.txt
```

> Script'i SMAX'a erişimi olan bir makineden (şirket ağı / VPN) çalıştırın.

Ortam değişkenleri: `SMAX_BASE_URL`, `SMAX_TENANT`, `SMAX_USERNAME`, `SMAX_PASSWORD`.
Şifrenizi asla dosyaya/koda yazmayın.

---

## 1. Toplu atama — `assign_requests.py`

```bash
# Alan adını doğrulayın (AssignedPerson mı, OwnedByPerson mı?)
python assign_requests.py --username kullanici@flo.com.tr --show-sample

# Kuru çalıştırma — hiçbir şey değiştirmez
python assign_requests.py --username kullanici@flo.com.tr --dry-run

# Gerçek atama
python assign_requests.py --username kullanici@flo.com.tr --yes
```

Varsayılan olarak yalnızca **açık** talepleri hedefler
(Ready / InProgress / Pending / Suspended). Kapalılar dahil hepsi için `--all`.
Başka birine atamak için `--assignee-email baska@flo.com.tr`.

---

## 2. Kurallı yönlendirme — `route_requests.py`

İş kuralları `routing_rules.json` dosyasında tutulur; **yeni kural eklemek için
kod değiştirmek gerekmez.**

### Tanımlı kural

> Sercan Bey'in sorumluluğundaki lokasyonlarda **klima** talepleri
> Proasist'e yönlendirilmez — **Ulusal**'a yönlendirilir.

Script bu kurala uyan talepleri bulur, yanlışlıkla Proasist'e gitmiş olanları
tespit eder ve Ulusal'a çevirir. Aynı lokasyondaki klima **dışı** işler ve
başka lokasyonlardaki klima işleri dokunulmadan bırakılır.

### Kullanım

```bash
# 1) Alan adlarını keşfet — routing_rules.json'ı doldurmak için
python route_requests.py --show-sample

# 2) Kuralları uygula ama değiştirme; CSV rapor da al
python route_requests.py --dry-run --report rapor.csv

# 3) Gerçek yönlendirme
python route_requests.py --yes
```

### `routing_rules.json` nasıl doldurulur

Dosyadaki `<<...>>` işaretli yerler ortamınıza özgü değerlerle doldurulmalıdır.
Doldurulmadan gerçek güncelleme yapılmaz; script hangi alanların eksik
olduğunu söyler.

```jsonc
"vendors": {
  "Proasist": { "field": "ExpertGroup", "value": "<grup Id>" },
  "Ulusal":   { "field": "ExpertGroup", "value": "<grup Id>" }
},
"areas": {
  "Sercan": {
    "match_fields": ["Location"],
    "values": ["MAGAZA-001", "Ankara Kentpark"]   // Sercan Bey'in lokasyonları
  }
}
```

- **`field`** — yönlendirmenin yazıldığı SMAX alanı (çoğu kurulumda
  `ExpertGroup`; `--show-sample` çıktısından doğrulayın).
- **`value`** — o tedarikçinin SMAX'taki grup/tedarikçi Id'si.
- **`values`** (areas) — mağaza kodu veya adı yazılabilir; parçalı eşleşme
  yapılır, yani `MAGAZA-001` değeri `MAGAZA-001 - Ankara` kaydını da yakalar.

Anahtar kelimeler Türkçe karakterden bağımsız eşleşir: `KLİMA`, `Klima`,
`klima` hepsi aynıdır.

### Yeni kural eklemek

`rules` dizisine bir nesne ekleyin — örneğin başka bir alanda asansör işleri:

```jsonc
{
  "name": "X alani - asansor -> Y firmasi",
  "when": {
    "area": "X",
    "any_keyword_in": { "fields": ["DisplayLabel", "Description"],
                        "keywords": ["asansor", "yürüyen merdiven"] }
  },
  "then": { "route_to": "Y", "forbid": ["Proasist"] }
}
```

Kurallar sırayla değerlendirilir; **ilk eşleşen** kural uygulanır.

---

## Testler

Kural motoru ağ bağlantısı olmadan test edilebilir:

```bash
python -m unittest test_routing -v
```

## Faydalı seçenekler (her iki script)

| Seçenek | Açıklama |
|---|---|
| `--dry-run` | Sadece ne yapılacağını gösterir |
| `--show-sample` | Bir talebi tüm alanlarıyla yazdırır |
| `--filter "..."` | Özel EMS filtresi, örn. `"Status='RequestStatusReady'"` |
| `--all` | Statü filtresi olmadan tüm talepler |
| `--report dosya.csv` | Karar raporu (yalnızca `route_requests.py`) |
| `--insecure` | İç ağ TLS sertifika hatasında doğrulamayı kapatır |
