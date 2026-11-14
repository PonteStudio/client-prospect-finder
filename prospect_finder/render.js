// Renders pages in headless Chromium so JavaScript-built sites can be checked.
// Usage: node render.js urls.json out.json
const fs = require('fs');
const { chromium } = require('playwright');

(async () => {
  const urls = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
  const out = {};
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ userAgent: 'PonteStudio-ProspectFinder/0.1 (business research tool)' });
  const queue = [...urls];
  async function worker() {
    while (queue.length) {
      const url = queue.shift();
      const page = await ctx.newPage();
      try {
        const resp = await page.goto(url, { waitUntil: 'networkidle', timeout: 20000 });
        out[url] = { html: await page.content(), status: resp ? resp.status() : 0 };
      } catch (e) {
        try { out[url] = { html: await page.content(), status: 0 }; } catch (_) {}
      }
      await page.close();
    }
  }
  await Promise.all([worker(), worker(), worker(), worker()]);
  await browser.close();
  fs.writeFileSync(process.argv[3], JSON.stringify(out));
})();
