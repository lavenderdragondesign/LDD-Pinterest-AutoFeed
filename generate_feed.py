#!/usr/bin/env python3
"""Generate one Pinterest RSS entry per product, using the storefront primary image."""
import csv
import io
import json
import os
import re
import urllib.request
from collections import OrderedDict
from datetime import datetime, timezone
from email.utils import format_datetime
from html import escape, unescape
from html.parser import HTMLParser
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

SOURCE = os.getenv('PRODUCT_FEED_URL', 'https://dramahusky.mdstore.io/meta-feed.csv')
PUBLIC_DOMAIN = os.getenv('PUBLIC_STORE_DOMAIN', 'lddstores.com')
FALLBACK_SOURCE = os.getenv('FALLBACK_PRODUCT_FEED_URL', 'https://lddstores.com/meta-feed.csv')
OUT = os.getenv('OUTPUT_FILE', 'site/dramahusky.xml')
ALLOWED_DOMAINS = set(os.getenv('STORE_DOMAINS', 'lddstores.com,dramahusky.mdstore.io').split(','))
OVERRIDES_FILE = os.getenv('PRIMARY_IMAGES_FILE', 'primary_images.json')

class MetadataParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.images = []
    def handle_starttag(self, tag, attrs):
        if tag.lower() != 'meta':
            return
        a = dict(attrs)
        key = (a.get('property') or a.get('name') or '').lower()
        if key in ('og:image:secure_url', 'og:image', 'twitter:image'):
            url = unescape(a.get('content', '')).strip()
            if url.startswith('https://'):
                self.images.append((key, url))

def clean_url(url):
    p = urlsplit((url or '').strip())
    if p.scheme != 'https' or p.hostname not in ALLOWED_DOMAINS:
        return ''
    qs = [(k, v) for k, v in parse_qsl(p.query) if k.lower() not in {'variant', 'utm_source', 'utm_medium', 'utm_campaign'}]
    return urlunsplit((p.scheme, PUBLIC_DOMAIN, p.path, urlencode(qs), ''))

def fetch(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (compatible; LDD-Pinterest-AutoFeed/2.0)'})
    with urllib.request.urlopen(req, timeout=30) as response:
        return response.read()

def primary_image(product_url):
    parser = MetadataParser()
    try:
        page = fetch(product_url)
    except Exception:
        p = urlsplit(product_url)
        page = fetch(urlunsplit((p.scheme, 'dramahusky.mdstore.io', p.path, p.query, '')))
    parser.feed(page.decode('utf-8', 'replace'))
    for kind in ('og:image:secure_url', 'og:image', 'twitter:image'):
        for key, url in parser.images:
            if key == kind:
                return url
    return ''

def cdata(value):
    return '<![CDATA[' + str(value or '').replace(']]>', ']]]]><![CDATA[>') + ']]>'

def generate():
    try:
        data = fetch(SOURCE)
        print(f'Primary source: {SOURCE}')
    except Exception as exc:
        print(f'WARN: primary source unavailable ({exc}); trying fallback {FALLBACK_SOURCE}')
        data = fetch(FALLBACK_SOURCE)
    rows = list(csv.DictReader(io.StringIO(data.decode('utf-8-sig'))))
    if not rows:
        raise RuntimeError('CSV empty: existing RSS will not be overwritten')
    overrides = {}
    if os.path.isfile(OVERRIDES_FILE):
        with open(OVERRIDES_FILE, encoding='utf-8') as f:
            overrides = json.load(f)
    groups = OrderedDict()
    for row in rows:
        if row.get('availability', '').lower() not in ('in stock', 'preorder'):
            continue
        url = clean_url(row.get('link'))
        if not url:
            continue
        key = str(row.get('item_group_id') or url)
        if key not in groups:
            groups[key] = (row, url)
    if not groups:
        raise RuntimeError('No eligible products: existing RSS will not be overwritten')
    entries = []
    unresolved = []
    for key, (row, url) in groups.items():
        image = overrides.get(key, '')
        if not image:
            try:
                image = primary_image(url)
            except Exception as exc:
                print(f'WARN: Could not inspect primary image for {key}: {exc}')
        if not image.startswith('https://'):
            unresolved.append(key)
            continue
        title = row.get('title', '').strip() or 'DramaHusky Shirt'
        description = re.sub(r'<[^>]*>', ' ', row.get('description', '')).strip()[:1000]
        entries.append((key, title, description, url, image))
    # Fail closed rather than publishing an incomplete feed or wrong variant photos.
    if unresolved:
        raise RuntimeError('Primary images unresolved for product IDs: ' + ', '.join(unresolved) + '. Add verified URLs to primary_images.json or restore storefront metadata. Existing RSS left untouched.')
    now = format_datetime(datetime.now(timezone.utc))
    parts = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/">',
             '<channel>', '<title>DramaHusky | Funny Husky Shirts</title>',
             f'<link>https://{PUBLIC_DOMAIN}/</link>',
             '<description>Funny Siberian Husky apparel and gifts from DramaHusky.</description>',
             '<language>en-us</language>']
    for key, title, description, url, img in entries:
        parts.extend(['<item>', f'<title>{cdata(title)}</title>',
                      f'<link>{escape(url)}</link>',
                      f'<guid isPermaLink="false">dramahusky-{escape(key)}</guid>',
                      f'<description>{cdata(description)}</description>',
                      f'<media:content url="{escape(img, quote=True)}" medium="image"/>', '</item>'])
    parts.extend(['</channel>', '</rss>'])
    os.makedirs(os.path.dirname(OUT) or '.', exist_ok=True)
    tmp = OUT + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write('\n'.join(parts))
    os.replace(tmp, OUT)
    print(f'Created {OUT}: {len(entries)} primary images from {len(rows)} variants at {now}')

if __name__ == '__main__':
    generate()
