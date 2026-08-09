# SMAX Talep Atama Otomasyonu

FLO SMAX (Service Anywhere — `https://flodesk.flo.com.tr/saw/...`) üzerindeki
talepleri (Request) REST API ile toplu olarak istediğiniz kişiye atar.

## Kurulum

```bash
pip install -r requirements.txt
```

> Not: Script'i SMAX'a erişimi olan bir makineden (şirket ağı / VPN) çalıştırın.

## Kullanım

### 1. Önce alan adını doğrulayın (önerilir)

SMAX ortamına göre atama alanı `AssignedPerson` veya `OwnedByPerson` olabilir.
Tek bir talebi tüm alanlarıyla yazdırıp doğru alanı görün:

```bash
python assign_requests.py --username kullanici@flo.com.tr --show-sample
```

Çıktıda atama alanının adını bulun (örn. `AssignedPerson`). Farklıysa aşağıdaki
komutlara `--assign-field OwnedByPerson` ekleyin.

### 2. Kuru çalıştırma (hiçbir şey değiştirmez)

```bash
export SMAX_PASSWORD='şifreniz'   # veya script sorunca girin
python assign_requests.py --username kullanici@flo.com.tr --dry-run
```

Varsayılan olarak yalnızca **açık** talepleri hedefler
(Ready / InProgress / Pending / Suspended). Kapalılar dahil hepsini hedeflemek
için `--all` ekleyin (önerilmez).

### 3. Gerçek atama

```bash
python assign_requests.py --username kullanici@flo.com.tr --yes
```

Talepler varsayılan olarak giriş yapan kullanıcıya atanır. Başka birine atamak
için `--assignee-email baska@flo.com.tr` kullanın.

## Faydalı seçenekler

| Seçenek | Açıklama |
|---|---|
| `--dry-run` | Sadece ne yapılacağını gösterir |
| `--show-sample` | Bir talebi tüm alanlarıyla yazdırır (alan adı keşfi) |
| `--assign-field X` | Atama alanı adı (varsayılan `AssignedPerson`) |
| `--filter "..."` | Özel EMS filtresi, örn. `"Status='RequestStatusReady'"` |
| `--all` | Statü filtresi olmadan tüm talepler |
| `--insecure` | İç ağ TLS sertifika hatasında doğrulamayı kapatır |
| `--tenant` / `--base-url` | Varsayılan: `316651941` / `https://flodesk.flo.com.tr` |

Ortam değişkenleri: `SMAX_BASE_URL`, `SMAX_TENANT`, `SMAX_USERNAME`, `SMAX_PASSWORD`.

## Güvenlik

Şifrenizi asla dosyaya/koda yazmayın; `SMAX_PASSWORD` ortam değişkeni veya
etkileşimli soru ile girin.
