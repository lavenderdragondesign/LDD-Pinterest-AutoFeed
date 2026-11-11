#!/usr/bin/env python3
import csv, io, os, re, urllib.request
from datetime import datetime, timezone
from email.utils import format_datetime
from html import escape
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

SOURCE = os.getenv("PRODUCT_FEED_URL", "https://lddstores.com/meta-feed.csv")
OUT = os.getenv("OUTPUT_FILE", "site/dramahusky.xml")
DOMAIN = "lddstores.com"

def clean_url(url):
    p = urlsplit((url or "").strip())
    if p.scheme != "https" or p.hostname not in {DOMAIN, "www."+DOMAIN}:
        return ""
    # Remove size/color variant parameter: one pin per product
    qs = [(k,v) for k,v in parse_qsl(p.query) if k.lower() not in {"variant","utm_source","utm_medium","utm_campaign"}]
    return urlunsplit((p.scheme,p.netloc,p.path,urlencode(qs),""))

def cdata(value):
    return "<![CDATA[" + str(value or "").replace("]]>", "]]]]><![CDATA[>") + "]]>"

def generate():
    req = urllib.request.Request(SOURCE, headers={"User-Agent":"LDD-Pinterest-AutoFeed/1.0"})
    with urllib.request.urlopen(req,timeout=40) as resp:
        data=resp.read()
    rows=list(csv.DictReader(io.StringIO(data.decode("utf-8-sig"))))
    if not rows: raise RuntimeError("Product CSV is empty; refusing to overwrite existing RSS")
    unique={}
    for row in rows:
        if row.get("availability","").lower() not in {"in stock","preorder"}: continue
        url=clean_url(row.get("link"))
        image=(row.get("image_link") or "").strip()
        if not url or not image.startswith("https://"): continue
        key=row.get("item_group_id") or url
        if key not in unique: unique[key]=(row,url,image)
    if not unique: raise RuntimeError("No eligible products; refusing to overwrite RSS")
    now=format_datetime(datetime.now(timezone.utc))
    parts=['<?xml version="1.0" encoding="UTF-8"?>',
           '<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/">',
           '<channel><title>DramaHusky | Funny Husky Shirts</title>',
           '<link>https://lddstores.com/</link>',
           '<description>Funny Siberian Husky apparel and gifts from DramaHusky.</description>',
           '<language>en-us</language>']
    for key,(row,url,img) in unique.items():
        title=row.get("title","DramaHusky Shirt").strip()
        description=re.sub(r"<[^>]*>"," ",row.get("description","")).strip()[:1000]
        parts += ['<item>',f'<title>{cdata(title)}</title>',
                  f'<link>{escape(url)}</link>',
                  f'<guid isPermaLink="false">dramahusky-{escape(str(key))}</guid>',
                  f'<description>{cdata(description)}</description>',
                  f'<media:content url="{escape(img,quote=True)}" medium="image"/>',
                  '</item>']
    parts+=['</channel></rss>']
    os.makedirs(os.path.dirname(OUT) or ".",exist_ok=True)
    with open(OUT,"w",encoding="utf-8") as f:f.write("\n".join(parts))
    print(f"Created {OUT}: {len(unique)} unique products from {len(rows)} variants, checked {now}")
if __name__=="__main__": generate()
