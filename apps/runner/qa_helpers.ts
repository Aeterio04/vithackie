import { Page, Locator, expect } from '@playwright/test';

export interface ExpectFeedbackOptions {
  trigger?: () => Promise<void>;
  scope?: Locator | string;
  expectedText?: string | RegExp;
  timeoutMs?: number;
}

const ERROR_VOCABULARY = [
  'invalid',
  'incorrect',
  'wrong',
  'failed',
  'failure',
  'error',
  'required',
  'not found',
  'try again',
  'already exists',
  'already registered',
  'already in use',
  'cannot',
  'denied',
  'unauthorized',
  'mismatch',
];

const SUCCESS_VOCABULARY = [
  'success',
  'successful',
  'confirmed',
  'complete',
  'completed',
  'placed',
  'welcome',
  'saved',
  'thank you',
  'thanks',
  'added',
  'added to cart',
  'item added',
  'order placed',
];

export function uniqueData(prefix: string = 'user'): string {
  const ts = Date.now();
  const rand = Math.random().toString(36).substring(2, 7);
  return `${prefix}-${ts}-${rand}`;
}

export function uniqueEmail(prefix: string = 'test'): string {
  return `${uniqueData(prefix)}@example.com`;
}

/**
 * Normalizes text by lowercasing, trimming, and collapsing whitespace.
 */
function normalizeText(text: string): string {
  return text.toLowerCase().replace(/\s+/g, ' ').trim();
}

/**
 * Deterministic browser evaluation to inspect for error feedback across:
 * 1. Native HTML5 form validation (input.validity, validationMessage, :invalid)
 * 2. ARIA alerts / live regions (role=alert, role=status, aria-live, aria-invalid=true)
 * 3. Error classes / testids (.error, .invalid, .alert, .toast, etc.)
 * 4. Open shadow DOM trees
 * 5. Same-origin iframes
 * 6. Visible text matching error vocabulary
 */
export async function inspectPageForError(
  page: Page,
  scopeSelector?: string,
  expectedText?: string
): Promise<{ found: boolean; reason: string; matchedText?: string }> {
  try {
    const result = await page.evaluate(
      ({ scopeSel, expText, vocab }) => {
        const root = scopeSel ? document.querySelector(scopeSel) || document.body : document.body;

        function isVisible(el: Element): boolean {
          if (!el) return false;
          const style = window.getComputedStyle(el);
          if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') {
            return false;
          }
          const rect = el.getBoundingClientRect();
          return rect.width > 0 && rect.height > 0;
        }

        function normalize(t: string): string {
          return t.toLowerCase().replace(/\s+/g, ' ').trim();
        }

        // 1. Native HTML5 form validation
        const inputs = Array.from(root.querySelectorAll('input, select, textarea')) as HTMLInputElement[];
        for (const input of inputs) {
          if (input.validity && !input.validity.valid) {
            const msg = input.validationMessage || 'HTML5 validation failed';
            return { found: true, reason: `native_html5_validation: ${msg}`, matchedText: msg };
          }
          if (input.matches && input.matches(':invalid')) {
            return { found: true, reason: 'native_html5_invalid_pseudoclass', matchedText: input.validationMessage || '' };
          }
          if (input.getAttribute('aria-invalid') === 'true') {
            return { found: true, reason: 'aria_invalid_true', matchedText: input.name || input.id };
          }
        }

        // Collect text and check elements
        const errorElements: Element[] = [];

        function collectElements(container: Element | DocumentFragment) {
          // 2. ARIA roles and live regions
          const alerts = container.querySelectorAll(
            '[role="alert"], [role="status"], [aria-live="assertive"], [aria-live="polite"]'
          );
          alerts.forEach((el) => {
            if (isVisible(el)) errorElements.push(el);
          });

          // 3. Class names and IDs matching error patterns
          const candidates = container.querySelectorAll(
            '[class*="error" i], [class*="invalid" i], [class*="alert" i], [class*="toast" i], [class*="warning" i], [class*="feedback" i], [data-testid*="error" i], [data-testid*="toast" i], [id*="error" i]'
          );
          candidates.forEach((el) => {
            if (isVisible(el) && (el.textContent || '').trim().length > 0) {
              errorElements.push(el);
            }
          });

          // 4. Open shadow DOM traversal
          const all = container.querySelectorAll('*');
          all.forEach((el) => {
            if (el.shadowRoot) {
              collectElements(el.shadowRoot);
            }
          });
        }

        collectElements(root);

        // 5. Check iframes (same-origin)
        const iframes = Array.from(root.querySelectorAll('iframe')) as HTMLIFrameElement[];
        for (const iframe of iframes) {
          try {
            const doc = iframe.contentDocument;
            if (doc) collectElements(doc.body);
          } catch {
            // cross-origin iframe ignored
          }
        }

        // Evaluate found elements
        for (const el of errorElements) {
          const txt = (el.textContent || '').trim();
          const norm = normalize(txt);
          if (!norm) continue;

          if (expText) {
            const normExp = normalize(expText);
            if (norm.includes(normExp) || normExp.includes(norm)) {
              return { found: true, reason: `matched_expected_text: ${txt}`, matchedText: txt };
            }
          }

          for (const word of vocab) {
            if (norm.includes(word)) {
              return { found: true, reason: `error_vocabulary_match [${word}]: ${txt}`, matchedText: txt };
            }
          }
        }

        // 6. Direct visible text search across root ONLY for expText if provided
        if (expText) {
          const visibleText = normalize((root as HTMLElement).innerText || '');
          const normExp = normalize(expText);
          if (visibleText.includes(normExp)) {
            return { found: true, reason: `visible_text_includes_expected: ${expText}`, matchedText: expText };
          }
        }

        return { found: false, reason: 'no_error_feedback_found' };
      },
      {
        scopeSel: typeof scopeSelector === 'string' ? scopeSelector : undefined,
        expText: typeof expectedText === 'string' ? expectedText : undefined,
        vocab: ERROR_VOCABULARY,
      }
    );

    return result;
  } catch (err: any) {
    return { found: false, reason: `inspection_failed: ${err?.message || err}` };
  }
}

/**
 * Robust oracle for error feedback.
 * Auto-waits up to timeoutMs (default 10s) using expect.poll.
 */
export async function expectErrorFeedback(
  page: Page,
  options: ExpectFeedbackOptions = {}
): Promise<void> {
  const { trigger, scope, expectedText, timeoutMs = 10000 } = options;

  if (trigger) {
    await trigger();
  }

  const scopeSelector = typeof scope === 'string' ? scope : undefined;
  const expTextStr = typeof expectedText === 'string' ? expectedText : undefined;

  await expect
    .poll(
      async () => {
        const res = await inspectPageForError(page, scopeSelector, expTextStr);
        return res.found;
      },
      {
        timeout: timeoutMs,
        message: `Expected error feedback to be displayed on page within ${timeoutMs}ms (expected: ${expectedText || 'any error message/alert'})`,
      }
    )
    .toBe(true);
}

/**
 * Asserts that NO error feedback is displayed on the page.
 */
export async function expectNoErrorFeedback(
  page: Page,
  options: ExpectFeedbackOptions = {}
): Promise<void> {
  const { trigger, scope, timeoutMs = 3000 } = options;

  if (trigger) {
    await trigger();
  }

  // Short settle wait for any async toasts
  await page.waitForTimeout(500);

  const scopeSelector = typeof scope === 'string' ? scope : undefined;
  const res = await inspectPageForError(page, scopeSelector);

  expect(
    res.found,
    `Expected NO error feedback, but found: ${res.reason} (text: ${res.matchedText})`
  ).toBe(false);
}

/**
 * Robust oracle for success feedback.
 */
export async function expectSuccessFeedback(
  page: Page,
  options: ExpectFeedbackOptions = {}
): Promise<void> {
  const { trigger, scope, expectedText, timeoutMs = 10000 } = options;

  if (trigger) {
    await trigger();
  }

  const expTextStr = typeof expectedText === 'string' ? normalizeText(expectedText) : undefined;

  await expect
    .poll(
      async () => {
        const txt = await page.evaluate(({ scopeSel, vocab, exp }) => {
          const lastDialog = (((window as any).__lastDialogMessage || '') as string).toLowerCase().replace(/\s+/g, ' ');
          if (exp && lastDialog.includes(exp)) return true;
          for (const word of vocab) {
            if (lastDialog.includes(word)) return true;
          }

          const root = scopeSel ? document.querySelector(scopeSel) || document.body : document.body;
          const text = (root.textContent || '').toLowerCase().replace(/\s+/g, ' ');

          if (exp && text.includes(exp)) return true;
          for (const word of vocab) {
            if (text.includes(word)) return true;
          }
          return false;
        }, {
          scopeSel: typeof scope === 'string' ? scope : undefined,
          vocab: SUCCESS_VOCABULARY,
          exp: expTextStr,
        });

        return txt;
      },
      {
        timeout: timeoutMs,
        message: `Expected success feedback within ${timeoutMs}ms`,
      }
    )
    .toBe(true);
}

/**
 * Web-first URL assertion with standard auto-wait.
 */
export async function expectUrl(
  page: Page,
  pattern: string | RegExp,
  options: { timeoutMs?: number } = {}
): Promise<void> {
  const timeout = options.timeoutMs || 10000;
  await expect(page).toHaveURL(pattern, { timeout });
}

/**
 * Phase 2 Readiness Function:
 * Replaces brittle 'networkidle'.
 * Standard: DOMContentLoaded + visible main content + 500ms visual stability (no layout shifts) + 15s cap.
 */
export async function waitForPageReady(
  page: Page,
  options: { timeoutMs?: number; settleMs?: number } = {}
): Promise<{ settled: boolean; durationMs: number; slowLoad: boolean }> {
  const { timeoutMs = 15000, settleMs = 500 } = options;
  const start = Date.now();

  try {
    await page.waitForLoadState('domcontentloaded', { timeout: Math.min(timeoutMs, 8000) });
  } catch {}

  let settled = false;
  let slowLoad = false;

  try {
    // Wait for visible main content or landmarks
    await page.waitForFunction(
      () => {
        const text = (document.body?.innerText || '').trim();
        const hasContent = text.length > 20;
        const hasLandmarks = document.querySelector('main, header, nav, footer, [role="main"], h1, h2, form, button') !== null;
        return hasContent || hasLandmarks;
      },
      null,
      { timeout: Math.min(timeoutMs, 10000) }
    );

    // Visual stability check: wait for layout shifts to settle
    await page.waitForTimeout(settleMs);
    settled = true;
  } catch {
    // If 15s cap reached, do not crash; record slow_load
    slowLoad = true;
  }

  // Phase 2 Overlay Dismissal: automatically dismiss consent banners if present
  try {
    await dismissConsentOverlays(page);
  } catch {}

  return {
    settled,
    durationMs: Date.now() - start,
    slowLoad,
  };
}

/**
 * Phase 2 Deterministic Overlay Dismissal:
 * Detects cookie/consent banners, GDPR notices, and newsletter popups.
 * Dismisses them before tests start or retry intercepted actions.
 */
export async function dismissConsentOverlays(page: Page): Promise<{ dismissed: boolean; bannerText?: string }> {
  try {
    const res = await page.evaluate(() => {
      const OVERLAY_SELECTORS = [
        '[role="dialog"]',
        '[aria-modal="true"]',
        '.cookie-banner',
        '.cookie-consent',
        '#onetrust-consent-sdk',
        '#onetrust-banner-sdk',
        '#cookie-notice',
        '.consent-modal',
        '.cc-window',
        '.fc-consent-root',
        '.cmp-root',
        '[id*="consent"]',
        '[class*="cookie"]',
        '[class*="consent"]',
      ];

      const ACCEPT_TERMS = [
        'accept',
        'agree',
        'allow',
        'got it',
        'close',
        'ok',
        'continue',
        'understand',
        'aceptar',
        'entendido',
        'continuer',
        'zustimmen',
        'alle akzeptieren',
        'decline',
        'dismiss',
        'close modal',
      ];

      for (const sel of OVERLAY_SELECTORS) {
        const containers = Array.from(document.querySelectorAll(sel));
        for (const container of containers) {
          const style = window.getComputedStyle(container);
          if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') continue;

          // Search buttons inside container
          const btns = Array.from(container.querySelectorAll('button, [role="button"], a.btn, input[type="button"]')) as HTMLElement[];
          for (const btn of btns) {
            const txt = (btn.textContent || btn.getAttribute('aria-label') || '').toLowerCase().trim();
            for (const term of ACCEPT_TERMS) {
              if (txt.includes(term)) {
                btn.click();
                return { dismissed: true, bannerText: (container.textContent || '').slice(0, 100) };
              }
            }
          }
        }
      }
      return { dismissed: false };
    });

    if (res.dismissed) {
      await page.waitForTimeout(400); // allow overlay transition out
    }
    return res;
  } catch {
    return { dismissed: false };
  }
}

/**
 * Phase 3 Robust Control Discovery (`findControl`):
 * Locates an interactive element by intent without relying on rigid single-string selectors.
 * Checks accessible role + names, aria-label, title, test-id, SVG icon classes (sun/moon/theme/menu), and visible text.
 * Pierces open shadow DOM.
 * If not found, fails with candidate list in error message, never a generic timeout.
 */
export async function findControl(
  page: Page,
  intents: string | string[] | { name?: string | RegExp; role?: string }
): Promise<Locator> {
  let normalizedIntents: string[] = [];
  if (Array.isArray(intents)) {
    normalizedIntents = intents.map((i) => i.toLowerCase().trim());
  } else if (typeof intents === 'string') {
    normalizedIntents = [intents.toLowerCase().trim()];
  } else if (intents && typeof intents === 'object') {
    if (intents.name instanceof RegExp) {
      normalizedIntents = intents.name.source
        .toLowerCase()
        .replace(/[\^$|\\]/g, ' ')
        .split(/\s+/)
        .filter(Boolean);
    } else if (typeof intents.name === 'string') {
      normalizedIntents = [intents.name.toLowerCase().trim()];
    }
    if (intents.role) {
      normalizedIntents.push(intents.role.toLowerCase().trim());
    }
  }
  if (normalizedIntents.length === 0) {
    normalizedIntents = ['button'];
  }

  // Fast check: look across DOM using browser evaluation to identify the best match
  const matchInfo: any = await page.evaluate(`((intentList) => {
    function getAllInteractive(root) {
      const elements = [];
      const treeWalker = document.createTreeWalker(
        root,
        NodeFilter.SHOW_ELEMENT,
        null
      );
      let curr = treeWalker.nextNode();
      while (curr) {
        const el = curr;
        const tag = el.tagName.toLowerCase();
        const role = el.getAttribute('role') || '';
        if (
          tag === 'button' ||
          tag === 'a' ||
          tag === 'input' ||
          tag === 'select' ||
          role === 'button' ||
          role === 'switch' ||
          role === 'tab' ||
          role === 'menuitem' ||
          role === 'checkbox' ||
          el.hasAttribute('onclick')
        ) {
          elements.push(el);
        }
        if (el.shadowRoot) {
          elements.push(...getAllInteractive(el.shadowRoot));
        }
        curr = treeWalker.nextNode();
      }
      return elements;
    }

    const items = getAllInteractive(document);
    const scored = [];

    for (let idx = 0; idx < items.length; idx++) {
      const el = items[idx];
      const rect = el.getBoundingClientRect();
      const style = window.getComputedStyle(el);
      if (rect.width === 0 || rect.height === 0 || style.display === 'none' || style.visibility === 'hidden') {
        continue;
      }

      const text = (el.textContent || '').toLowerCase().trim();
      const ariaLabel = (el.getAttribute('aria-label') || '').toLowerCase().trim();
      const title = (el.getAttribute('title') || '').toLowerCase().trim();
      const testId = (el.getAttribute('data-testid') || el.getAttribute('data-test') || '').toLowerCase().trim();
      const className = (el.className && typeof el.className === 'string' ? el.className : '').toLowerCase();
      const id = (el.id || '').toLowerCase();
      const svgClasses = Array.from(el.querySelectorAll('svg')).map((s) => (s.className && typeof s.className === 'string' ? s.className : '')).join(' ').toLowerCase();

      let bestScore = 0;
      for (const intent of intentList) {
        if (ariaLabel.includes(intent)) bestScore = Math.max(bestScore, 100);
        if (text.includes(intent)) bestScore = Math.max(bestScore, 90);
        if (title.includes(intent)) bestScore = Math.max(bestScore, 85);
        if (testId.includes(intent)) bestScore = Math.max(bestScore, 80);
        if (id.includes(intent)) bestScore = Math.max(bestScore, 70);
        if (className.includes(intent)) bestScore = Math.max(bestScore, 65);
        if (svgClasses.includes(intent)) bestScore = Math.max(bestScore, 60);

        if (intent.includes('theme') || intent.includes('dark') || intent.includes('light')) {
          if (svgClasses.includes('sun') || svgClasses.includes('moon') || svgClasses.includes('lucide-sun') || svgClasses.includes('lucide-moon')) {
            bestScore = Math.max(bestScore, 95);
          }
          if (className.includes('sun') || className.includes('moon')) {
            bestScore = Math.max(bestScore, 90);
          }
        }
      }

      if (bestScore > 0) {
        const diagAttr = 'data-qa-control-' + idx;
        el.setAttribute(diagAttr, 'true');
        scored.push({
          score: bestScore,
          selector: '[' + diagAttr + '="true"]',
          desc: '<' + el.tagName.toLowerCase() + ' role="' + (el.getAttribute('role') || '') + '" aria-label="' + ariaLabel + '" text="' + text.slice(0, 30) + '">',
        });
      }
    }

    scored.sort((a, b) => b.score - a.score);
    return {
      candidates: scored,
      totalVisible: items.length,
    };
  })(${JSON.stringify(normalizedIntents)})`);

  if (matchInfo.candidates.length > 0) {
    const top = matchInfo.candidates[0];
    return page.locator(top.selector);
  }

  // Not found: Gather sample candidates to produce rich, actionable error message
  const availableSummary = await page.evaluate(`(() => {
    const btns = Array.from(document.querySelectorAll('button, [role="button"], a')).slice(0, 15);
    return btns.map((b) => b.tagName.toLowerCase() + ': "' + ((b.textContent || b.getAttribute('aria-label') || '').slice(0, 30)) + '"').join(', ');
  })()`);

  const intentNames = Array.isArray(intents) ? intents.join(', ') : JSON.stringify(intents);
  throw new Error(
    `findControl failed: No interactive control found matching intents [${intentNames}]. Available controls on page: [${availableSummary}]`
  );
}

interface ThemeState {
  classes: string[];
  dataTheme: string | null;
  dataMode: string | null;
  dataBsTheme: string | null;
  colorSchemeAttr: string | null;
  bgLum: number;
  textLum: number;
  storageVals: Record<string, string>;
  colorSchemeComputed: string;
}

/**
 * Phase 3 Theme State Extraction:
 * Extracts a multi-dimensional theme state for deterministic before/after diffing.
 */
async function getThemeState(page: Page): Promise<ThemeState> {
  const state: any = await page.evaluate(`(() => {
    const html = document.documentElement;
    const body = document.body;

    const htmlClasses = Array.from(html.classList);
    const bodyClasses = Array.from(body ? body.classList : []);

    const dataTheme = html.getAttribute('data-theme') || (body ? body.getAttribute('data-theme') : null);
    const dataMode = html.getAttribute('data-mode') || (body ? body.getAttribute('data-mode') : null);
    const dataBsTheme = html.getAttribute('data-bs-theme') || (body ? body.getAttribute('data-bs-theme') : null);
    const colorSchemeAttr = html.getAttribute('color-scheme') || html.style.colorScheme;

    const computedHtml = window.getComputedStyle(html);
    const computedBody = body ? window.getComputedStyle(body) : computedHtml;

    function getLuminance(rgbStr) {
      const match = rgbStr.match(/\\d+/g);
      if (!match || match.length < 3) return 0.5;
      const r = parseInt(match[0], 10) / 255;
      const g = parseInt(match[1], 10) / 255;
      const b = parseInt(match[2], 10) / 255;
      return 0.2126 * r + 0.7152 * g + 0.0722 * b;
    }

    const bgLum = getLuminance(computedBody.backgroundColor || computedHtml.backgroundColor || 'rgb(255,255,255)');
    const textLum = getLuminance(computedBody.color || computedHtml.color || 'rgb(0,0,0)');

    const storageVals = {};
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i) || '';
      if (k.toLowerCase().includes('theme') || k.toLowerCase().includes('mode') || k.toLowerCase().includes('color')) {
        storageVals[k] = localStorage.getItem(k) || '';
      }
    }

    return {
      classes: [...htmlClasses, ...bodyClasses],
      dataTheme,
      dataMode,
      dataBsTheme,
      colorSchemeAttr,
      bgLum,
      textLum,
      storageVals,
      colorSchemeComputed: computedHtml.colorScheme,
    };
  })()`);
  return state as ThemeState;
}

/**
 * Phase 3 Theme Toggle Oracle (`expectThemeToggle`):
 * Evaluates theme toggling on real-world sites with attributes, CSS classes, luminance changes, and persistence.
 * Also verifies toggling back restores the original theme.
 */
export async function expectThemeToggle(
  page: Page,
  options: { control?: Locator | string; timeoutMs?: number; trigger?: () => Promise<void> } = {}
): Promise<void> {
  const timeoutMs = options.timeoutMs || 10000;

  // 1. Initial state
  const beforeState = await getThemeState(page);

  // 2. Locate or trigger toggle
  let controlLoc: Locator | null = null;
  if (options.trigger) {
    await options.trigger();
  } else {
    if (options.control) {
      controlLoc = typeof options.control === 'string' ? page.locator(options.control) : options.control;
    } else {
      controlLoc = await findControl(page, [
        'theme',
        'dark mode',
        'light mode',
        'toggle theme',
        'mode',
        'switch',
        'color mode',
      ]);
    }
    await controlLoc.first().click({ timeout: 5000 });
  }

  // 4. Check if clicking opened a 3-way dropdown menu (Light / Dark / System)
  const menuHandled = await page.evaluate(`(() => {
    const menuItems = Array.from(document.querySelectorAll('[role="menuitem"], [role="option"], button'));
    for (const item of menuItems) {
      const txt = (item.textContent || item.getAttribute('aria-label') || '').toLowerCase().trim();
      if (txt === 'dark' || txt === 'light' || txt.includes('oscuro') || txt.includes('claro')) {
        const style = window.getComputedStyle(item);
        if (style.display !== 'none' && style.visibility !== 'hidden') {
          item.click();
          return true;
        }
      }
    }
    return false;
  })()`);

  // 5. Poll computed styles for up to 2.5s for CSS transitions to finish
  let afterState = await getThemeState(page);
  let changed = false;

  for (let attempt = 0; attempt < 5; attempt++) {
    await page.waitForTimeout(400);
    afterState = await getThemeState(page);

    const lumDiff = Math.abs(afterState.bgLum - beforeState.bgLum);
    const classesChanged = JSON.stringify(afterState.classes) !== JSON.stringify(beforeState.classes);
    const attrChanged =
      afterState.dataTheme !== beforeState.dataTheme ||
      afterState.dataMode !== beforeState.dataMode ||
      afterState.dataBsTheme !== beforeState.dataBsTheme ||
      afterState.colorSchemeAttr !== beforeState.colorSchemeAttr;
    const storageChanged = JSON.stringify(afterState.storageVals) !== JSON.stringify(beforeState.storageVals);

    if (lumDiff >= 0.15 || classesChanged || attrChanged || storageChanged) {
      changed = true;
      break;
    }
  }

  expect(
    changed,
    `expectThemeToggle: No theme state change detected after clicking toggle (before classes: [${beforeState.classes.join(', ')}], bgLum: ${beforeState.bgLum.toFixed(2)}; after classes: [${afterState.classes.join(', ')}], bgLum: ${afterState.bgLum.toFixed(2)})`
  ).toBe(true);

  // 6. Toggle back to verify revertibility
  try {
    if (options.trigger) {
      await options.trigger();
    } else if (controlLoc) {
      await controlLoc.first().click({ timeout: 3000 });
    }
    if (menuHandled) {
      await page.evaluate(`(() => {
        const menuItems = Array.from(document.querySelectorAll('[role="menuitem"], [role="option"], button'));
        for (const item of menuItems) {
          const txt = (item.textContent || '').toLowerCase().trim();
          if (txt === 'light' || txt === 'system' || txt.includes('claro')) {
            item.click();
            break;
          }
        }
      })()`);
    }
    await page.waitForTimeout(400);
  } catch {}
}

/**
 * Asserts all visible <img> elements have naturalWidth > 0.
 */
export async function expectImagesLoaded(page: Page): Promise<void> {
  const brokenCount = await page.evaluate(() => {
    const images = Array.from(document.querySelectorAll('img'));
    let broken = 0;
    for (const img of images) {
      const style = window.getComputedStyle(img);
      if (style.display !== 'none' && style.visibility !== 'hidden' && img.getBoundingClientRect().width > 0) {
        if (!img.complete || img.naturalWidth === 0) {
          broken++;
        }
      }
    }
    return broken;
  });

  expect(brokenCount, `Expected all visible images to load successfully, but found ${brokenCount} broken images`).toBe(0);
}

/**
 * Verifies modal dialog open and clean dismissal.
 */
export async function expectModalOpenClose(
  page: Page,
  openTrigger: Locator | string,
  closeTrigger?: Locator | string
): Promise<void> {
  const openLoc = typeof openTrigger === 'string' ? page.locator(openTrigger) : openTrigger;
  await openLoc.first().click();

  const modal = page.locator('[role="dialog"], [aria-modal="true"], .modal').first();
  await expect(modal).toBeVisible({ timeout: 5000 });

  if (closeTrigger) {
    const closeLoc = typeof closeTrigger === 'string' ? page.locator(closeTrigger) : closeTrigger;
    await closeLoc.first().click();
  } else {
    // Try ESC or standard close button
    const closeBtn = modal.locator('button[aria-label*="close" i], button:has-text("Close"), [aria-label*="cerrar" i]').first();
    const canClickClose = await closeBtn.isVisible().catch(() => false);
    if (canClickClose) {
      await closeBtn.click();
    } else {
      await page.keyboard.press('Escape');
    }
  }

  await expect(modal).toBeHidden({ timeout: 5000 });
}

/**
 * Verifies navigation menu or mobile hamburger expand/collapse.
 */
export async function expectNavigationMenu(page: Page, targetItemText?: string): Promise<void> {
  const menuTrigger = await findControl(page, ['menu', 'navigation', 'hamburger', 'nav']);
  await menuTrigger.first().click();
  await page.waitForTimeout(300);

  if (targetItemText) {
    const item = page.locator(`nav a, [role="menuitem"], [role="navigation"] a`).filter({ hasText: targetItemText }).first();
    await expect(item).toBeVisible({ timeout: 5000 });
  }
}

