const express = require('express');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 3100;

app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// Feature toggles from env BUGS (comma-separated list, e.g. "login-no-error,cart-total-wrong")
function isBugActive(bugId) {
  const bugsEnv = (process.env.BUGS || '').split(',').map((b) => b.trim().toLowerCase());
  return bugsEnv.includes(bugId.toLowerCase());
}

// In-memory data store with reset capability
let users = new Map([
  ['seed.user@example.com', { password: 'Password123!', name: 'Seed User' }],
  ['qa.tester@example.com', { password: 'Passw0rd!23', name: 'QA Tester' }],
]);

let products = [
  { id: '1', name: 'Wireless Noise-Cancelling Headphones', price: 99.99, category: 'Electronics', image: '/images/headphones.png', description: 'Premium wireless headphones with active noise cancellation.' },
  { id: '2', name: 'Mechanical Gaming Keyboard', price: 69.50, category: 'Accessories', image: '/images/keyboard.png', description: 'RGB backlit mechanical keyboard with tactile switches.' },
  { id: '3', name: 'Ergonomic Office Chair', price: 189.00, category: 'Furniture', image: '/images/chair.png', description: 'Adjustable lumbar support ergonomic chair.' },
  { id: '4', name: 'USB-C Fast Charging Hub', price: 29.99, category: 'Electronics', image: '/images/hub.png', description: 'Multi-port USB-C adapter with 4K HDMI output.' },
];

let carts = new Map(); // sessionId/ip -> items

let slowLoadTriggered = false;
let flakyAccessCounter = 0;

// Session extraction with cookie support
function getSessionId(req, res) {
  let cookieHeader = req.headers.cookie || '';
  let match = cookieHeader.match(/shop_session=([^;]+)/);
  if (match) return match[1];
  if (req.headers['x-session-id']) return req.headers['x-session-id'];
  const newId = 'sess_' + Math.random().toString(36).substring(2, 10);
  if (res && res.setHeader) {
    res.setHeader('Set-Cookie', `shop_session=${newId}; Path=/`);
  }
  return newId;
}

// Reset endpoint
app.post('/api/reset', (req, res) => {
  const sessionId = req.headers['x-session-id'] || (req.headers.cookie && req.headers.cookie.match(/shop_session=([^;]+)/)?.[1]);
  if (sessionId && carts.has(sessionId)) {
    carts.delete(sessionId);
  } else {
    carts.clear();
  }
  users = new Map([
    ['seed.user@example.com', { password: 'Password123!', name: 'Seed User' }],
    ['qa.tester@example.com', { password: 'Passw0rd!23', name: 'QA Tester' }],
  ]);
  slowLoadTriggered = false;
  flakyAccessCounter = 0;
  res.json({ ok: true, message: 'Benchmark state reset successfully.' });
});

// Dynamic image server
app.get('/images/:filename', (req, res) => {
  const { filename } = req.params;
  if (filename.includes('non-existent')) {
    return res.status(404).send('Image not found');
  }
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200"><rect width="200" height="200" fill="#cbd5e1"/><text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" fill="#475569" font-family="sans-serif" font-size="14">${filename}</text></svg>`;
  res.setHeader('Content-Type', 'image/svg+xml');
  res.send(svg);
});

// K6: Harmless third-party style noise - Favicon 404
app.get('/favicon.ico', (req, res) => {
  res.status(404).send('Favicon not found');
});

// Common header HTML
function renderHeader(activePage = '') {
  return `
    <header style="background: #1e293b; color: white; padding: 12px 24px; display: flex; justify-content: space-between; align-items: center;">
      <div style="font-size: 20px; font-weight: bold;"><a href="/" style="color: white; text-decoration: none;">ShopDemo</a></div>
      <nav style="display: flex; gap: 18px;">
        <a href="/" style="color: ${activePage === 'home' ? '#38bdf8' : '#e2e8f0'}; text-decoration: none; font-weight: 500;">Products</a>
        <a href="/cart" style="color: ${activePage === 'cart' ? '#38bdf8' : '#e2e8f0'}; text-decoration: none; font-weight: 500;">Cart</a>
        <a href="/login" style="color: ${activePage === 'login' ? '#38bdf8' : '#e2e8f0'}; text-decoration: none; font-weight: 500;">Log In</a>
        <a href="/signup" style="color: ${activePage === 'signup' ? '#38bdf8' : '#e2e8f0'}; text-decoration: none; font-weight: 500;">Sign Up</a>
      </nav>
    </header>
    <script>
      // K6: Harmless third-party style noise
      console.info('Analytics initialized (mocked third-party library)');
    </script>
  `;
}

// 1. Home / Product List Page
app.get('/', (req, res) => {
  flakyAccessCounter++;

  // K7: Slow first load on initial visit if configured
  const delay = !slowLoadTriggered && req.query.slow ? 2500 : 0;
  slowLoadTriggered = true;

  setTimeout(() => {
    let productCards = products.map((p) => {
      let displayPrice = `$${p.price.toFixed(2)}`;
      // B8 planted defect: price shows NaN for product 3
      if (isBugActive('price-format') && p.id === '3') {
        displayPrice = '$NaN';
      }

      let imgUrl = p.image;
      // B6 planted defect: product image 404
      if (isBugActive('broken-image') && p.id === '2') {
        imgUrl = '/images/non-existent-image-404.png';
      }

      // B7 planted defect: flaky random banner / missing buy button on 1 in 3 loads
      const isFlakyOmission = isBugActive('flaky-random') && flakyAccessCounter % 3 === 0 && p.id === '1';

      return `
        <div class="product-card" data-testid="product-${p.id}" style="border: 1px solid #cbd5e1; border-radius: 8px; padding: 16px; width: 220px; display: flex; flex-direction: column; justify-content: space-between;">
          <img src="${imgUrl}" alt="${p.name}" style="width: 100%; height: 140px; object-fit: cover; border-radius: 4px; background: #f1f5f9;" onerror="this.onerror=null; this.dataset.failed=true;">
          <h3 style="font-size: 15px; margin: 10px 0 6px;"><a href="/products/${p.id}" style="color: #0f172a; text-decoration: none;">${p.name}</a></h3>
          <p style="font-size: 12px; color: #64748b; margin: 0 0 10px;">${p.category}</p>
          <div style="display: flex; justify-content: space-between; align-items: center; margin-top: auto;">
            <span class="product-price" style="font-weight: bold; font-size: 16px;">${displayPrice}</span>
            ${
              isFlakyOmission
                ? `<span style="color: #ef4444; font-size: 11px;">[Error: Component load failed]</span>`
                : `<button onclick="addToCart('${p.id}')" data-testid="add-to-cart-${p.id}" style="background: #2563eb; color: white; border: none; padding: 6px 12px; border-radius: 4px; cursor: pointer;">Add to Cart</button>`
            }
          </div>
        </div>
      `;
    }).join('');

    res.send(`
      <!DOCTYPE html>
      <html lang="en">
      <head>
        <meta charset="UTF-8">
        <title>ShopDemo - Products Catalog</title>
        <style>
          body { font-family: system-ui, sans-serif; margin: 0; background: #f8fafc; color: #0f172a; }
          .container { max-width: 1040px; margin: 30px auto; padding: 0 20px; }
          .grid { display: flex; flex-wrap: wrap; gap: 20px; }
        </style>
      </head>
      <body>
        ${renderHeader('home')}
        <div class="container">
          <h1 style="font-size: 24px; margin-bottom: 20px;">Products</h1>
          <div class="grid">${productCards}</div>
        </div>
        <script>
          async function addToCart(productId) {
            await fetch('/api/cart', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ productId, quantity: 1 })
            });
            alert('Item added to cart!');
          }
        </script>
      </body>
      </html>
    `);
  }, delay);
});

// 2. Product Detail Page
app.get('/products/:id', (req, res) => {
  const product = products.find((p) => p.id === req.params.id);
  if (!product) {
    return res.status(404).send('Product not found');
  }

  // B5 planted defect: silent console error on product page
  const injectSilentError = isBugActive('silent-console-error');

  res.send(`
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8">
      <title>${product.name} - ShopDemo</title>
      <style>
        body { font-family: system-ui, sans-serif; margin: 0; background: #f8fafc; color: #0f172a; }
        .container { max-width: 800px; margin: 30px auto; padding: 0 20px; }
      </style>
      ${
        injectSilentError
          ? `<script>
              window.addEventListener('DOMContentLoaded', () => {
                // Planted Defect B5: Uncaught TypeError in product telemetry
                setTimeout(() => {
                  window.__telemetry.track('product_view'); // Throws Uncaught TypeError: Cannot read properties of undefined
                }, 50);
              });
            </script>`
          : ''
      }
    </head>
    <body>
      ${renderHeader()}
      <div class="container">
        <a href="/" style="display: inline-block; margin-bottom: 16px; color: #2563eb; text-decoration: none;">&larr; Back to Products</a>
        <div style="background: white; border: 1px solid #cbd5e1; border-radius: 8px; padding: 24px; display: flex; gap: 24px;">
          <img src="${product.image}" alt="${product.name}" style="width: 260px; height: 260px; object-fit: cover; border-radius: 4px; background: #f1f5f9;">
          <div>
            <h1 style="font-size: 22px; margin-top: 0;">${product.name}</h1>
            <p style="color: #64748b;">Category: ${product.category}</p>
            <p style="font-size: 20px; font-weight: bold; color: #0f172a;">$${product.price.toFixed(2)}</p>
            <p style="margin: 16px 0 24px; line-height: 1.5;">${product.description}</p>
            <button onclick="addToCart('${product.id}')" data-testid="detail-add-to-cart" style="background: #2563eb; color: white; border: none; padding: 10px 20px; font-size: 15px; border-radius: 4px; cursor: pointer;">Add to Cart</button>
          </div>
        </div>
      </div>
      <script>
        async function addToCart(productId) {
          await fetch('/api/cart', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ productId, quantity: 1 })
          });
          alert('Item added to cart!');
        }
      </script>
    </body>
    </html>
  `);
});

// 3. Cart Page
app.get('/cart', (req, res) => {
  const sessionId = getSessionId(req, res);
  const cartItems = carts.get(sessionId) || [];

  let subtotal = 0;
  const itemsWithProduct = cartItems.map((item) => {
    const prod = products.find((p) => p.id === item.productId);
    const itemTotal = prod ? prod.price * item.quantity : 0;
    subtotal += itemTotal;
    return { ...item, product: prod, itemTotal };
  });

  // B2 planted defect: cart-total-wrong ignores quantity > 1
  let effectiveSubtotal = subtotal;
  if (isBugActive('cart-total-wrong')) {
    effectiveSubtotal = itemsWithProduct.reduce((sum, item) => sum + (item.product ? item.product.price * 1 : 0), 0);
  }

  const tax = Math.round(effectiveSubtotal * 0.10 * 100) / 100;
  const total = effectiveSubtotal + tax;

  res.send(`
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8">
      <title>Shopping Cart - ShopDemo</title>
      <style>
        body { font-family: system-ui, sans-serif; margin: 0; background: #f8fafc; color: #0f172a; }
        .container { max-width: 800px; margin: 30px auto; padding: 0 20px; }
        table { width: 100%; border-collapse: collapse; margin-top: 16px; background: white; }
        th, td { padding: 12px; border-bottom: 1px solid #e2e8f0; text-align: left; }
      </style>
    </head>
    <body>
      ${renderHeader('cart')}
      <div class="container">
        <h1>Your Cart</h1>
        ${
          itemsWithProduct.length === 0
            ? '<p data-testid="empty-cart-msg">Your cart is empty.</p>'
            : `
              <table>
                <thead>
                  <tr><th>Product</th><th>Quantity</th><th>Unit Price</th><th>Total</th></tr>
                </thead>
                <tbody>
                  ${itemsWithProduct.map((it) => `
                    <tr data-testid="cart-row-${it.productId}">
                      <td>${it.product?.name}</td>
                      <td>${it.quantity}</td>
                      <td>$${it.product?.price.toFixed(2)}</td>
                      <td>$${it.itemTotal.toFixed(2)}</td>
                    </tr>
                  `).join('')}
                </tbody>
              </table>
              <div style="margin-top: 20px; text-align: right; background: white; padding: 16px; border-radius: 8px; border: 1px solid #e2e8f0;">
                <p>Subtotal: <span data-testid="cart-subtotal">$${effectiveSubtotal.toFixed(2)}</span></p>
                <p>Tax (10%): <span data-testid="cart-tax">$${tax.toFixed(2)}</span></p>
                <h3 style="margin-top: 8px;">Total: <span data-testid="cart-total">$${total.toFixed(2)}</span></h3>
                <a href="/checkout" data-testid="proceed-checkout-btn" style="display: inline-block; background: #16a34a; color: white; padding: 10px 20px; border-radius: 4px; text-decoration: none; font-weight: 500;">Proceed to Checkout</a>
              </div>
            `
        }

        <!-- K4: Open Shadow DOM discount box with error feedback -->
        <div style="margin-top: 24px;">
          <discount-box></discount-box>
        </div>

        <!-- K4: Iframe with support feedback -->
        <div style="margin-top: 20px;">
          <h4>Order Support & Questions</h4>
          <iframe id="support-frame" src="/iframe-support" style="width: 100%; height: 90px; border: 1px solid #cbd5e1; border-radius: 6px;"></iframe>
        </div>
      </div>

      <script>
        // Custom Element implementing open shadow root (K4)
        class DiscountBox extends HTMLElement {
          constructor() {
            super();
            const shadow = this.attachShadow({ mode: 'open' });
            shadow.innerHTML = \`
              <style>
                .box { background: #f1f5f9; padding: 14px; border-radius: 6px; border: 1px solid #cbd5e1; }
                input { padding: 6px 10px; border: 1px solid #94a3b8; border-radius: 4px; }
                button { padding: 6px 12px; background: #334155; color: white; border: none; border-radius: 4px; cursor: pointer; }
                .msg { margin-top: 8px; font-size: 13px; color: #dc2626; font-weight: 500; }
              </style>
              <div class="box">
                <label for="code" style="font-size: 13px; font-weight: 600; display: block; margin-bottom: 4px;">Promo Code:</label>
                <input id="code" type="text" placeholder="Enter code">
                <button id="apply-btn">Apply</button>
                <div id="discount-feedback" class="msg" style="display: none;" role="alert">Invalid discount coupon code</div>
              </div>
            \`;
            shadow.getElementById('apply-btn').addEventListener('click', () => {
              const code = shadow.getElementById('code').value;
              if (code !== 'VALID10') {
                shadow.getElementById('discount-feedback').style.display = 'block';
              }
            });
          }
        }
        customElements.define('discount-box', DiscountBox);
      </script>
    </body>
    </html>
  `);
});

// Iframe route for K4
app.get('/iframe-support', (req, res) => {
  res.send(`
    <!DOCTYPE html>
    <html>
    <head><style>body { font-family: system-ui, sans-serif; margin: 10px; font-size: 13px; }</style></head>
    <body>
      <form id="contact-form" onsubmit="event.preventDefault(); document.getElementById('iframe-err').style.display = 'block';">
        <span>Need assistance? </span>
        <input type="text" id="query" placeholder="Question topic" style="padding: 4px 8px;">
        <button type="submit" style="padding: 4px 8px;">Ask</button>
        <span id="iframe-err" style="display: none; color: #dc2626; margin-left: 10px;" role="status">Support desk is temporarily offline</span>
      </form>
    </body>
    </html>
  `);
});

// API Cart Operations
app.post('/api/cart', (req, res) => {
  const sessionId = getSessionId(req, res);
  const { productId, quantity = 1 } = req.body;
  if (!carts.has(sessionId)) {
    carts.set(sessionId, []);
  }
  const cart = carts.get(sessionId);
  const existing = cart.find((i) => i.productId === productId);
  if (existing) {
    existing.quantity += Number(quantity);
  } else {
    cart.push({ productId, quantity: Number(quantity) });
  }
  res.json({ ok: true, cart });
});

// 4. Login Page
app.get('/login', (req, res) => {
  res.send(`
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8">
      <title>Sign In - ShopDemo</title>
      <style>
        body { font-family: system-ui, sans-serif; margin: 0; background: #f8fafc; color: #0f172a; }
        .container { max-width: 400px; margin: 50px auto; padding: 24px; background: white; border-radius: 8px; border: 1px solid #cbd5e1; }
        .form-group { margin-bottom: 16px; }
        label { display: block; font-weight: 500; margin-bottom: 6px; }
        input[type="text"], input[type="email"], input[type="password"] { width: 100%; box-sizing: border-box; padding: 8px 12px; border: 1px solid #94a3b8; border-radius: 4px; }
        button { width: 100%; padding: 10px; background: #2563eb; color: white; border: none; border-radius: 4px; font-size: 15px; font-weight: 500; cursor: pointer; }
        .alert-error { margin-top: 14px; padding: 10px; background: #fee2e2; color: #991b1b; border: 1px solid #f87171; border-radius: 4px; font-size: 13px; }
      </style>
    </head>
    <body>
      ${renderHeader('login')}
      <div class="container">
        <h2 style="margin-top: 0;">Sign In</h2>
        <form id="login-form">
          <div class="form-group">
            <label for="email">Email Address</label>
            <input type="email" id="email" name="email" required value="qa.tester@example.com">
          </div>
          <div class="form-group">
            <label for="password">Password</label>
            <input type="password" id="password" name="password" required>
          </div>
          <button type="submit" id="login-submit" data-testid="login-submit-btn">Log In</button>
          <!-- Toast/Alert for K1 & K2 -->
          <div id="login-error-toast" class="alert-error" role="alert" style="display: none;"></div>
        </form>
      </div>

      <script>
        document.getElementById('login-form').addEventListener('submit', async (e) => {
          e.preventDefault();
          const email = document.getElementById('email').value;
          const password = document.getElementById('password').value;
          const toast = document.getElementById('login-error-toast');
          toast.style.display = 'none';

          const res = await fetch('/api/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password })
          });
          const data = await res.json();

          if (data.ok) {
            window.location.href = '/';
          } else {
            // If B1 is active, show NO error message
            if (data.suppressMessage) {
              return;
            }

            // K2: Error toast appears after 1.5 second delay
            setTimeout(() => {
              // K1: Wording is "Incorrect email or password" (different from spec's "Invalid credentials")
              toast.textContent = data.error || 'Incorrect email or password';
              toast.style.display = 'block';
            }, 1500);
          }
        });
      </script>
    </body>
    </html>
  `);
});

app.post('/api/login', (req, res) => {
  const { email, password } = req.body;
  const user = users.get((email || '').toLowerCase().trim());

  if (user && user.password === password) {
    return res.json({ ok: true, user: { email, name: user.name } });
  }

  // Planted defect B1: wrong password shows NO message
  if (isBugActive('login-no-error')) {
    return res.status(401).json({ ok: false, suppressMessage: true });
  }

  // K1: Wording "Incorrect email or password"
  return res.status(401).json({ ok: false, error: 'Incorrect email or password' });
});

// 5. Signup Page (K3: native HTML5 validation, K8: existing email trap)
app.get('/signup', (req, res) => {
  res.send(`
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8">
      <title>Sign Up - ShopDemo</title>
      <style>
        body { font-family: system-ui, sans-serif; margin: 0; background: #f8fafc; color: #0f172a; }
        .container { max-width: 400px; margin: 50px auto; padding: 24px; background: white; border-radius: 8px; border: 1px solid #cbd5e1; }
        .form-group { margin-bottom: 16px; }
        label { display: block; font-weight: 500; margin-bottom: 6px; }
        input[type="text"], input[type="email"], input[type="password"] { width: 100%; box-sizing: border-box; padding: 8px 12px; border: 1px solid #94a3b8; border-radius: 4px; }
        button { width: 100%; padding: 10px; background: #2563eb; color: white; border: none; border-radius: 4px; font-size: 15px; font-weight: 500; cursor: pointer; }
        .alert-error { margin-top: 14px; padding: 10px; background: #fee2e2; color: #991b1b; border: 1px solid #f87171; border-radius: 4px; font-size: 13px; }
      </style>
    </head>
    <body>
      ${renderHeader('signup')}
      <div class="container">
        <h2 style="margin-top: 0;">Create Account</h2>
        <form id="signup-form">
          <div class="form-group">
            <label for="name">Full Name</label>
            <input type="text" id="name" name="name" required>
          </div>
          <div class="form-group">
            <label for="email">Email Address</label>
            <!-- K3: type="email" triggers native HTML5 validation bubble unless B3 active -->
            <input type="${isBugActive('signup-accepts-invalid-email') ? 'text' : 'email'}" id="email" name="email" required>
          </div>
          <div class="form-group">
            <label for="password">Password</label>
            <input type="password" id="password" name="password" minlength="8" required>
          </div>
          <button type="submit" id="signup-submit" data-testid="signup-submit-btn">Sign Up</button>
          <div id="signup-error" class="alert-error" role="alert" style="display: none;"></div>
        </form>
      </div>

      <script>
        document.getElementById('signup-form').addEventListener('submit', async (e) => {
          e.preventDefault();
          const name = document.getElementById('name').value;
          const email = document.getElementById('email').value;
          const password = document.getElementById('password').value;
          const errDiv = document.getElementById('signup-error');
          errDiv.style.display = 'none';

          const res = await fetch('/api/signup', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, email, password })
          });
          const data = await res.json();

          if (data.ok) {
            alert('Account created successfully!');
            window.location.href = '/login';
          } else {
            errDiv.textContent = data.error || 'Signup failed';
            errDiv.style.display = 'block';
          }
        });
      </script>
    </body>
    </html>
  `);
});

app.post('/api/signup', (req, res) => {
  const { name, email, password } = req.body;
  const cleanEmail = (email || '').toLowerCase().trim();

  // B3 planted defect: server accepts invalid email
  const isInvalidEmail = !cleanEmail.includes('@') || !cleanEmail.includes('.');
  if (isInvalidEmail && !isBugActive('signup-accepts-invalid-email')) {
    return res.status(400).json({ ok: false, error: 'Enter a valid email address' });
  }

  // K8: Test data reuse trap - already registered email error
  if (users.has(cleanEmail)) {
    return res.status(409).json({ ok: false, error: 'Email address already registered' });
  }

  if (!password || password.length < 8) {
    return res.status(400).json({ ok: false, error: 'Password must be at least 8 characters' });
  }

  users.set(cleanEmail, { password, name });
  return res.status(201).json({ ok: true });
});

// 6. Checkout Page (K5: empty cart block, B4: checkout 500)
app.get('/checkout', (req, res) => {
  const sessionId = getSessionId(req, res);
  const cartItems = carts.get(sessionId) || [];

  res.send(`
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8">
      <title>Checkout - ShopDemo</title>
      <style>
        body { font-family: system-ui, sans-serif; margin: 0; background: #f8fafc; color: #0f172a; }
        .container { max-width: 600px; margin: 30px auto; padding: 24px; background: white; border-radius: 8px; border: 1px solid #cbd5e1; }
        .form-group { margin-bottom: 14px; }
        label { display: block; font-weight: 500; margin-bottom: 4px; }
        input[type="text"] { width: 100%; box-sizing: border-box; padding: 8px 10px; border: 1px solid #94a3b8; border-radius: 4px; }
        button { padding: 10px 20px; background: #16a34a; color: white; border: none; border-radius: 4px; font-size: 15px; cursor: pointer; }
        .alert-error { margin-top: 14px; padding: 10px; background: #fee2e2; color: #991b1b; border: 1px solid #f87171; border-radius: 4px; }
      </style>
    </head>
    <body>
      ${renderHeader('checkout')}
      <div class="container">
        <h2>Checkout</h2>
        <form id="checkout-form">
          <div class="form-group">
            <label for="address">Shipping Address</label>
            <input type="text" id="address" name="address" required value="123 Test St, Testing City">
          </div>
          <div class="form-group">
            <label for="card">Card Details (Demo)</label>
            <input type="text" id="card" name="card" required value="4242 4242 4242 4242">
          </div>
          <button type="submit" id="checkout-submit-btn" data-testid="checkout-submit-btn">Place Order</button>
          <div id="checkout-feedback" class="alert-error" role="alert" style="display: none;"></div>
        </form>
      </div>

      <script>
        document.getElementById('checkout-form').addEventListener('submit', async (e) => {
          e.preventDefault();
          const feedback = document.getElementById('checkout-feedback');
          feedback.style.display = 'none';

          const res = await fetch('/api/checkout', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              address: document.getElementById('address').value,
              card: document.getElementById('card').value
            })
          });

          if (res.status === 500) {
            // Planted Defect B4: Checkout 500 and UI shows nothing
            return;
          }

          const data = await res.json();
          if (data.ok) {
            alert('Order placed successfully! Order ID: ' + data.orderId);
            window.location.href = '/';
          } else {
            feedback.textContent = data.error || 'Checkout failed';
            feedback.style.display = 'block';
          }
        });
      </script>
    </body>
    </html>
  `);
});

app.post('/api/checkout', (req, res) => {
  const sessionId = getSessionId(req, res);
  const cartItems = carts.get(sessionId) || [];

  // K5: Empty-cart checkout correctly blocked with a message
  if (cartItems.length === 0) {
    return res.status(400).json({ ok: false, error: 'Your cart is empty' });
  }

  // Planted defect B4: checkout-500
  if (isBugActive('checkout-500')) {
    return res.status(500).send('Internal Server Error: Payment gateway timeout');
  }

  carts.delete(sessionId);
  return res.json({ ok: true, orderId: 'ORD-' + Math.floor(Math.random() * 90000 + 10000) });
});

if (require.main === module) {
  app.listen(PORT, () => {
    console.log(`[QA Benchmark Shop] Running on port ${PORT} with BUGS=${process.env.BUGS || 'none'}`);
  });
}

module.exports = app;
