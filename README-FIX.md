# Primary mockup fix

Replace the repository's `generate_feed.py` and `.github/workflows/update.yml` with the included files. Add `primary_images.json` to the repository root.

The generator reads each product's public storefront `og:image` metadata to identify the canonical primary image rather than selecting the first CSV variant. If the site does not expose the intended image through `og:image`, put a verified image URL in `primary_images.json` using the `item_group_id` as key:

{
  "5515372": "https://cdn.mydesigns.io/your-verified-primary-image.jpeg"
}

IMPORTANT: Storefront `og:image` is the social-sharing image, which may or may not equal the first mockup chosen in the MyDesigns editor. Verify a sample product on the live storefront before relying on it. If MyDesigns exposes a different image, use overrides.

If any product has no confirmed primary image, generation fails without overwriting the existing feed. No arbitrary color variant fallback.

The workflow schedule is fixed to every 15 minutes. GitHub Actions scheduled execution is best effort, not guaranteed every 15 minutes.
