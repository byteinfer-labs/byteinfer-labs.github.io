"""Offline checks for the research page's initial download budget.

Run with: python3 -m unittest discover -s tests -v
"""
from html.parser import HTMLParser
from pathlib import Path
import re
import struct
import unittest
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]


class Page(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.tags = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


class ResearchAssets(unittest.TestCase):
    def setUp(self):
        self.html = ROOT / 'research/index.html'
        self.text = self.html.read_text()
        self.page = Page(self.text)

    def local_path(self, source, url):
        parsed = urlsplit(url)
        self.assertFalse(parsed.netloc, f'Critical asset requires another origin: {url}')
        self.assertFalse(parsed.scheme, f'Unexpected asset scheme: {url}')
        path = ((ROOT if parsed.path.startswith('/') else source.parent)
                / unquote(parsed.path.lstrip('/'))).resolve()
        self.assertTrue(path.is_relative_to(ROOT), f'Asset outside site: {url}')
        self.assertTrue(path.is_file(), f'Missing deployed asset: {url}')
        return path

    def test_initial_assets_stay_within_150_kib_without_external_dependencies(self):
        # A full-size artwork or a third-party font CSS chain would break this budget.
        pending = [self.html]
        for tag, attrs in self.page.tags:
            if tag in ('img', 'script') and attrs.get('src'):
                pending.append(self.local_path(self.html, attrs['src']))
            if tag == 'link' and attrs.get('rel') in ('stylesheet', 'preload', 'icon'):
                pending.append(self.local_path(self.html, attrs['href']))
        assets = set()
        while pending:
            path = pending.pop()
            if path in assets:
                continue
            assets.add(path)
            css = path.read_text() if path.suffix == '.css' else ''
            if path == self.html:
                css = '\n'.join(re.findall(r'<style[^>]*>(.*?)</style>', self.text, re.S))
            for match in re.finditer(r'''url\(\s*(?:"([^"]*)"|'([^']*)'|([^)]*))\s*\)''', css):
                url = next(value for value in match.groups() if value is not None).strip()
                if not url.startswith('data:'):
                    pending.append(self.local_path(path, url))
        total = sum(path.stat().st_size for path in assets)
        self.assertLess(total, 150 * 1024, f'Initial assets total {total:,} bytes')

    def test_navigation_image_has_small_payload_and_reserved_aspect_ratio(self):
        images = [attrs for tag, attrs in self.page.tags if tag == 'img']
        self.assertTrue(images)
        for image in images:
            path = self.local_path(self.html, image['src'])
            self.assertLess(path.stat().st_size, 10 * 1024)
            data = path.read_bytes()
            self.assertEqual(data[:8], b'\x89PNG\r\n\x1a\n')
            width, height = struct.unpack('>II', data[16:24])
            self.assertLessEqual(width, 156)
            self.assertAlmostEqual(int(image.get('width', 0)) / int(image.get('height', 1)),
                                   width / height, places=2)


if __name__ == '__main__':
    unittest.main()
