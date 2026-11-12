#!/usr/bin/env python3
"""Generate one Pinterest RSS entry per product, using the storefront primary image.

Fixes over the original (Nov 12, 2026):
- fetch() resumes truncated downloads with HTTP Range requests (the 7.3 MB
  store CSV regularly drops mid-transfer; the CDN answers 206) instead of
  killing the whole run on the first cut.
- A product whose primary image cannot be resolved no longer fails the
  whole run: the previous published entry for that product is reused when
  one exists, otherwise the product is skipped with a warning. The feed
  never publishes a wrong image, but one bad product can no longer freeze
  all 37.
- Items carry a stable <pubDate> and the channel a <lastBuildDate>.
  pubDate is the first-seen time for each product, carried over from the
  previously published feed so re-runs never restamp old items as new.
  New products get the current run time. Without dates Pinterest is slow
  to notice new items.
"""
import csv
import http.client
import io
import json
import os
import re
import time
import urllib.request
from collections import OrderedDict
from datetime import datetime, timezone
from email.utils import format_datetime
from html import escape, unescape
from html.parser import HTMLParser
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
import xml.etree.ElementTree as ET

SOURCE = os.getenv('PRODUCT_FEED_URL', 'https://dramahusky.mdstore.io/meta-feed.csv')
PUBLIC_DOMAIN = os.getenv('PUBLIC_STORE_DOMAIN', 'lddstores.com')
FALLBACK_SOURCE = os.getenv('FALLBACK_PRODUCT_FEED_URL', 'https://lddstores.com/meta-feed.csv')
OUT = os.getenv('OUTPUT_FILE', 'site/dramahusky.xml')
PREVIOUS_FEED_URL = os.getenv(
    'PREVIOUS_FEED_URL',
    'https://lavenderdragondesign.github.io/LDD-Pinterest-AutoFeed/dramahusky.xml')
ALLOWED_DOMAINS = set(os.getenv('STORE_DOMAINS', 'lddstores.com,dramahusky.mdstore.io').split(','))
OVERRIDES_FILE = os.getenv('PRIMARY_IMAGES_FILE', 'primary_images.json')
FETCH_RETRIES = int(os.getenv('FETCH_RETRIES', '3'))
MEDIA_NS = '{http://search.yahoo.com/mrss/}'


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


def fetch(url, timeout=60):
    """GET a URL, resuming truncated downloads with Range requests.

    The store CSV is ~7 MB and the CDN regularly drops the connection
    mid-transfer (http.client.IncompleteRead). urllib's read() then throws
    away the bytes already received, and retrying from scratch hits the
    same wall. Resuming from the byte offset works: the CDN answers 206
    with Accept-Ranges: bytes. A partial body is never treated as success.
    """
    data = b''
    failures = 0
    for round_no in range(1, 31):
        headers = {'User-Agent': 'Mozilla/5.0 (compatible; LDD-Pinterest-AutoFeed/2.0)'}
        if data:
            headers['Range'] = f'bytes={len(data)}-'
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as response:
                ranged = response.status == 206
                try:
                    chunk = response.read()
                except http.client.IncompleteRead as exc:
                    # partial is a suffix of the file when ranged, a fresh
                    # prefix of the full body when the server ignored Range.
                    data = data + exc.partial if ranged else exc.partial
                    print(f'WARN: download cut at {len(data)} bytes for {url}; resuming')
                    time.sleep(1)
                    continue
                data = data + chunk if ranged else chunk
                return data
        except Exception as exc:
            failures += 1
            print(f'WARN: fetch round {round_no} failed for {url}: {exc}')
            if failures >= FETCH_RETRIES:
                raise RuntimeError(f'fetch failed after {FETCH_RETRIES} attempts for {url}: {exc}')
            time.sleep(2 * failures)
    raise RuntimeError(f'fetch failed: download of {url} stalled at {len(data)} bytes')


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


def load_previous_feed():
    """Map guid -> (title, description, url, image, pubDate) from the feed
    currently published on GitHub Pages. Missing/unreadable -> empty map;
    every product then gets stamped with the current run time.
    """
    previous = {}
    try:
        data = fetch(PREVIOUS_FEED_URL, timeout=30)
    except Exception as exc:
        print(f'WARN: could not load previous feed ({exc}); all items get a fresh pubDate')
        return previous
    try:
        root = ET.fromstring(data)
    except Exception as exc:
        print(f'WARN: previous feed did not parse ({exc}); all items get a fresh pubDate')
        return previous
    for item in root.iter('item'):
        guid = (item.findtext('guid') or '').strip()
        if not guid:
            continue
        pub = (item.findtext('pubDate') or '').strip()
        media = item.find(f'{MEDIA_NS}content')
        image = ''
        if media is not None:
            image = media.get('url', '')
        previous[guid] = (
            item.findtext('title') or '',
            item.findtext('description') or '',
            item.findtext('link') or '',
            image,
            pub,
        )
    print(f'Previous feed: {len(previous)} known items')
    return previous


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
    previous = load_previous_feed()
    now = format_datetime(datetime.now(timezone.utc))
    entries = []
    skipped = []
    for key, (row, url) in groups.items():
        guid = f'dramahusky-{key}'
        prev = previous.get(guid)
        image = overrides.get(key, '')
        if not image:
            try:
                image = primary_image(url)
            except Exception as exc:
                print(f'WARN: Could not inspect primary image for {key}: {exc}')
        if not image.startswith('https://'):
            # Never publish a wrong image, but never freeze the whole feed
            # over one product: reuse its last published entry if we have
            # one, otherwise leave it out of this build with a warning.
            if prev and prev[3].startswith('https://'):
                print(f'WARN: image unresolved for {key}; reusing previous published entry')
                entries.append((key, prev[0], prev[1], prev[2], prev[3],
                                prev[4] or now))
                continue
            print(f'WARN: image unresolved for {key}; skipping product this run')
            skipped.append(key)
            continue
        title = row.get('title', '').strip() or 'DramaHusky Shirt'
        description = re.sub(r'<[^>]*>', ' ', row.get('description', '')).strip()[:1000]
        pub_date = (prev[4] if prev and prev[4] else now)
        entries.append((key, title, description, url, image, pub_date))
    if skipped:
        print(f'WARN: {len(skipped)} product(s) skipped (no confirmed image): {", ".join(skipped)}')
    parts = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/">',
             '<channel>', '<title>DramaHusky | Funny Husky Shirts</title>',
             f'<link>https://{PUBLIC_DOMAIN}/</link>',
             '<description>Funny Siberian Husky apparel and gifts from DramaHusky.</description>',
             '<language>en-us</language>',
             f'<lastBuildDate>{now}</lastBuildDate>']
    for key, title, description, url, img, pub_date in entries:
        parts.extend(['<item>', f'<title>{cdata(title)}</title>',
                      f'<link>{escape(url)}</link>',
                      f'<guid isPermaLink="false">dramahusky-{escape(key)}</guid>',
                      f'<pubDate>{pub_date}</pubDate>',
                      f'<description>{cdata(description)}</description>',
                      f'<media:content url="{escape(img, quote=True)}" medium="image"/>', '</item>'])
    parts.extend(['</channel>', '</rss>'])
    os.makedirs(os.path.dirname(OUT) or '.', exist_ok=True)
    tmp = OUT + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write('\n'.join(parts))
    os.replace(tmp, OUT)
    print(f'Created {OUT}: {len(entries)} items from {len(rows)} variants at {now}')


if __name__ == '__main__':
    generate()
