import { test as base, expect } from '@playwright/test';
import * as fs from 'node:fs';
import * as path from 'node:path';

export { expect };
import { inspectPageForError } from './qa_helpers';
export * from './qa_helpers';


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
      const allowedHostsRaw = process.env.ALLOWED_HOSTS ?? '*';
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

        // Allowed protocols, allowed hostnames, or subresources (stylesheets, scripts, fonts, images)
        const isNavigation = req.isNavigationRequest();
        const resourceType = req.resourceType();
        const isSafeSubresource = ['stylesheet', 'script', 'image', 'font', 'media', 'fetch', 'xhr'].includes(resourceType);

        if (
          allowedHosts.has('*') ||
          protocol === 'data:' ||
          protocol === 'blob:' ||
          protocol === 'about:' ||
          allowedHosts.has(hostname) ||
          (!isNavigation && isSafeSubresource)
        ) {
          await route.continue();
          return;
        }

        // Abort off-domain top-level navigation requests
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

      const testStart = Date.now();

      // Page listener setup for multi-page support
      const setupPageListeners = (p: typeof page) => {
        p.on('console', (msg) => {
          if (msg.type() === 'error') {
            const relMs = Date.now() - testStart;
            consoleErrors.push(`[+${relMs}ms] ${msg.text()}`);
          }
        });

        p.on('pageerror', (err) => {
          const relMs = Date.now() - testStart;
          consoleErrors.push(`[+${relMs}ms] Uncaught: ${err.message || String(err)}`);
        });

        p.on('requestfailed', (req) => {
          const failureText = req.failure()?.errorText || 'Unknown failure';
          if (
            failureText.includes('ERR_BLOCKED_BY_CLIENT') ||
            failureText.includes('blockedbyclient')
          ) {
            return;
          }
          const relMs = Date.now() - testStart;
          failedRequests.push({
            url: req.url(),
            failure: `[+${relMs}ms] ${failureText}`,
          });
        });

        p.on('response', (res) => {
          try {
            const resUrl = res.url();
            if (resUrl.includes('/favicon.ico')) return;
            if (res.status() >= 400) {
              const relMs = Date.now() - testStart;
              badResponses.push({
                url: resUrl,
                status: res.status(),
                method: res.request().method(),
                rel_time_ms: relMs,
              } as any);
            }
          } catch {
            // response might be disposed
          }
        });

        p.on('dialog', async (dialog) => {
          const msg = dialog.message();
          consoleErrors.push(`[+${Date.now() - testStart}ms] Dialog (${dialog.type()}): ${msg}`);
          try {
            await p.evaluate((m) => { (window as any).__lastDialogMessage = m; }, msg).catch(() => {});
            await dialog.accept().catch(() => {});
          } catch {}
        });

        const liveDir = process.env.LIVE_DIR;
        const workerId = `w${((testInfo.workerIndex ?? 0) % 2) + 1}`;

        p.on('framenavigated', async (frame) => {
          if (frame === p.mainFrame()) {
            const url = frame.url();
            if (url && !visitedUrls.includes(url)) {
              visitedUrls.push(url);
            }
            if (liveDir) {
              try {
                const workerImgPath = path.join(liveDir, `${workerId}.png`);
                await p.screenshot({ path: workerImgPath, timeout: 2000 }).catch(() => {});
              } catch {}
            }
          }
        });
      };

      const liveDir = process.env.LIVE_DIR;
      const workerId = `w${((testInfo.workerIndex ?? 0) % 2) + 1}`;

      // Listen to existing and new pages in the context
      context.pages().forEach(setupPageListeners);
      context.on('page', setupPageListeners);
      if (liveDir && testId) {
        try {
          if (!fs.existsSync(liveDir)) {
            fs.mkdirSync(liveDir, { recursive: true });
          }
          const startFile = path.join(liveDir, `${testId}.json`);
          fs.writeFileSync(
            startFile,
            JSON.stringify(
              {
                id: testId,
                title: testInfo.title,
                status: 'running',
                worker_id: workerId,
                started_at: new Date().toISOString(),
              },
              null,
              2
            ),
            'utf-8'
          );
        } catch {
          // Ignore live status write error
        }
      }

      try {
        // Visual indicator for video evidence: pointer cursor dot and click ripple overlay
        await context.addInitScript(() => {
          if (typeof window === 'undefined' || window !== window.top) return;
          const initOverlay = () => {
            if (document.getElementById('__kawach_cursor')) return;
            const cursor = document.createElement('div');
            cursor.id = '__kawach_cursor';
            cursor.style.cssText =
              'position:fixed;width:18px;height:18px;border-radius:50%;background:rgba(239,68,68,0.7);border:2px solid #ffffff;pointer-events:none;z-index:999999999;transform:translate(-50%,-50%);box-shadow:0 0 6px rgba(0,0,0,0.5);display:none;';
            document.documentElement.appendChild(cursor);

            window.addEventListener(
              'mousemove',
              (e) => {
                cursor.style.display = 'block';
                cursor.style.left = `${e.clientX}px`;
                cursor.style.top = `${e.clientY}px`;
              },
              { passive: true }
            );

            window.addEventListener(
              'click',
              (e) => {
                const ripple = document.createElement('div');
                ripple.style.cssText = `position:fixed;left:${e.clientX}px;top:${e.clientY}px;width:12px;height:12px;border-radius:50%;background:rgba(239,68,68,0.85);pointer-events:none;z-index:999999998;transform:translate(-50%,-50%) scale(1);transition:transform 0.35s ease-out, opacity 0.35s ease-out;box-shadow:0 0 10px rgba(239,68,68,0.9);`;
                document.documentElement.appendChild(ripple);
                requestAnimationFrame(() => {
                  ripple.style.transform = 'translate(-50%,-50%) scale(4)';
                  ripple.style.opacity = '0';
                });
                setTimeout(() => ripple.remove(), 400);
              },
              { passive: true }
            );
          };
          if (document.readyState === 'loading') {
            window.addEventListener('DOMContentLoaded', initOverlay);
          } else {
            initOverlay();
          }
        }).catch(() => {});

        // Ensure shared test data / state reset between workers
        await context.clearCookies().catch(() => {});
        await context.clearPermissions().catch(() => {});
        try {
          await page.evaluate(() => {
            try { localStorage.clear(); } catch {}
            try { sessionStorage.clear(); } catch {}
          }).catch(() => {});
        } catch {}
        await use();
      } finally {
        // Phase 2 settle delay: allow final state / toasts to be recorded in video
        await page.waitForTimeout(1000).catch(() => {});
        if (liveDir && testId) {
          try {
            if (!fs.existsSync(liveDir)) {
              fs.mkdirSync(liveDir, { recursive: true });
            }
            // Capture screenshot for worker preview
            const screenshotPath = path.join(liveDir, `${testId}.png`);
            await page.screenshot({ path: screenshotPath, timeout: 3000 }).catch(() => {});

            // Update latest screenshot for this worker
            const workerImgPath = path.join(liveDir, `${workerId}.png`);
            try {
              if (fs.existsSync(screenshotPath)) {
                fs.copyFileSync(screenshotPath, workerImgPath);
              }
            } catch {}

            const statusFile = path.join(liveDir, `${testId}.json`);
            const finalStatus = testInfo.status === 'passed' ? 'passed' : 'failed';
            fs.writeFileSync(
              statusFile,
              JSON.stringify(
                {
                  id: testId,
                  title: testInfo.title,
                  status: finalStatus,
                  duration_ms: testInfo.duration,
                  worker_id: workerId,
                  error_message: testInfo.error?.message ? String(testInfo.error.message).slice(0, 500) : null,
                  finished_at: new Date().toISOString(),
                },
                null,
                2
              ),
              'utf-8'
            );
          } catch {
            // Ignore live status update error
          }
        }

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

        // Second-opinion control check: if test failed, inspect whether the page actually contains error feedback
        if (testInfo.status !== 'passed') {
          try {
            const controlCheck = await inspectPageForError(page);
            await testInfo.attach('control_check.json', {
              body: Buffer.from(JSON.stringify(controlCheck, null, 2), 'utf-8'),
              contentType: 'application/json',
            });
          } catch {
            // ignore inspection error
          }
        }

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
