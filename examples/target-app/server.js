import express from 'express';
import crypto from 'node:crypto';

const app = express();
const PORT = process.env.PORT || 4000;

app.use(express.urlencoded({ extended: false }));
app.use(express.json());

// In-memory data store
let users = {};        // email -> { email, password }
let sessions = {};     // sid -> email
let items = {};        // email -> [{ id, title }]
let displayNames = {}; // email -> string
let saveCount = 0;     // global counter for settings saves
let nextItemId = 0;

const ALL_BUGS = ['GT01', 'GT02', 'GT03', 'GT04', 'GT05', 'GT06', 'GT07', 'GT08', 'GT09'];

export function bugOn(id) {
  const bugsOff = (process.env.BUGS_OFF || '').trim();
  if (bugsOff.toLowerCase() === 'all') return false;
  const offList = bugsOff.split(',').map(s => s.trim().toUpperCase());
  return !offList.includes(id.toUpperCase());
}

function resetState() {
  users = {};
  sessions = {};
  items = {};
  displayNames = {};
  saveCount = 0;
  nextItemId = 0;

  // Seed user
  const seedEmail = 'qa.tester@example.com';
  users[seedEmail] = {
    email: seedEmail,
    password: 'Passw0rd!23',
  };
  items[seedEmail] = [];
  displayNames[seedEmail] = 'QA Tester';
}

resetState();

function parseCookies(req) {
  const list = {};
  const header = req.headers.cookie;
  if (!header) return list;
  header.split(';').forEach(cookie => {
    const parts = cookie.split('=');
    if (parts.length >= 2) {
      list[parts[0].trim()] = decodeURIComponent(parts.slice(1).join('=').trim());
    }
  });
  return list;
}

function getSessionUser(req) {
  const cookies = parseCookies(req);
  const sid = cookies.sid;
  if (!sid || !sessions[sid]) return null;
  const email = sessions[sid];
  return users[email] || null;
}

function createSession(res, email) {
  const sid = crypto.randomBytes(16).toString('hex');
  sessions[sid] = email;
  res.setHeader('Set-Cookie', `sid=${sid}; HttpOnly; SameSite=Lax; Path=/`);
  return sid;
}

function destroySession(req, res) {
  const cookies = parseCookies(req);
  const sid = cookies.sid;
  if (sid && sessions[sid]) {
    delete sessions[sid];
  }
  res.setHeader('Set-Cookie', 'sid=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0');
}

function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function layout({ title, user, content, headExtra = '' }) {
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${escapeHtml(title)} - TaskBoard</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: system-ui, -apple-system, sans-serif; background: #f4f6f8; color: #222; line-height: 1.5; padding: 24px; }
    .card { max-width: 480px; margin: 0 auto; background: #fff; padding: 32px; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.08); }
    header { margin-bottom: 24px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #eee; padding-bottom: 12px; }
    .app-title { font-size: 1.25rem; font-weight: 700; color: #111; }
    nav { display: flex; gap: 12px; align-items: center; font-size: 0.9rem; }
    nav a { color: #0066cc; text-decoration: none; }
    nav a:hover { text-decoration: underline; }
    main { margin-top: 16px; }
    h1 { font-size: 1.5rem; margin-bottom: 16px; color: #111; }
    label { display: block; margin-top: 12px; margin-bottom: 4px; font-weight: 500; font-size: 0.9rem; }
    input[type="text"], input[type="email"], input[type="password"] { width: 100%; padding: 8px 12px; border: 1px solid #ccc; border-radius: 4px; font-size: 1rem; }
    button { display: inline-block; margin-top: 16px; padding: 8px 16px; background: #0066cc; color: #fff; border: none; border-radius: 4px; font-size: 0.95rem; cursor: pointer; }
    button:hover { background: #0052a3; }
    button.link-button { background: none; border: none; color: #0066cc; padding: 0; margin: 0; cursor: pointer; font-size: 0.9rem; }
    button.link-button:hover { text-decoration: underline; }
    p[role="alert"] { background: #ffebee; color: #c62828; padding: 8px 12px; border-radius: 4px; margin-bottom: 12px; font-size: 0.9rem; }
    p[role="status"] { background: #e8f5e9; color: #2e7d32; padding: 8px 12px; border-radius: 4px; margin-bottom: 12px; font-size: 0.9rem; }
    ul[aria-label="Items"] { list-style: none; margin-top: 16px; }
    ul[aria-label="Items"] li { display: flex; justify-content: space-between; align-items: center; padding: 8px 0; border-bottom: 1px solid #f0f0f0; }
    .mt-4 { margin-top: 16px; }
    .text-muted { color: #666; font-size: 0.9rem; }
  </style>
  ${headExtra}
</head>
<body>
  <div class="card">
    <header>
      <div class="app-title">TaskBoard</div>
      ${user ? `
      <nav>
        <a href="/dashboard">Dashboard</a>
        <a href="/settings">Settings</a>
        <form method="post" action="/logout" style="display:inline;">
          <button type="submit" class="link-button">Log out</button>
        </form>
      </nav>
      ` : ''}
    </header>
    <main>
      ${content}
    </main>
  </div>
</body>
</html>`;
}

// ---------------- Routes ---------------- //

// GET / : redirect 302 to /dashboard if signed in, else /login
app.get('/', (req, res) => {
  const user = getSessionUser(req);
  if (user) {
    return res.redirect(302, '/dashboard');
  }
  return res.redirect(302, '/login');
});

// GET /signup : ALWAYS renders the form, even when signed in
app.get('/signup', (req, res) => {
  const content = `
    <h1>Create your account</h1>
    <form method="post" action="/signup">
      <label for="email">Email</label>
      <input type="email" id="email" name="email">
      <label for="password">Password</label>
      <input type="password" id="password" name="password">
      <button type="submit">Sign up</button>
    </form>
    <p class="mt-4"><a href="/login">Already have an account? Log in</a></p>
  `;
  res.send(layout({ title: 'Sign up', user: null, content }));
});

// POST /signup : lower-case and trim email
app.post('/signup', (req, res) => {
  const rawEmail = req.body.email || '';
  const email = rawEmail.trim().toLowerCase();
  const password = req.body.password || '';

  const renderError = (errorMsg) => {
    const content = `
      <h1>Create your account</h1>
      <p role="alert">${escapeHtml(errorMsg)}</p>
      <form method="post" action="/signup">
        <label for="email">Email</label>
        <input type="email" id="email" name="email" value="${escapeHtml(rawEmail)}">
        <label for="password">Password</label>
        <input type="password" id="password" name="password">
        <button type="submit">Sign up</button>
      </form>
      <p class="mt-4"><a href="/login">Already have an account? Log in</a></p>
    `;
    return res.status(200).send(layout({ title: 'Sign up', user: null, content }));
  };

  // 1. Email format check
  // BUG GT01: skip this check
  if (!bugOn('GT01')) {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(email)) {
      return renderError('Enter a valid email address');
    }
  }

  // 2. Password length check
  // BUG GT02: the check is length < 4 instead
  const minLength = bugOn('GT02') ? 4 : 8;
  if (password.length < minLength) {
    return renderError('Password must be at least 8 characters');
  }

  // 3. Email exists check
  if (users[email]) {
    return renderError('An account with this email already exists');
  }

  // 4. Create user and session
  users[email] = { email, password };
  items[email] = [];
  displayNames[email] = email.split('@')[0];
  createSession(res, email);
  return res.redirect(302, '/dashboard');
});

// GET /login : ALWAYS renders the form even when signed in
app.get('/login', (req, res) => {
  const content = `
    <h1>Log in</h1>
    <form method="post" action="/login">
      <label for="email">Email</label>
      <input type="email" id="email" name="email">
      <label for="password">Password</label>
      <input type="password" id="password" name="password">
      <button type="submit">Log in</button>
    </form>
    <p class="mt-4"><a href="/signup">Create an account</a></p>
  `;
  res.send(layout({ title: 'Log in', user: null, content }));
});

// POST /login : look user up by lower-cased email; compare passwords exactly
app.post('/login', (req, res) => {
  const rawEmail = req.body.email || '';
  const password = req.body.password || '';

  // BUG GT04: do NOT lower-case the submitted email, so "QA.Tester@Example.com" fails to find the user
  const lookupEmail = bugOn('GT04') ? rawEmail.trim() : rawEmail.trim().toLowerCase();

  const user = users[lookupEmail];
  if (!user || user.password !== password) {
    // BUG GT03: on failure re-render the form with NO message at all
    const alertHtml = bugOn('GT03') ? '' : '<p role="alert">Invalid email or password</p>';
    const content = `
      <h1>Log in</h1>
      ${alertHtml}
      <form method="post" action="/login">
        <label for="email">Email</label>
        <input type="email" id="email" name="email" value="${escapeHtml(rawEmail)}">
        <label for="password">Password</label>
        <input type="password" id="password" name="password">
        <button type="submit">Log in</button>
      </form>
      <p class="mt-4"><a href="/signup">Create an account</a></p>
    `;
    return res.status(200).send(layout({ title: 'Log in', user: null, content }));
  }

  createSession(res, user.email);
  return res.redirect(302, '/dashboard');
});

// GET /dashboard : requires a session, else redirect 302 /login
app.get('/dashboard', (req, res) => {
  const user = getSessionUser(req);
  if (!user) {
    return res.redirect(302, '/login');
  }

  // Response header Cache-Control
  // BUG GT07: send "Cache-Control: private, max-age=600" instead
  if (bugOn('GT07')) {
    res.setHeader('Cache-Control', 'private, max-age=600');
  } else {
    res.setHeader('Cache-Control', 'no-store');
  }

  const userItems = items[user.email] || [];
  const itemsListHtml = userItems.length === 0
    ? '<p>No items yet</p>'
    : `<ul aria-label="Items">
        ${userItems.map(item => `
          <li>
            <span>${escapeHtml(item.title)}</span>
            <form method="post" action="/dashboard/items/${item.id}/delete" style="display:inline;">
              <button type="submit" aria-label="Delete ${escapeHtml(item.title)}">Delete</button>
            </form>
          </li>
        `).join('')}
      </ul>`;

  const content = `
    <h1>Dashboard</h1>
    <p class="text-muted">Signed in as ${escapeHtml(user.email)}</p>
    <form method="post" action="/dashboard/items" class="mt-4">
      <label for="title">Item title</label>
      <input type="text" id="title" name="title">
      <button type="submit">Add item</button>
    </form>
    ${itemsListHtml}
  `;

  return res.send(layout({ title: 'Dashboard', user, content }));
});

// POST /dashboard/items : trim the title
app.post('/dashboard/items', (req, res) => {
  const user = getSessionUser(req);
  if (!user) return res.redirect(302, '/login');

  const rawTitle = req.body.title || '';
  const title = rawTitle.trim();

  // BUG GT05: accept the empty title and add the item
  if (!bugOn('GT05')) {
    if (title === '') {
      const userItems = items[user.email] || [];
      const itemsListHtml = userItems.length === 0
        ? '<p>No items yet</p>'
        : `<ul aria-label="Items">
            ${userItems.map(item => `
              <li>
                <span>${escapeHtml(item.title)}</span>
                <form method="post" action="/dashboard/items/${item.id}/delete" style="display:inline;">
                  <button type="submit" aria-label="Delete ${escapeHtml(item.title)}">Delete</button>
                </form>
              </li>
            `).join('')}
          </ul>`;

      const content = `
        <h1>Dashboard</h1>
        <p role="alert">Title is required</p>
        <p class="text-muted">Signed in as ${escapeHtml(user.email)}</p>
        <form method="post" action="/dashboard/items" class="mt-4">
          <label for="title">Item title</label>
          <input type="text" id="title" name="title">
          <button type="submit">Add item</button>
        </form>
        ${itemsListHtml}
      `;
      return res.status(200).send(layout({ title: 'Dashboard', user, content }));
    }
  }

  nextItemId++;
  items[user.email] = items[user.email] || [];
  items[user.email].push({ id: nextItemId, title });
  return res.redirect(302, '/dashboard');
});

// POST /dashboard/items/:id/delete : remove item
app.post('/dashboard/items/:id/delete', (req, res) => {
  const user = getSessionUser(req);
  if (!user) return res.redirect(302, '/login');

  const deleteId = parseInt(req.params.id, 10);
  const userList = items[user.email] || [];

  if (userList.length > 0) {
    // BUG GT06: remove the FIRST item of the user's list instead of the item with that id
    if (bugOn('GT06')) {
      userList.shift();
    } else {
      const idx = userList.findIndex(item => item.id === deleteId);
      if (idx !== -1) {
        userList.splice(idx, 1);
      }
    }
  }

  return res.redirect(302, '/dashboard');
});

// GET /settings : requires a session, else redirect /login
app.get('/settings', (req, res) => {
  const user = getSessionUser(req);
  if (!user) return res.redirect(302, '/login');

  const displayName = displayNames[user.email] || '';

  // BUG GT08: include an inline <script> that logs console error and throws uncaught TypeError
  const headExtra = bugOn('GT08')
    ? `<script>console.error("Failed to load preferences"); document.title = window.__prefs.theme;</script>`
    : '';

  const content = `
    <h1>Settings</h1>
    <form method="post" action="/settings">
      <label for="displayName">Display name</label>
      <input type="text" id="displayName" name="displayName" value="${escapeHtml(displayName)}">
      <button type="submit">Save settings</button>
    </form>
  `;

  return res.send(layout({ title: 'Settings', user, content, headExtra }));
});

// POST /settings : increment global saveCount
app.post('/settings', (req, res) => {
  const user = getSessionUser(req);
  if (!user) return res.redirect(302, '/login');

  saveCount++;

  // BUG GT09: if saveCount is even, respond HTTP 500 with a tiny page and do not save
  if (bugOn('GT09') && saveCount % 2 === 0) {
    return res.status(500).send('<h1>Internal Server Error</h1>');
  }

  const rawName = req.body.displayName || '';
  displayNames[user.email] = rawName.trim();

  // Re-render settings page with <p role="status">Settings saved</p>
  const headExtra = bugOn('GT08')
    ? `<script>console.error("Failed to load preferences"); document.title = window.__prefs.theme;</script>`
    : '';

  const content = `
    <h1>Settings</h1>
    <p role="status">Settings saved</p>
    <form method="post" action="/settings">
      <label for="displayName">Display name</label>
      <input type="text" id="displayName" name="displayName" value="${escapeHtml(displayNames[user.email])}">
      <button type="submit">Save settings</button>
    </form>
  `;

  return res.status(200).send(layout({ title: 'Settings', user, content, headExtra }));
});

// POST /logout : destroy session, clear cookie, redirect 302 /login
app.post('/logout', (req, res) => {
  destroySession(req, res);
  return res.redirect(302, '/login');
});

// GET|POST /__reset : wipe and re-seed state, respond JSON {"ok":true}
app.all('/__reset', (req, res) => {
  resetState();
  return res.json({ ok: true });
});

// GET /__bugs : respond JSON {"enabled":[...ids of bugs currently on...]}
app.get('/__bugs', (req, res) => {
  const enabled = ALL_BUGS.filter(id => bugOn(id));
  return res.json({ enabled });
});

// Unknown paths: 404 with simple page "Not found"
app.use((req, res) => {
  res.status(404).send('<!DOCTYPE html><html><head><title>Not found</title></head><body><h1>Not found</h1></body></html>');
});

if (process.env.NODE_ENV !== 'test') {
  app.listen(PORT, () => {
    console.log(`Target app on http://localhost:${PORT}`);
  });
}

export default app;
