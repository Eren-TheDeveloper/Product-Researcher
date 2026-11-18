"""Hepsiburada ve Trendyol fiyat araştırması. Kullanım: python main.py --help"""

import argparse
import csv
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from html import escape
import json
from pathlib import Path
import re
import sys
import time
from urllib.parse import urlencode, urljoin, urlsplit

from bs4 import BeautifulSoup
from playwright.sync_api import Error as PlaywrightError


SOURCES = {
    "hepsiburada": {
        "base": "https://www.hepsiburada.com",
        "cards": 'li[class*="productListContent"], [data-test-id="product-card"], [data-test-id="product-card-container"]',
        "names": ['[data-test-id="product-card-name"]', 'h3', 'h2[class*="title"]', 'h2'],
        "prices": ['[data-test-id="price-current-price"]', '[data-test-id="price-current"]', '[class*="finalPrice"]', '[itemprop="price"]'],
    },
    "trendyol": {
        "base": "https://www.trendyol.com",
        "cards": '.p-card-wrppr, .product-card, [data-testid="product-card"]',
        "names": ['.prdct-desc-cntnr-name', '.product-name', '[data-testid="product-name"]'],
        "prices": ['.prc-dsc', '.discounted-price', '.prc-cntnr', '.price-section', '[data-testid="price-current-price"]', '[itemprop="price"]'],
    },
}


@dataclass(frozen=True)
class Product:
    name: str
    price: float | None
    source: str
    url: str = ""
    currency: str = "TRY"
    checked_at: str = ""


def parse_price(value):
    """Türkçe fiyat metnini veya JSON sayısını kuruş hassasiyetinde oku."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (float, int, Decimal)):
        text = str(value)
    else:
        text = str(value).replace("\xa0", " ").strip()
        match = re.search(r"-?\d[\d.,]*(?:\s+(?:TL|₺))?", text)
        if not match:
            return None
        text = match.group().replace("TL", "").replace("₺", "").strip()
        if "," in text:
            text = text.replace(".", "").replace(",", ".")
        elif re.fullmatch(r"\d{1,3}(?:\.\d{3})+", text):
            text = text.replace(".", "")
    try:
        amount = Decimal(text)
        if not amount.is_finite() or amount <= 0:
            return None
        return float(amount.quantize(Decimal("0.01")))
    except InvalidOperation:
        return None


def format_price(price):
    if price is None:
        return "Fiyat bulunamadı"
    return f"{price:,.2f}".translate(str.maketrans(",.", ".,")) + " TL"


def price_argument(value):
    if value.strip() in {"0", "0,00", "0.00"}:
        return 0.0
    result = parse_price(value)
    if result is None:
        raise argparse.ArgumentTypeError("Fiyat sıfır veya pozitif bir tutar olmalı (örnek: 1.500,50).")
    return result


def first_node(card, selectors):
    for selector in selectors:
        node = card.select_one(selector)
        if node is not None:
            return node
    return None


def safe_url(value, base):
    url = urljoin(base, str(value or ""))
    return url if value and urlsplit(url).scheme in {"https", "http"} else ""


def deduplicate(products):
    result = {}
    for product in products:
        key = (product.source, product.url or product.name.casefold())
        old = result.get(key)
        if old is None or (old.price is None and product.price is not None):
            result[key] = product
    return list(result.values())


def parse_products(html, source, checked_at=None):
    config = SOURCES[source]
    soup = BeautifulSoup(html, "html.parser")
    timestamp = checked_at or datetime.now().astimezone().isoformat(timespec="seconds")
    products = []
    for card in soup.select(config["cards"]):
        name_node = first_node(card, config["names"])
        if name_node is None:
            continue
        name = name_node.get("title") or name_node.get_text(" ", strip=True)
        if source == "trendyol":
            brand = card.select_one(".prdct-desc-cntnr-ttl, .product-brand")
            if brand and not name.casefold().startswith(brand.get_text(strip=True).casefold()):
                name = brand.get_text(strip=True) + " " + name
        price = None
        for selector in config["prices"]:
            node = card.select_one(selector)
            if node is not None:
                price = parse_price(node.get("content") or node.get_text(" ", strip=True))
                if price is not None:
                    break
        anchor = card if card.name == "a" else card.select_one("a[href]")
        url = safe_url(anchor.get("href"), config["base"]) if anchor else ""
        if name.strip():
            products.append(Product(name.strip(), price, source, url, checked_at=timestamp))

    # Kart tasarımı değişirse standart Product JSON-LD verilerini de dene.
    structured = []

    def walk(value):
        if isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, dict):
            types = value.get("@type", [])
            if types == "Product" or isinstance(types, list) and "Product" in types:
                offers = value.get("offers") or {}
                offers = offers if isinstance(offers, list) else [offers]
                for offer in offers:
                    if not isinstance(offer, dict) or offer.get("priceCurrency", "TRY") not in {"TRY", "TL"}:
                        continue
                    raw = offer.get("price", offer.get("lowPrice"))
                    # JSON-LD fiyatları noktalı ondalık biçimindedir.
                    try:
                        raw = Decimal(str(raw))
                    except InvalidOperation:
                        pass
                    name = str(value.get("name") or "").strip()
                    if name:
                        structured.append(Product(name, parse_price(raw), source,
                            safe_url(offer.get("url") or value.get("url"), config["base"]), checked_at=timestamp))
            for nested in value.values():
                if isinstance(nested, (list, dict)):
                    walk(nested)

    for script in soup.select('script[type="application/ld+json"]'):
        try:
            walk(json.loads(script.string or script.get_text()))
        except (ValueError, TypeError):
            continue
    if not products:
        return deduplicate(structured)
    by_url = {p.url: p for p in structured if p.url and p.price is not None}
    by_name = {}
    for candidate in structured:
        if candidate.price is not None:
            by_name.setdefault(candidate.name.casefold(), []).append(candidate)
    completed = []
    for p in products:
        fallback = by_url.get(p.url)
        candidates = by_name.get(p.name.casefold(), [])
        if fallback is None and len(candidates) == 1:
            candidate = candidates[0]
            # Aynı adlı, farklı bağlantılı varyantların fiyatlarını karıştırma.
            if not p.url or not candidate.url:
                fallback = candidate
        completed.append(Product(p.name, fallback.price, p.source, p.url or fallback.url,
                                 checked_at=timestamp) if p.price is None and fallback else p)
    return deduplicate(completed)


def search_url(source, query, page):
    if source == "hepsiburada":
        return SOURCES[source]["base"] + "/ara?" + urlencode({"q": query, "sayfa": page})
    return SOURCES[source]["base"] + "/sr?" + urlencode({"q": query, "pi": page})


def scrape(query, sources, pages, headed=False, timeout=30000, delay=1.5):
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

    products, warnings = [], []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not headed)
        try:
            context = browser.new_context(locale="tr-TR", viewport={"width": 1440, "height": 1000})
            page = context.new_page()
            for source in sources:
                seen = set()
                for number in range(1, pages + 1):
                    print(f"{source} | Sayfa {number}/{pages} taranıyor...", flush=True)
                    try:
                        response = page.goto(search_url(source, query, number), wait_until="domcontentloaded", timeout=timeout)
                        if response and response.status >= 400:
                            warnings.append(f"{source}: HTTP {response.status}; kaynak taraması durduruldu.")
                            break
                        try:
                            page.wait_for_selector(SOURCES[source]["cards"], timeout=timeout)
                            page.wait_for_selector(", ".join(SOURCES[source]["prices"]), timeout=min(timeout, 10000))
                        except PlaywrightTimeout:
                            pass
                        current = parse_products(page.content(), source)
                        if not current:
                            warnings.append(f"{source}, sayfa {number}: Ürün okunamadı. Erişim engeli, boş sonuç veya sayfa yapısı değişikliği olabilir.")
                            break
                        new = [p for p in current if (p.url or p.name.casefold()) not in seen]
                        products.extend(new)
                        seen.update(p.url or p.name.casefold() for p in new)
                        print(f"  {len(new)} yeni ürün; {sum(p.price is not None for p in new)} fiyat bulundu.")
                        if not new:
                            break
                    except PlaywrightError as exc:
                        warnings.append(f"{source}, sayfa {number}: {str(exc).splitlines()[0]}")
                        break
                    if number < pages:
                        time.sleep(delay)
        finally:
            browser.close()
    return deduplicate(products), warnings


def filter_products(products, minimum=None, maximum=None, priced_only=False, descending=False):
    result = [p for p in products if
              (not priced_only or p.price is not None) and
              (minimum is None or p.price is not None and p.price >= minimum) and
              (maximum is None or p.price is not None and p.price <= maximum)]
    return sorted(result, key=lambda p: (p.price is None, (-p.price if descending else p.price) if p.price is not None else 0, p.name))


def load_products(path):
    """Yeni raporları veya eski names/prices dosyalarını oku."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict) and "names" in data:
        names, prices = data["names"], data.get("prices", [])
        aligned = len(names) == len(prices)
        source = "trendyol" if Path(path).stem.endswith("_ty") else "hepsiburada"
        products = [Product(str(name), parse_price(prices[i]) if aligned else None, source)
                    for i, name in enumerate(names)]
        warnings = [f"{path}: Arşiv kaydı; fiyatların tarihi ve eski ad/fiyat eşleştirmeleri doğrulanamıyor."] if aligned else [f"{path}: Eski ad/fiyat listelerinin uzunluğu farklı; yanlış eşleştirmeyi önlemek için fiyatlar kullanılmadı. Canlı arama yapın."]
        return deduplicate(products), warnings, "Kayıtlı veriler"
    rows = data.get("products", []) if isinstance(data, dict) else data
    products = []
    for row in rows:
        currency = row.get("currency", "TRY")
        if currency != "TRY":
            raise ValueError(f"Desteklenmeyen para birimi: {currency}")
        products.append(Product(str(row["name"]), parse_price(row.get("price")),
                                str(row["source"]), safe_url(row.get("url"), ""),
                                currency, str(row.get("checked_at", ""))))
    return deduplicate(products), data.get("warnings", []) if isinstance(data, dict) else [], data.get("query", "Kayıtlı veriler") if isinstance(data, dict) else "Kayıtlı veriler"


def export_results(products, query, warnings, output):
    output.mkdir(parents=True, exist_ok=True)
    report = {"query": query, "exported_at": datetime.now().astimezone().isoformat(timespec="seconds"),
              "warnings": warnings, "products": [asdict(p) for p in products]}
    temp = output / "results.json.tmp"
    temp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(output / "results.json")
    with (output / "results.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["Ürün", "Fiyat (TL)", "Kaynak", "Bağlantı", "Kontrol zamanı"])
        for p in products:
            cells = [p.name, "" if p.price is None else f"{p.price:.2f}".replace(".", ","), p.source, p.url, p.checked_at]
            writer.writerow(["'" + c if c.startswith(("=", "+", "-", "@")) else c for c in cells])
    priced = [p.price for p in products if p.price is not None]
    stats = f"{len(products)} ürün · {len(priced)} fiyat · En düşük: {format_price(min(priced)) if priced else '—'}"
    rows = []
    for p in products:
        link = f'<a href="{escape(p.url, quote=True)}" target="_blank" rel="noopener noreferrer">Ürüne git ↗</a>' if safe_url(p.url, "") else "—"
        rows.append(f'<tr><td>{escape(p.name)}</td><td class="price">{format_price(p.price)}</td><td>{escape(p.source)}</td><td>{link}</td><td>{escape(p.checked_at or "Bilinmiyor")}</td></tr>')
    notices = "".join(f"<li>{escape(w)}</li>" for w in warnings)
    html = '''<!doctype html><html lang="tr"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Fiyat Araştırması</title><style>
body{font:16px system-ui;background:#f4f6fa;color:#172238;margin:0;padding:32px}main{max-width:1280px;margin:auto}
h1{margin-bottom:8px}p{color:#495770}.summary{background:#172238;color:white;padding:20px;border-radius:12px;margin:24px 0}
input{font:inherit;padding:12px;border:1px solid #bec7d6;border-radius:8px;width:min(90%,440px);margin-bottom:20px}
.scroll{overflow:auto;background:white;border-radius:12px}table{border-collapse:collapse;width:100%}th,td{text-align:left;padding:16px;border-bottom:1px solid #e6eaf1}
th{background:#eaf0f8;white-space:nowrap}.price{font-weight:700;white-space:nowrap;color:#116446}a{color:#1955b6;white-space:nowrap}li{margin:8px 0}
</style><main><h1>Fiyat Araştırması</h1><p>__QUERY__</p><div class="summary">__STATS__</div>
<p>Fiyatlar kayıt zamanına aittir. Farklı model, satıcı ve varyantlar eşdeğer olmayabilir. Kargo ve kupon koşullarını mağazada kontrol edin.</p>
<ul>__NOTICES__</ul><input id="filter" aria-label="Sonuçlarda ara" placeholder="Ürün veya mağaza ara…">
<div class="scroll"><table><thead><tr><th>Ürün</th><th>Fiyat</th><th>Mağaza</th><th>Bağlantı</th><th>Kontrol zamanı</th></tr></thead>
<tbody>__ROWS__</tbody></table></div><p id="count" aria-live="polite"></p></main><script>
const filter=document.getElementById('filter');filter.addEventListener('input',()=>{let count=0;for(const row of document.querySelectorAll('tbody tr')){row.hidden=!row.textContent.toLocaleLowerCase('tr').includes(filter.value.toLocaleLowerCase('tr'));if(!row.hidden)count++;}document.getElementById('count').textContent=count+' ürün gösteriliyor';});
</script></html>'''
    replacements = {"__QUERY__": escape(query), "__STATS__": escape(stats), "__NOTICES__": notices,
                    "__ROWS__": "".join(rows) or '<tr><td colspan="5">Filtrelere uygun ürün bulunamadı.</td></tr>'}
    html = re.sub(r"__QUERY__|__STATS__|__NOTICES__|__ROWS__", lambda m: replacements[m.group()], html)
    (output / "report.html").write_text(html, encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Hepsiburada ve Trendyol fiyat araştırması")
    parser.add_argument("query", nargs="?", help="Aranacak ürün adı")
    parser.add_argument("--source", choices=["all", *SOURCES], default="all", help="Mağaza (varsayılan: all)")
    parser.add_argument("--pages", type=int, default=2, help="Mağaza başına sayfa sayısı (1–30)")
    parser.add_argument("--min-price", type=price_argument, help="En düşük fiyat (TL)")
    parser.add_argument("--max-price", type=price_argument, help="En yüksek fiyat (TL)")
    parser.add_argument("--priced-only", action="store_true", help="Sadece fiyatı bulunan ürünler")
    parser.add_argument("--descending", action="store_true", help="Pahalıdan ucuza sırala")
    parser.add_argument("--headed", action="store_true", help="Tarayıcı penceresini göster")
    parser.add_argument("--timeout", type=int, default=30000, help="Sayfa bekleme süresi (ms)")
    parser.add_argument("--delay", type=float, default=1.5, help="Sayfalar arası bekleme (saniye)")
    parser.add_argument("--output", type=Path, default=Path("output"), help="Rapor klasörü")
    parser.add_argument("--load", type=Path, help="Canlı arama yerine JSON dosyasını aç")
    args = parser.parse_args(argv)
    if not 1 <= args.pages <= 30 or args.timeout <= 0 or not 0 <= args.delay < float("inf"):
        parser.error("Sayfa sayısı 1–30, zaman aşımı pozitif, bekleme sıfır veya pozitif olmalı.")
    if args.min_price is not None and args.max_price is not None and args.min_price > args.max_price:
        parser.error("En düşük fiyat en yüksek fiyattan büyük olamaz.")
    try:
        if args.load:
            products, warnings, query = load_products(args.load)
            if args.source != "all":
                products = [p for p in products if p.source == args.source]
        else:
            query = (args.query if args.query is not None else input("Aramak istediğiniz ürünün adı: ")).strip()
            if not query:
                parser.error("Ürün adı boş olamaz.")
            sources = list(SOURCES) if args.source == "all" else [args.source]
            products, warnings = scrape(query, sources, args.pages, args.headed, args.timeout, args.delay)
        missing = sum(p.price is None for p in products)
        if missing:
            warnings.append(f"{missing} ürünün fiyatı okunamadı; eksik fiyatlar tahmin edilmedi.")
        products = filter_products(products, args.min_price, args.max_price, args.priced_only, args.descending)
        print(f"\n{'FİYAT':>20}  {'MAĞAZA':14}  ÜRÜN\n" + "─" * 90)
        for product in products:
            print(f"{format_price(product.price):>20}  {product.source:14}  {product.name}")
        priced = [p.price for p in products if p.price is not None]
        print(f"\n{len(products)} ürün listelendi; {len(priced)} ürünün fiyatı var.")
        if priced:
            print(f"En düşük: {format_price(min(priced))} | Ortalama: {format_price(sum(priced) / len(priced))}")
        for warning in warnings:
            print(f"Uyarı: {warning}", file=sys.stderr)
        export_results(products, query, warnings, args.output)
        print(f"JSON, CSV ve HTML raporu: {args.output.resolve()}")
        return 0 if products else 1
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Hata: {exc}", file=sys.stderr)
        return 1
    except PlaywrightError as exc:
        print(f"Tarayıcı hatası: {str(exc).splitlines()[0]}\nChromium kurulumu: python -m playwright install chromium", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nİşlem kullanıcı tarafından durduruldu.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
