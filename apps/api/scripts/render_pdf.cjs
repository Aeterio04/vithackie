const path = require('path');
const fs = require('fs');

let playwright;
const candidatePaths = [
  'playwright',
  path.resolve(__dirname, '../../runner/node_modules/playwright'),
  path.resolve(__dirname, '../../../apps/runner/node_modules/playwright'),
  path.resolve(process.cwd(), 'apps/runner/node_modules/playwright'),
  path.resolve(process.cwd(), 'node_modules/playwright'),
];

for (const p of candidatePaths) {
  try {
    playwright = require(p);
    if (playwright && playwright.chromium) break;
  } catch (e) {
    // try next
  }
}

if (!playwright || !playwright.chromium) {
  console.error("Playwright module could not be resolved from candidate paths:", candidatePaths);
  process.exit(1);
}

const { chromium } = playwright;

async function main() {
  const htmlPath = process.argv[2];
  const pdfPath = process.argv[3];
  if (!htmlPath || !pdfPath) {
    console.error("Usage: node render_pdf.cjs <input.html> <output.pdf>");
    process.exit(1);
  }

  const absHtml = path.resolve(htmlPath);
  const absPdf = path.resolve(pdfPath);
  const fileUrl = 'file:///' + absHtml.replace(/\\/g, '/');

  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage();
    await page.goto(fileUrl, { waitUntil: 'load', timeout: 30000 });
    await page.waitForTimeout(400);
    await page.pdf({
      path: absPdf,
      format: 'A4',
      printBackground: true,
      displayHeaderFooter: true,
      headerTemplate: '<div></div>',
      footerTemplate: `
        <div style="font-size: 8px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #8A887F; width: 100%; padding: 0 12mm; display: flex; justify-content: space-between;">
          <span>KAWACH Autonomous QA Engine</span>
          <span>Page <span class="pageNumber"></span> of <span class="totalPages"></span></span>
        </div>
      `,
      margin: {
        top: '15mm',
        bottom: '15mm',
        left: '15mm',
        right: '15mm',
      },
    });
    console.log("PDF successfully rendered to " + absPdf);
  } finally {
    await browser.close();
  }
}

main().catch((err) => {
  console.error("Playwright PDF render error:", err);
  process.exit(1);
});
