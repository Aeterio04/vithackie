// qa_benchmark/deployed_sim/server.js
// Deterministic Deployed-Site Simulator for KAWACH / Ordinous QA Platform

const http = require('node:http');
const url = require('node:url');

const PORT = parseInt(process.env.PORT || '4500', 10);
let flakyCounter = 0;

const server = http.createServer((req, res) => {
  const parsedUrl = url.parse(req.url, true);
  const pathname = parsedUrl.pathname;
  const method = req.method.toUpperCase();
  const ua = req.headers['user-agent'] || '';
  const qaToken = req.headers['x-qa-token'];

  // CORS headers
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, HEAD, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, X-QA-Token, Authorization, Range');

  if (method === 'OPTIONS') {
    res.writeHead(204);
    res.end();
    return;
  }

  // 1. WAF Blocked Simulation
  if (pathname === '/waf-blocked') {
    if (qaToken === 'test-qa-token-123') {
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
      res.end('<h1>WAF Bypass Success: X-QA-Token Verified</h1><p>Welcome, authorized test runner.</p>');
      return;
    }
    if (ua.includes('HeadlessChrome') || ua.includes('bot') || ua.includes('crawler') || !ua.includes('Mozilla/5.0')) {
      res.writeHead(403, { 'Content-Type': 'text/html; charset=utf-8' });
      res.end('<h1>403 Forbidden: Security Challenge Intercept</h1><p>Automated headless requests are blocked by Cloudflare WAF.</p>');
      return;
    }
    // Standard desktop browser allowed
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    res.end('<h1>Welcome to Protected Site</h1><p>Standard desktop browser verified.</p>');
    return;
  }

  // 2. HEAD 405 Method Not Allowed Simulation (Tests GET Range fallback)
  if (pathname === '/api/head-405') {
    if (method === 'HEAD') {
      res.writeHead(405, {
        'Allow': 'GET, POST',
        'Content-Type': 'application/json',
      });
      res.end();
      return;
    }
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ status: 'ok', method, message: 'GET probe succeeded after HEAD 405' }));
    return;
  }

  // 3. Flaky 502 Bad Gateway Simulation (Fails on 1st request, recovers on 2nd)
  if (pathname === '/api/flaky-gateway') {
    flakyCounter++;
    if (flakyCounter % 2 === 1) {
      res.writeHead(502, { 'Content-Type': 'text/html; charset=utf-8' });
      res.end('<h1>502 Bad Gateway</h1><p>Origin web server returned an invalid response.</p>');
      return;
    }
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ status: 'ok', requestNum: flakyCounter, message: 'Gateway recovered on retry' }));
    return;
  }

  // 4. Cookie Consent Banner Simulation
  if (pathname === '/consent-banner') {
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    res.end(`<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Consent Banner Test</title>
  <style>
    body { font-family: sans-serif; padding: 40px; margin: 0; }
    #consent-banner {
      position: fixed;
      bottom: 0; left: 0; right: 0;
      background: #0f172a;
      color: #f8fafc;
      padding: 24px;
      z-index: 999999;
      display: flex;
      justify-content: space-between;
      align-items: center;
      box-shadow: 0 -4px 12px rgba(0,0,0,0.2);
    }
    #accept-cookies {
      background: #2563eb;
      color: white;
      border: none;
      padding: 10px 20px;
      border-radius: 6px;
      font-weight: 600;
      cursor: pointer;
    }
    .main-content { margin-top: 20px; }
    .action-btn {
      padding: 12px 24px;
      background: #10b981;
      color: white;
      border: none;
      border-radius: 6px;
      cursor: pointer;
      font-size: 16px;
    }
  </style>
</head>
<body>
  <div id="consent-banner">
    <div>
      <strong>Cookie Notice:</strong> We use cookies to measure site performance and security.
    </div>
    <button id="accept-cookies" aria-label="Accept all cookies">Accept All</button>
  </div>
  <div class="main-content">
    <h1>Consent Overlay Simulator</h1>
    <p>This button tests interactions behind consent overlays.</p>
    <button id="target-action" class="action-btn">Perform Protected Action</button>
    <div id="action-result" style="margin-top: 15px; font-weight: bold; color: #10b981;"></div>
  </div>
  <script>
    document.getElementById('accept-cookies').addEventListener('click', function() {
      document.getElementById('consent-banner').style.display = 'none';
    });
    document.getElementById('target-action').addEventListener('click', function() {
      document.getElementById('action-result').textContent = 'Action executed successfully!';
    });
  </script>
</body>
</html>`);
    return;
  }

  // 5. Dark / Light Theme Toggle Variants Simulation
  if (pathname === '/theme-test') {
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    res.end(`<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
  <meta charset="UTF-8">
  <title>Theme Toggle Test</title>
  <style>
    :root {
      --bg-color: #ffffff;
      --text-color: #0f172a;
      --card-bg: #f1f5f9;
    }
    [data-theme="dark"], body.dark {
      --bg-color: #0f172a;
      --text-color: #f8fafc;
      --card-bg: #1e293b;
    }
    body {
      background-color: var(--bg-color);
      color: var(--text-color);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      padding: 40px;
      margin: 0;
      transition: background-color 0.2s ease, color 0.2s ease;
    }
    .header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-bottom: 1px solid #cbd5e1;
      padding-bottom: 20px;
    }
    #theme-toggle {
      background: none;
      border: 1px solid #94a3b8;
      border-radius: 8px;
      padding: 8px 12px;
      cursor: pointer;
      color: var(--text-color);
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .card {
      background: var(--card-bg);
      padding: 24px;
      border-radius: 8px;
      margin-top: 24px;
    }
  </style>
</head>
<body>
  <div class="header">
    <h2>Theme Switcher Demo</h2>
    <button id="theme-toggle" role="button" aria-label="Toggle theme" title="Toggle dark/light mode">
      <svg id="theme-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="12" cy="12" r="5"></circle>
        <line x1="12" y1="1" x2="12" y2="3"></line>
        <line x1="12" y1="21" x2="12" y2="23"></line>
      </svg>
      <span id="theme-text" style="display:none;">Toggle</span>
    </button>
  </div>
  <div class="card">
    <h3>Application Content</h3>
    <p>This page tests theme toggle oracles across luminance, attributes, CSS custom properties, and localStorage.</p>
    <p id="current-mode">Current mode: light</p>
  </div>
  <script>
    const btn = document.getElementById('theme-toggle');
    const modeLabel = document.getElementById('current-mode');

    // Read stored theme
    const stored = localStorage.getItem('theme');
    if (stored === 'dark') {
      document.documentElement.setAttribute('data-theme', 'dark');
      document.body.classList.add('dark');
      modeLabel.textContent = 'Current mode: dark';
    }

    btn.addEventListener('click', function() {
      const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
      const next = isDark ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', next);
      if (next === 'dark') {
        document.body.classList.add('dark');
      } else {
        document.body.classList.remove('dark');
      }
      localStorage.setItem('theme', next);
      modeLabel.textContent = 'Current mode: ' + next;
    });
  </script>
</body>
</html>`);
    return;
  }

  // 6. SPA Routing Simulation
  if (pathname === '/spa') {
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    res.end(`<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>SPA Router Demo</title>
  <style>
    body { font-family: sans-serif; padding: 40px; }
    nav a { margin-right: 15px; font-weight: bold; text-decoration: none; color: #2563eb; }
    #view { margin-top: 30px; padding: 20px; border: 1px solid #e2e8f0; border-radius: 8px; }
  </style>
</head>
<body>
  <nav>
    <a href="#/home" id="tab-home">Home</a>
    <a href="#/dashboard" id="tab-dashboard">Dashboard</a>
    <a href="#/settings" id="tab-settings">Settings</a>
  </nav>
  <div id="view">
    <h2 id="view-title">Home Page</h2>
    <p id="view-desc">Welcome to the client-rendered single page app.</p>
  </div>
  <script>
    function render() {
      const hash = window.location.hash || '#/home';
      const title = document.getElementById('view-title');
      const desc = document.getElementById('view-desc');
      if (hash.includes('dashboard')) {
        title.textContent = 'Analytics Dashboard';
        desc.textContent = 'Metrics, charts, and telemetry data rendered.';
      } else if (hash.includes('settings')) {
        title.textContent = 'User Settings';
        desc.textContent = 'Profile preferences, notifications, and security.';
      } else {
        title.textContent = 'Home Page';
        desc.textContent = 'Welcome to the client-rendered single page app.';
      }
    }
    window.addEventListener('hashchange', render);
    render();
  </script>
</body>
</html>`);
    return;
  }

  // Default Landing Page
  res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
  res.end(`<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>KAWACH Deployed Sites Simulator</title>
  <style>
    body { font-family: sans-serif; padding: 40px; line-height: 1.6; max-width: 800px; margin: auto; }
    h1 { color: #1e293b; }
    li { margin-bottom: 12px; }
    code { background: #f1f5f9; padding: 2px 6px; border-radius: 4px; font-size: 14px; }
  </style>
</head>
<body>
  <h1>KAWACH Deployed-Site Simulator</h1>
  <p>Mock server exercising edge cases found in deployed web environments:</p>
  <ul>
    <li><a href="/waf-blocked">/waf-blocked</a> - Simulates Cloudflare/AWS WAF challenge against headless bots; passes on desktop Chrome UA or <code>X-QA-Token: test-qa-token-123</code>.</li>
    <li><a href="/api/head-405">/api/head-405</a> - Returns 405 Method Not Allowed on HEAD, 200 on GET (tests GET range fallback).</li>
    <li><a href="/api/flaky-gateway">/api/flaky-gateway</a> - Returns 502 Bad Gateway on first hit, recovers to 200 OK on retry.</li>
    <li><a href="/consent-banner">/consent-banner</a> - Cookie consent banner overlay blocking underlying actions.</li>
    <li><a href="/theme-test">/theme-test</a> - Dark/light mode theme toggle button with SVG icon, aria-label, CSS custom properties, and localStorage.</li>
    <li><a href="/spa">/spa</a> - Client-side hash routing SPA.</li>
  </ul>
</body>
</html>`);
});

server.listen(PORT, '127.0.0.1', () => {
  console.log(`Deployed-Site Simulator running at http://127.0.0.1:${PORT}`);
});

process.on('SIGTERM', () => server.close());
process.on('SIGINT', () => server.close());
