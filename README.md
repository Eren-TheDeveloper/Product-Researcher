<div align="center">

# 🛍️ Fiyat Araştırması

### Ürününü ara. Fiyatları sırala. Bütçene uygun seçenekleri keşfet.

Hepsiburada ve Trendyol sonuçlarını tek tabloda incele; araştırmanı **HTML, CSV ve JSON** olarak kaydet.

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)
![Playwright](https://img.shields.io/badge/Browser-Playwright-2EAD33?style=flat-square)
![BeautifulSoup](https://img.shields.io/badge/Parser-BeautifulSoup-596780?style=flat-square)
![Currency](https://img.shields.io/badge/Para_birimi-TRY-116446?style=flat-square)

[Hızlı Başlangıç](#baslangic) · [Kullanım](#kullanim) · [Seçenekler](#secenekler) · [Raporlar](#raporlar) · [Veri Doğruluğu](#veri)

</div>

---

## ✨ Neler yapabilirsiniz?

| Özellik | Size ne sağlar? |
| :--- | :--- |
| **İki mağazada arama** | Hepsiburada ve Trendyol sonuçlarını aynı araştırmada toplar. |
| **Görünür fiyatlar** | Ürün adı, fiyat, mağaza, bağlantı ve kontrol zamanını birlikte kaydeder. |
| **Bütçe filtresi** | Alt ve üst fiyat sınırıyla aramanızı daraltır. |
| **Fiyat sıralaması** | Ucuzdan pahalıya veya pahalıdan ucuza listeleme sunar. |
| **Tekrarları temizleme** | Aynı mağaza ve ürün bağlantısının yeniden listelenmesini önler. |
| **Aranabilir HTML raporu** | Sonuçları ürün veya mağaza adına göre süzmenizi sağlar. |
| **CSV ve JSON çıktısı** | Verileri Excel'de veya başka araçlarda kullanmanıza olanak tanır. |
| **Çevrimdışı inceleme** | Kayıtlı dosyadan yeniden filtreleme ve rapor oluşturma sağlar. |

> **Eksik fiyatlar açıkça gösterilir.** Okunamayan tutarlar tahmin edilmez; “Fiyat bulunamadı” olarak listelenir.

<a id="baslangic"></a>
## 🚀 Hızlı başlangıç

Proje klasöründe PowerShell açın. Python 3.10 veya üzeri gerekir.

**1. Ortamı hazırlayın**

```powershell
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe -m playwright install chromium
```

**2. İlk aramanızı yapın**

```powershell
.\venv\Scripts\python.exe main.py "mekanik klavye"
```

**3. Raporunuzu açın**

```powershell
Start-Process .\output\report.html
```

Varsayılan arama iki mağazada, mağaza başına **2 sayfa** tarar. Sonuçlar ucuzdan pahalıya sıralanır; fiyatı olmayan ürünler sonda gösterilir. Parametresiz çalıştırırsanız uygulama ürün adını sorar.

<a id="kullanim"></a>
## 🎯 Kullanım

### Bütçenize uygun ürünleri bulun

500–2.500 TL aralığında, yalnızca fiyatı okunabilen ürünleri listeleyin:

```powershell
.\venv\Scripts\python.exe main.py "klavye" --min-price 500 --max-price 2500 --priced-only
```

### Tek mağazada daha fazla sayfa tarayın

Tarayıcı penceresini açarak Trendyol'da 3 sayfa arayın:

```powershell
.\venv\Scripts\python.exe main.py "klavye" --source trendyol --pages 3 --headed
```

### En yüksek fiyatlardan başlayın

```powershell
.\venv\Scripts\python.exe main.py "kablosuz kulaklık" --descending
```

### Kayıtlı verileri internet olmadan inceleyin

```powershell
.\venv\Scripts\python.exe main.py --load products.json
```

### Raporu farklı bir bütçeyle yeniden oluşturun

```powershell
.\venv\Scripts\python.exe main.py --load output/results.json --max-price 1500 --output output/filtered
```

> **Aramalarınızı saklayın:** Aynı çıktı klasöründeki raporlar her çalıştırmada yenilenir. Ayrı araştırmaları korumak için `--output output/klavye` gibi farklı klasörler kullanın.

<a id="secenekler"></a>
## Komut satırı seçenekleri

| Seçenek | Açıklama | Varsayılan |
| :--- | :--- | :--- |
| `query` | Ürün adı; boşluk varsa tırnak içine alın | Girilmezse sorulur |
| `--source` | `all`, `hepsiburada` veya `trendyol` | `all` |
| `--pages` | Mağaza başına sayfa sayısı | `2` · aralık: `1–30` |
| `--min-price` | Alt fiyat sınırı, TL | Sınır yok |
| `--max-price` | Üst fiyat sınırı, TL | Sınır yok |
| `--priced-only` | Sadece fiyatı bulunan ürünler | Kapalı |
| `--descending` | Pahalıdan ucuza sırala | Kapalı |
| `--headed` | Tarayıcı penceresini göster | Kapalı |
| `--timeout` | Sayfa bekleme süresi, milisaniye | `30000` |
| `--delay` | Sayfalar arası bekleme, saniye | `1.5` |
| `--output` | Rapor klasörü | `output` |
| `--load` | Canlı arama yerine JSON dosyası oku | Kullanılmaz |

Fiyat sınırları `1500` veya `"1.500,50"` biçiminde yazılabilir. Bütçe filtresi fiyatı olmayan ürünleri eler.

```powershell
.\venv\Scripts\python.exe main.py --help
```

<a id="raporlar"></a>
## 📊 Raporlar

```text
output/
├── report.html     → Tarayıcıda açılan, arama alanı içeren fiyat tablosu
├── results.csv     → Excel için UTF-8 BOM, noktalı virgülle ayrılmış veri
└── results.json    → Ürün kayıtları, arama bilgisi ve uyarılar
```

| Çıktı | Ne zaman kullanılır? |
| :--- | :--- |
| **HTML** | Ürünleri incelemek, mağaza bağlantılarını açmak ve sonuçlarda arama yapmak için |
| **CSV** | Fiyatları Excel'e aktarmak ve kendi analizlerinizi yapmak için |
| **JSON** | Veriyi başka araçlarda işlemek veya `--load` ile yeniden açmak için |

Terminal ve HTML raporunda ürün sayısı, fiyatı bulunan ürün sayısı ve en düşük fiyat gösterilir. Terminal ayrıca ortalama fiyatı verir. İstatistikler filtrelerden sonra listelenen ürünlere aittir; farklı modellerin fiyatları aynı özete dahil olabilir.

<a id="veri"></a>
## Veri ve fiyat doğruluğu

- Ürün adı ve fiyatı **aynı ürün kartından** alınır; eksik fiyat başka ürünün fiyatıyla doldurulmaz. Kartlar okunamazsa standart Product JSON-LD verileri denenir.
- Fiyat bulunamadığında `null` kaydedilir, raporda “Fiyat bulunamadı” gösterilir. Bütçe filtresi fiyatı olmayanları eler.
- Aynı mağaza ve ürün bağlantısı tekrarları temizlenir. Mağazalar arasındaki farklı modeller otomatik olarak aynı ürün kabul edilmez. Özet istatistikleri listelenen sonuçlara aittir.
- Fiyatlar TRY cinsindedir; kargo, kupon ve kişiye özel kampanyalar hesaplanmaz. Güncel tutarı ürün sayfasından kontrol edin. Kayıtlı dosya yeni bir tarama olmadan güncel fiyatı temsil etmez.

<details>
<summary><strong>Eski JSON dosyaları nasıl işlenir?</strong></summary>

Mevcut `products.json` ve `products_ty.json` dosyaları korunur.

- Eski `names` / `prices` listelerinin uzunluğu farklıysa fiyat eşleştirmesi yapılmaz.
- Uzunluklar eşitse kayıtlar eski sıralarıyla okunur. Eski toplayıcının eşleştirme doğruluğu geriye dönük doğrulanamaz; rapora arşiv uyarısı eklenir.
- Eski kayıtlarda fiyatın kontrol zamanı bilinmez.
- Projedeki mevcut Trendyol arşivinin fiyat listesi boştur. Fiyat toplamak için yeni bir canlı arama gerekir.

</details>

## Sorun giderme

| Durum | Yapılabilecek işlem |
| :--- | :--- |
| **HTTP 403 veya doğrulama ekranı** | `--headed` ile tarayıcıdaki durumu inceleyin. Mağaza erişimi engelliyorsa canlı veri alınamayabilir; uygulama bunu uyarı olarak bildirir. |
| **Chromium bulunamadı** | `.\venv\Scripts\python.exe -m playwright install chromium` komutunu çalıştırın. |
| **Ürün veya fiyat okunamadı** | Önce mağaza sayfasını kontrol edin. Tasarım değiştiyse `main.py` içindeki `SOURCES` seçicilerinin güncellenmesi gerekebilir. |
| **Filtre sonrası sonuç kalmadı** | Fiyat aralığını genişletin; kaynak veride fiyat bulunup bulunmadığını kontrol edin. |

Playwright güncellendikten sonra Chromium'u yeniden kurmak gerekebilir. Ayrıntılar: [Playwright tarayıcı kurulum belgesi](https://playwright.dev/python/docs/browsers).

Bir mağazada sonuç bulunması diğer mağazaya da başarıyla erişildiği anlamına gelmez. Terminaldeki ve rapordaki uyarılar kaynakların durumunu gösterir.

## Testler

```powershell
.\venv\Scripts\python.exe -m unittest -v
```

Testler ağ bağlantısı gerektirmez. Türkçe fiyat dönüşümü, eksik fiyatın diğer ürüne kaymaması, indirimli fiyat, JSON-LD, filtreleme, sayfalama URL'leri, eski veriler ve rapor çıktıları doğrulanır. Canlı mağazalara erişim ayrıca değerlendirilmelidir.

<details>
<summary><strong>Otomasyon için çıkış kodları</strong></summary>

| Kod | Anlamı |
| :--- | :--- |
| `0` | Sonuç bulundu |
| `1` | Sonuç yok veya çalışma hatası |
| `2` | Geçersiz komut satırı argümanı |
| `130` | İşlem kullanıcı tarafından durduruldu |

</details>
