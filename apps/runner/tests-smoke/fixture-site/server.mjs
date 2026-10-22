/**
 * Zero-dependency local HTTP fixture site for testing explore.ts crawler.
 * Run with: node server.mjs
 * Port: 5055
 */

import http from 'node:http';

const PORT = 5055;

const server = http.createServer((req, res) => {
  const url = new URL(req.url || '/', `http://localhost:${PORT}`);
  const cookies = req.headers['cookie'] || '';
  const isAuthenticated = cookies.includes('session=authenticated');

  // Handle POST /login
  if (req.method === 'POST' && url.pathname === '/login') {
    res.writeHead(302, {
      'Set-Cookie': 'session=authenticated; Path=/',
      'Location': '/home',
    });
    return res.end();
  }

  // Handle routes
  if (url.pathname === '/') {
    res.writeHead(302, { 'Location': '/login' });
    return res.end();
  }

  if (url.pathname === '/login') {
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    return res.end(`
      <!DOCTYPE html>
      <html>
        <head><title>Sign in - Fixture Site</title></head>
        <body>
          <h1>Sign In</h1>
          <form method="POST" action="/login">
            <label for="email">Email</label>
            <input type="email" id="email" name="email" required />
            <label for="password">Password</label>
            <input type="password" id="password" name="password" required />
            <button type="submit">Sign In</button>
          </form>
        </body>
      </html>
    `);
  }

  if (url.pathname === '/home') {
    if (!isAuthenticated) {
      res.writeHead(302, { 'Location': '/login' });
      return res.end();
    }
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    return res.end(`
      <!DOCTYPE html>
      <html>
        <head><title>Home Dashboard</title></head>
        <body>
          <h1>Welcome Home</h1>
          <nav>
            <a href="/about">About Us</a>
            <a href="/items">Manage Items</a>
            <a href="/logout">Log out</a>
            <a href="/__secret">Secret Admin</a>
          </nav>
        </body>
      </html>
    `);
  }

  if (url.pathname === '/items') {
    if (!isAuthenticated) {
      res.writeHead(302, { 'Location': '/login' });
      return res.end();
    }
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    return res.end(`
      <!DOCTYPE html>
      <html>
        <head><title>Items Management</title></head>
        <body>
          <h1>Items</h1>
          <form method="POST" action="/items">
            <label for="item_name">Item Name</label>
            <input type="text" id="item_name" name="item_name" placeholder="Enter title" />
            <button type="submit">Add Item</button>
          </form>
          <a href="/home">Back Home</a>
        </body>
      </html>
    `);
  }

  if (url.pathname === '/about') {
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    return res.end(`
      <!DOCTYPE html>
      <html>
        <head><title>About</title></head>
        <body>
          <h1>About Fixture Site</h1>
          <p>Plain text description of the app.</p>
          <a href="/home">Home</a>
        </body>
      </html>
    `);
  }

  if (url.pathname === '/__secret') {
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    return res.end(`<h1>Super Secret Path</h1>`);
  }

  if (url.pathname === '/logout') {
    res.writeHead(302, {
      'Set-Cookie': 'session=; Path=/; Expires=Thu, 01 Jan 1970 00:00:00 GMT',
      'Location': '/login',
    });
    return res.end();
  }

  res.writeHead(404, { 'Content-Type': 'text/plain' });
  res.end('Not Found');
});

server.listen(PORT, () => {
  console.log(`Fixture server listening on http://localhost:${PORT}`);
});
