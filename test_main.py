import argparse
from contextlib import redirect_stderr, redirect_stdout
import csv
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from main import (Product, deduplicate, export_results, filter_products, load_products,
                  main, parse_price, parse_products, price_argument, search_url)


class PriceTests(unittest.TestCase):
    def test_turkish_and_numeric_prices(self):
        for raw, expected in [("1.234,56 TL", 1234.56), ("₺ 999,90", 999.9),
                              ("12.500 TL", 12500), (1234.5, 1234.5),
                              ("1.234,50 TL 1.500 TL", 1234.5)]:
            with self.subTest(raw=raw):
                self.assertEqual(parse_price(raw), expected)
        for raw in [None, "Stokta yok", -50, "-50 TL", float("nan"), float("inf"), True]:
            with self.subTest(raw=raw):
                self.assertIsNone(parse_price(raw))

    def test_invalid_filter_is_rejected(self):
        self.assertEqual(price_argument("0"), 0)
        for raw in ["abc", "-10", "NaN"]:
            with self.assertRaises(argparse.ArgumentTypeError):
                price_argument(raw)

    def test_hepsiburada_missing_price_does_not_shift_next_price(self):
        html = '''<ul>
        <li class="productListContent-new"><a href="/a-p-1"><h2 class="title-module_titleRoot_new">A</h2></a></li>
        <li class="productListContent-new"><a href="/b-p-2"><h2>B</h2><div class="price-module_finalPrice_new">2.399,90 TL</div></a></li>
        </ul>'''
        products = parse_products(html, "hepsiburada")
        self.assertEqual([(p.name, p.price) for p in products], [("A", None), ("B", 2399.9)])
        self.assertEqual(products[1].url, "https://www.hepsiburada.com/b-p-2")

    def test_trendyol_uses_discounted_price_and_brand(self):
        html = '''<div class="p-card-wrppr"><a href="/keyboard-p-123">
        <span class="prdct-desc-cntnr-ttl">Marka</span><span class="prdct-desc-cntnr-name">Klavye</span>
        <div class="price-section"><span class="prc-org">1.500 TL</span><span class="prc-dsc">999,99 TL</span></div>
        </a></div>'''
        product, = parse_products(html, "trendyol")
        self.assertEqual((product.name, product.price), ("Marka Klavye", 999.99))

    def test_json_ld_nested_fallback_and_decimal_string(self):
        payload = {"@type": "ItemList", "itemListElement": [{"item": {
            "@type": "Product", "name": "Klavye", "offers": {"price": "1234.500", "priceCurrency": "TRY", "url": "/p-1"}}}]}
        product, = parse_products('<script type="application/ld+json">' + json.dumps(payload) + '</script>', "trendyol")
        self.assertEqual(product.price, 1234.5)

    def test_json_ld_completes_missing_card_price(self):
        html = '''<div class="product-card"><a href="/p-1"><span class="product-name">Klavye</span></a></div>
        <script type="application/ld+json">{"@type":"Product","name":"Klavye","offers":{"price":120,"url":"/p-1"}}</script>'''
        product, = parse_products(html, "trendyol")
        self.assertEqual(product.price, 120)

    def test_malformed_json_and_foreign_currency_are_ignored(self):
        html = '''<script type="application/ld+json">invalid</script>
        <script type="application/ld+json">{"@type":"Product","name":"X","offers":{"price":10,"priceCurrency":"USD"}}</script>'''
        self.assertEqual(parse_products(html, "trendyol"), [])

    def test_same_name_different_variant_does_not_supply_price(self):
        html = '''<div class="product-card"><a href="/red-p-1"><span class="product-name">Klavye</span></a></div>
        <script type="application/ld+json">{"@type":"Product","name":"Klavye","offers":{"price":120,"url":"/blue-p-2"}}</script>'''
        product, = parse_products(html, "trendyol")
        self.assertIsNone(product.price)

    def test_duplicate_with_price_replaces_missing_but_preserves_variants(self):
        products = [Product("X", None, "trendyol", "https://example.com/1"),
                    Product("X", 100, "trendyol", "https://example.com/1"),
                    Product("X", 200, "trendyol", "https://example.com/2")]
        self.assertEqual([p.price for p in deduplicate(products)], [100, 200])

    def test_filters_and_sort_keep_missing_last(self):
        products = [Product("X", None, "trendyol"), Product("Y", 100, "trendyol"), Product("Z", 200, "trendyol")]
        self.assertEqual([p.price for p in filter_products(products, descending=True)], [200, 100, None])
        self.assertEqual([p.price for p in filter_products(products, minimum=100, maximum=100)], [100])
        self.assertEqual(len(filter_products(products, priced_only=True)), 2)

    def test_url_encoding_and_pagination(self):
        for source, key in [("trendyol", "pi"), ("hepsiburada", "sayfa")]:
            params = parse_qs(urlsplit(search_url(source, "klavye & fare Türkçe", 3)).query)
            self.assertEqual(params["q"], ["klavye & fare Türkçe"])
            self.assertEqual(params[key], ["3"])

    def test_legacy_mismatched_lists_are_not_paired(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "products_ty.json"
            path.write_text(json.dumps({"names": ["A", "B"], "prices": ["100 TL"]}), encoding="utf-8")
            products, warnings, _ = load_products(path)
            self.assertTrue(warnings)
            self.assertTrue(all(p.price is None for p in products))

    def test_exports_escape_html_and_roundtrip(self):
        products = [Product('<script>alert(1)</script>', 1234.56, 'trendyol', 'javascript:alert(1)'),
                    Product('=1+1', None, 'hepsiburada')]
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            export_results(products, 'Türkçe <b>arama</b>', [], output)
            html = (output / 'report.html').read_text(encoding='utf-8')
            self.assertIn('1.234,56 TL', html)
            self.assertIn('&lt;script&gt;', html)
            self.assertNotIn('href="javascript:', html)
            with (output / 'results.csv').open(encoding='utf-8-sig', newline='') as f:
                rows = list(csv.reader(f, delimiter=';'))
            self.assertEqual(rows[2][0], "'=1+1")
            reloaded, _, query = load_products(output / 'results.json')
            self.assertEqual(reloaded[0].price, 1234.56)
            self.assertEqual(reloaded[0].url, '')
            self.assertEqual(query, 'Türkçe <b>arama</b>')

    def test_cli_load_filters_and_exports(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'saved.json'
            path.write_text(json.dumps([{"name": "Klavye", "price": 500, "source": "trendyol"}]), encoding="utf-8")
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                status = main(['--load', str(path), '--max-price', '600', '--output', str(Path(folder) / 'report')])
            self.assertEqual(status, 0)
            self.assertTrue((Path(folder) / 'report' / 'report.html').exists())

    def test_browser_error_is_actionable(self):
        from playwright.sync_api import Error
        with patch('main.scrape', side_effect=Error('Executable missing')):
            message = io.StringIO()
            with redirect_stderr(message):
                self.assertEqual(main(['klavye']), 1)
            self.assertIn('playwright install chromium', message.getvalue())


if __name__ == '__main__':
    unittest.main()
