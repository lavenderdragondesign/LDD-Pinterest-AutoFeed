# LDD Pinterest AutoFeed

Converts the public MyDesigns product CSV at `https://lddstores.com/meta-feed.csv` into a Pinterest-style RSS 2.0 feed. One item per `item_group_id`, not one per size/color. Only in-stock products are included. Runs daily and can run manually.

## Setup
1. Create a **public** GitHub repository named `LDD-Pinterest-AutoFeed` under `lavenderdragondesign`.
2. Upload the contents of this ZIP (including the hidden `.github` folder) to the repository's `main` branch.
3. In **Settings → Actions → General → Workflow permissions**, allow **Read and write permissions** if available.
4. In **Actions → Update Pinterest RSS → Run workflow**, run once.
5. In **Settings → Pages → Build and deployment**, choose **Deploy from a branch**, `gh-pages`, `/ (root)`, and save.
6. Once deployed, the expected URL is:
   `https://lavenderdragondesign.github.io/LDD-Pinterest-AutoFeed/dramahusky.xml`

## Important Pinterest caveat
Pinterest may require the RSS feed's site and product-link domain to meet its claimed-website rules. A feed hosted on github.io with product links to claimed `lddstores.com` is **not guaranteed to be accepted**. Test it in Pinterest before relying on automation. If rejected, we will need an RSS URL hosted under the claimed domain or another supported publishing route.

## Notes
- GitHub Pages is public; all products are already public storefront data.
- No passwords or API keys are needed.
- Existing products may be imported when the RSS feed is first connected. Subsequent runs keep stable GUIDs to avoid identifying variants as new products.
- This creates a feed; it does **not** itself publish Pins or guarantee Pinterest acceptance, reach, or sales.
- Scheduled GitHub Actions runs can be delayed, and may be disabled for inactive public repositories.
