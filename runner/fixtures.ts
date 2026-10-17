import { test as base, expect } from '@playwright/test';
import * as fs from 'node:fs';
import * as path from 'node:path';

export { expect };

export const credentials = {
  username: process.env.TEST_USERNAME ?? '',
  password: process.env.TEST_PASSWORD ?? '',
};

export function unique(prefix: string): string {
  const chars = 'abcdefghijklmnopqrstuvwxyz0123456789';
  let rand = '';
  for (let i = 0; i < 4; i++) {
    rand += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  return `${prefix}-${Date.now()}-${rand}`;
}

interface NetworkLog {
  failedRequests: Array<{ url: string; failure: string }>;
  badResponses: Array<{ url: string; status: number; method: string }>;
}

export const test = base.extend<{ evidence: void }>({
  evidence: [
    async ({ context, page }, use, testInfo) => {
      // 1. Determine testId from title (e.g. /^(T|X)\d+/)
      const titleMatch = testInfo.title.match(/^(T|X)\d+/);
      const testId = titleMatch ? titleMatch[0] : '';

      const consoleErrors: string[] = [];
      const failedRequests: Array<{ url: string; failure: string }> = [];
      const badResponses: Array<{ url: string; status: number; method: string }> = [];
      const visitedUrls: string[] = [];

      // Parse allowed hosts
      const allowedHostsRaw = process.env.ALLOWED_HOSTS ?? 'localhost,127.0.0.1';
      const allowedHosts = new Set(
        allowedHostsRaw.split(',').map((h) => h.trim().toLowerCase()).filter(Boolean)
      );

      // If BASE_URL is set, also allow its hostname
      if (process.env.BASE_URL) {
        try {
          const baseHost = new URL(process.env.BASE_URL).hostname.toLowerCase();
          allowedHosts.add(baseHost);
        } catch {
          // ignore invalid BASE_URL
        }
      }

      // 2. Install context.route allowlist handler
      await context.route('**/*', async (route) => {
        const req = route.request();
        let reqUrl: URL;
        try {
          reqUrl = new URL(req.url());
        } catch {
          await route.continue();
          return;
        }

        const protocol = reqUrl.protocol;
        const hostname = reqUrl.hostname.toLowerCase();

        // Allowed protocols or allowed hostnames
        if (
          protocol === 'data:' ||
          protocol === 'blob:' ||
          protocol === 'about:' ||
          allowedHosts.has(hostname)
        ) {
          await route.continue();
          return;
        }

        // Abort off-domain requests
        await route.abort('blockedbyclient');

        // Log to BLOCKED_LOG if set
        const blockedLogPath = process.env.BLOCKED_LOG;
        if (blockedLogPath) {
          try {
            const entry = {
              ts: new Date().toISOString(),
              testId,
              url: req.url(),
              method: req.method(),
              resourceType: req.resourceType(),
            };
            const dir = path.dirname(blockedLogPath);
            if (!fs.existsSync(dir)) {
              fs.mkdirSync(dir, { recursive: true });
            }
            fs.appendFileSync(blockedLogPath, JSON.stringify(entry) + '\n', 'utf-8');
          } catch {
            // Never let logging error break test
          }
        }
      });

      // Page listener setup for multi-page support
      const setupPageListeners = (p: typeof page) => {
        p.on('console', (msg) => {
          if (msg.type() === 'error') {
            consoleErrors.push(msg.text());
          }
        });

        p.on('pageerror', (err) => {
          consoleErrors.push(`Uncaught: ${err.message || String(err)}`);
        });

        p.on('requestfailed', (req) => {
          const failureText = req.failure()?.errorText || 'Unknown failure';
          // Skip if aborted by our client allowlist
          if (
            failureText.includes('ERR_BLOCKED_BY_CLIENT') ||
            failureText.includes('blockedbyclient')
          ) {
            return;
          }
          failedRequests.push({
            url: req.url(),
            failure: failureText,
          });
        });

        p.on('response', (res) => {
          try {
            const resUrl = res.url();
            if (resUrl.includes('/favicon.ico')) return;
            if (res.status() >= 400) {
              badResponses.push({
                url: resUrl,
                status: res.status(),
                method: res.request().method(),
              });
            }
          } catch {
            // response might be disposed
          }
        });

        p.on('framenavigated', (frame) => {
          if (frame === p.mainFrame()) {
            const url = frame.url();
            if (url && !visitedUrls.includes(url)) {
              visitedUrls.push(url);
            }
          }
        });
      };

      // Listen to existing and new pages in the context
      context.pages().forEach(setupPageListeners);
      context.on('page', setupPageListeners);

      try {
        await use();
      } finally {
        // Teardown: attach console.json and network.json to every test
        await testInfo.attach('console.json', {
          body: Buffer.from(JSON.stringify(consoleErrors, null, 2), 'utf-8'),
          contentType: 'application/json',
        });

        const networkPayload: NetworkLog = {
          failedRequests,
          badResponses,
        };
        await testInfo.attach('network.json', {
          body: Buffer.from(JSON.stringify(networkPayload, null, 2), 'utf-8'),
          contentType: 'application/json',
        });

        // Write VISITED_DIR/<testId>.json if VISITED_DIR is set and testId is present
        const visitedDir = process.env.VISITED_DIR;
        if (visitedDir && testId) {
          try {
            if (!fs.existsSync(visitedDir)) {
              fs.mkdirSync(visitedDir, { recursive: true });
            }
            const outPath = path.join(visitedDir, `${testId}.json`);
            fs.writeFileSync(
              outPath,
              JSON.stringify({ testId, urls: visitedUrls }, null, 2),
              'utf-8'
            );
          } catch {
            // Never break test on teardown file write error
          }
        }
      }
    },
    { auto: true },
  ],
});
