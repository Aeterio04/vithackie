// Drives the REAL website in Chromium: register, logout, login, wrong password, guard redirect, session expiry,
// "MCP-created data appears on the dashboard", and per-user isolation in the UI.
//
//   node scripts/verify_auth_ui.mjs [--web http://localhost:3000] [--api http://localhost:8000]
//
// Needs the backend and the built website running, and Playwright (borrowed from apps/runner). Creates throwaway users.
import { createRequire } from "node:module";
import { mkdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(path.join(here, "..", "apps", "runner", "package.json"));
const { chromium } = require("playwright");

const arg = (name, dflt) => { const i = process.argv.indexOf(name); return i > 0 ? process.argv[i + 1] : dflt; };
const WEB = arg("--web", "http://localhost:3000");
const API = arg("--api", "http://localhost:8000");
const shots = path.join(here, "..", "kawach_ui_screenshots");
mkdirSync(shots, { recursive: true });

const tag = Math.random().toString(36).slice(2, 8);
const emailA = `ui-a-${tag}@example.com`, emailB = `ui-b-${tag}@example.com`, pw = `Ui-${tag}-pass-9!`;
let failures = 0;
const check = (name, ok, detail = "") => { console.log(`${ok ? "PASS" : "FAIL"}  ${name}${!ok && detail ? `   [${detail}]` : ""}`); if (!ok) failures++; };

const browser = await chromium.launch();
const newPage = async () => { const ctx = await browser.newContext(); const page = await ctx.newPage(); return { ctx, page }; };
const api = async (method, url, { token, body } = {}) => {
  const r = await fetch(API + url, { method, headers: { "content-type": "application/json", ...(token ? { authorization: `Bearer ${token}` } : {}) }, body: body ? JSON.stringify(body) : undefined });
  return { status: r.status, json: await r.json().catch(() => null) };
};

try {
  // 1. guard: signed-out visitor is sent to login and returned afterwards
  let { ctx, page } = await newPage();
  await page.goto(`${WEB}/projects`);
  check("signed-out /projects redirects to /login with returnUrl", page.url().includes("/login") && decodeURIComponent(page.url()).includes("returnUrl=/projects"), page.url());
  await page.goto(`${WEB}/results`);
  check("signed-out /results also redirects", page.url().includes("/login"), page.url());

  // 2. register validation
  await page.goto(`${WEB}/register`);
  await page.fill("#email", emailA);
  await page.fill("#password", pw);
  await page.fill("#confirm_password", pw + "x");
  await page.click("button[type=submit]");
  check("register: mismatched passwords show an error", await page.getByText("Passwords do not match").isVisible());
  await page.fill("#password", "short");
  await page.fill("#confirm_password", "short");
  await page.click("button[type=submit]");
  check("register: short password rejected client-side", await page.getByText("at least 8 characters").first().isVisible());
  check("register: show/hide password toggle exists", (await page.locator("button[type=button]").count()) > 0);

  // 3. register succeeds -> logged in, lands on /projects, email shown, cookie is httpOnly
  await page.fill("#password", pw);
  await page.fill("#confirm_password", pw);
  await page.fill("#display_name", "UI Tester");
  await Promise.all([page.waitForURL("**/projects", { timeout: 20000 }), page.click("button[type=submit]")]);
  check("register: auto-login lands on /projects", page.url().endsWith("/projects"), page.url());
  await page.waitForTimeout(1500);
  check("navbar/sidebar shows the logged-in email", await page.getByText(emailA).first().isVisible());
  const cookies = await ctx.cookies();
  const session = cookies.find((c) => c.name === "auth_token");
  check("session cookie is httpOnly + SameSite=Lax", !!session && session.httpOnly && session.sameSite === "Lax", JSON.stringify(session && { h: session.httpOnly, s: session.sameSite }));
  check("JS cannot read the token (document.cookie)", !(await page.evaluate(() => document.cookie)).includes("auth_token"));
  check("token is not in localStorage", !(await page.evaluate(() => JSON.stringify({ ...localStorage }))).includes("eyJ"));
  await page.screenshot({ path: path.join(shots, "1-after-register.png") });

  // 4. MCP-style API client with the SAME account creates data -> visible on the website
  const loginA = await api("POST", "/api/v1/auth/login", { body: { email: emailA, password: pw } });
  const projName = `Made by MCP ${tag}`;
  const proj = await api("POST", "/api/v1/projects", { token: loginA.json.token, body: { name: projName, targetUrl: "http://localhost:4000" } });
  check("MCP-style (Bearer) call creates a project for the same account", proj.status === 201);
  await page.goto(`${WEB}/projects`);
  await page.waitForTimeout(2000);
  check("that project appears on the website dashboard", await page.getByText(projName).first().isVisible());
  await page.screenshot({ path: path.join(shots, "2-mcp-project-on-dashboard.png") });

  // 5. logout
  await page.getByRole("button", { name: /log out/i }).click();
  await page.waitForURL("**/login**", { timeout: 15000 });
  check("logout returns to /login", page.url().includes("/login"), page.url());
  await page.goto(`${WEB}/projects`);
  check("after logout, /projects is guarded again", page.url().includes("/login"), page.url());
  check("after logout the session cookie is gone", !(await ctx.cookies()).some((c) => c.name === "auth_token" && c.value));

  // 6. wrong password / unknown user show the SAME message and stay on the login page
  await page.goto(`${WEB}/login`);
  await page.fill("#username_or_email", emailA);
  await page.fill("#password", "totally-wrong-pw");
  await page.click("button[type=submit]");
  await page.waitForTimeout(1200);
  const msgWrong = await page.locator("div[role=alert]:not([id])").innerText();
  check("login: wrong password shows 'Invalid email or password'", msgWrong.includes("Invalid email or password"), msgWrong);
  await page.fill("#username_or_email", `nobody-${tag}@example.com`);
  await page.click("button[type=submit]");
  await page.waitForTimeout(1200);
  const msgUnknown = await page.locator("div[role=alert]:not([id])").innerText();
  check("login: unknown email shows the identical message", msgUnknown === msgWrong, msgUnknown);
  check("login: still on /login", page.url().includes("/login"));
  await page.screenshot({ path: path.join(shots, "3-wrong-password.png") });

  // 7. duplicate registration (different case)
  await page.goto(`${WEB}/register`);
  await page.fill("#email", emailA.toUpperCase());
  await page.fill("#password", pw);
  await page.fill("#confirm_password", pw);
  await page.click("button[type=submit]");
  await page.waitForTimeout(1500);
  check("register: duplicate email (other case) says it already exists", (await page.locator("div[role=alert]:not([id])").innerText()).includes("already exists"));

  // 8. login success returns to the intended page
  await page.goto(`${WEB}/login?returnUrl=%2Fresults`);
  await page.fill("#username_or_email", emailA);
  await page.fill("#password", pw);
  await Promise.all([page.waitForURL("**/results", { timeout: 20000 }), page.click("button[type=submit]")]);
  check("login: redirected back to the intended page (/results)", page.url().endsWith("/results"), page.url());
  await page.goto(`${WEB}/login?returnUrl=https%3A%2F%2Fevil.example`);
  check("signed-in user on /login with hostile returnUrl is not sent off-site", new URL(page.url()).origin === new URL(WEB).origin);

  // 9. session expiry: corrupt the cookie -> proxy lets the page load, API says 401 -> login with notice
  await ctx.addCookies(cookies.filter((c) => c.name === "auth_token").map((c) => ({ ...c, value: "expired.invalid.token" })));
  await page.goto(`${WEB}/projects`);
  await page.waitForURL("**/login**", { timeout: 20000 });
  check("expired/invalid session sends the user to /login with reason=expired", page.url().includes("reason=expired"), page.url());
  check("login page explains the session expired", await page.getByText("Your session has expired").first().isVisible());
  await page.screenshot({ path: path.join(shots, "4-session-expired.png") });
  await ctx.close();

  // 10. a different user sees none of A's data in the UI
  const regB = await api("POST", "/api/v1/auth/register", { body: { email: emailB, password: pw } });
  check("second user registers", regB.status === 200);
  ({ ctx, page } = await newPage());
  await page.goto(`${WEB}/login`);
  await page.fill("#username_or_email", emailB);
  await page.fill("#password", pw);
  await Promise.all([page.waitForURL("**/projects", { timeout: 20000 }), page.click("button[type=submit]")]);
  await page.waitForTimeout(2000);
  check("user B's dashboard does not show A's project", !(await page.getByText(projName).count()));
  check("user B sees his own email, not A's", (await page.getByText(emailB).count()) > 0 && !(await page.getByText(emailA).count()));
  await page.screenshot({ path: path.join(shots, "5-user-b-empty.png") });
  const peek = await page.evaluate(async (id) => (await fetch(`/api/v1/projects/${id}`, { credentials: "include" })).status, proj.json.id);
  check("user B's browser gets 404 for A's project id", peek === 404, String(peek));
  await ctx.close();
} catch (e) {
  console.log(`FAIL  script error: ${e.message}`);
  failures++;
} finally {
  await browser.close();
}
console.log(`\n${failures ? failures + " CHECK(S) FAILED" : "ALL UI CHECKS PASSED"}   (screenshots: ${shots})`);
process.exit(failures ? 1 : 0);
