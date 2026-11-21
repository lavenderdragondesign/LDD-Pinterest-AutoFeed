# Primary mockup fix

Replace the repository's `generate_feed.py` and `.github/workflows/update.yml` with the included files. Add `primary_images.json` to the repository root.

The generator reads each product's public storefront `og:image` metadata to identify the canonical primary image rather than selecting the first CSV variant. If the site does not expose the intended image through `og:image`, put a verified image URL in `primary_images.json` using the `item_group_id` as key:

{
  "5515372": "https://cdn.mydesigns.io/your-verified-primary-image.jpeg"
}

IMPORTANT: Storefront `og:image` is the social-sharing image, which may or may not equal the first mockup chosen in the MyDesigns editor. Verify a sample product on the live storefront before relying on it. If MyDesigns exposes a different image, use overrides.

If any product has no confirmed primary image, generation fails without overwriting the existing feed. No arbitrary color variant fallback.

The workflow schedule is fixed to every 15 minutes. GitHub Actions scheduled execution is best effort, not guaranteed every 15 minutes.

---

# Nov 12, 2026 fix (resumable downloads, per-product fallback, dates)

- The store CSV is ~7 MB and the CDN regularly drops the connection
  mid-transfer. `fetch()` now resumes with HTTP Range requests (the CDN
  answers 206) instead of dying on the first cut. A partial body is never
  treated as success.
- One product with an unresolvable primary image no longer fails the whole
  run. Its last published entry is reused when one exists; otherwise the
  product is skipped with a warning. The feed still never publishes a
  wrong image.
- Items now carry a stable `<pubDate>` (first-seen time, carried over from
  the previously published feed) and the channel a `<lastBuildDate>`, so
  Pinterest can tell new items from old ones. First run after this change
  stamps all current items with the run time; later runs keep them stable.
- Note: GitHub's scheduled runs are best effort — only 2 scheduled runs
  fired in ~36 hours despite the 15-minute cron (last good build Nov 12,
  3:28 AM CST). Manual runs all succeed. If the feed goes stale, run the
  workflow manually from the Actions tab.
