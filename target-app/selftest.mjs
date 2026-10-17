// Self-test runner for target-app
// Usage:
//   node selftest.mjs         (all 9 bugs must be PRESENT)
//   node selftest.mjs --clean (all 9 bugs must be ABSENT, with BUGS_OFF=all)

const isClean = process.argv.includes('--clean');
const BASE_URL = process.env.BASE_URL || 'http://localhost:4000';

let failures = 0;
let passes = 0;

function report(id, bugPresent, detail = '') {
  const ok = isClean ? !bugPresent : bugPresent;
  const statusStr = ok ? 'PASS' : 'FAIL';
  const stateStr = bugPresent ? 'PRESENT' : 'ABSENT';
  if (ok) {
    passes++;
    console.log(`[${statusStr}] ${id}: Bug is ${stateStr} (${detail})`);
  } else {
    failures++;
    console.error(`[${statusStr}] ${id}: Expected ${isClean ? 'ABSENT' : 'PRESENT'}, but was ${stateStr} (${detail})`);
  }
}

function getCookie(res) {
  const setCookie = res.headers.getSetCookie ? res.headers.getSetCookie() : [res.headers.get('set-cookie')];
  if (!setCookie || setCookie.length === 0 || !setCookie[0]) return '';
  const match = setCookie[0].match(/sid=([^;]+)/);
  return match ? `sid=${match[1]}` : '';
}

async function run() {
  console.log(`Running selftest against ${BASE_URL} (mode: ${isClean ? 'CLEAN / BUGS_OFF=all' : 'DEFAULT / BUGS_ON'})`);

  // Reset state before tests
  const resetRes = await fetch(`${BASE_URL}/__reset`, { method: 'POST' });
  const resetJson = await resetRes.json();
  if (!resetJson.ok) {
    throw new Error('Failed to reset state via /__reset');
  }

  // 1. Verify seed user can log in
  const seedLoginRes = await fetch(`${BASE_URL}/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: 'email=qa.tester%40example.com&password=Passw0rd!23',
    redirect: 'manual',
  });
  const seedCookie = getCookie(seedLoginRes);
  if (seedLoginRes.status !== 302 || !seedCookie) {
    console.error('FAIL: Seed user login failed. Status:', seedLoginRes.status, 'Cookie:', seedCookie);
    process.exit(1);
  } else {
    console.log('[PASS] Seed user login verified (status 302 + sid cookie)');
  }

  // GT01: Signup accepts invalid email
  const gt01Res = await fetch(`${BASE_URL}/signup`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: 'email=not-an-email&password=Passw0rd!23',
    redirect: 'manual',
  });
  const gt01BugPresent = gt01Res.status === 302;
  report('GT01', gt01BugPresent, `status=${gt01Res.status}`);

  // GT02: Signup accepts password shorter than 8 (checks for 4)
  const gt02Res = await fetch(`${BASE_URL}/signup`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: 'email=shortpass%40example.com&password=abcde',
    redirect: 'manual',
  });
  const gt02BugPresent = gt02Res.status === 302;
  report('GT02', gt02BugPresent, `password "abcde" status=${gt02Res.status}`);

  // GT03: Wrong password shows no error message
  const gt03Res = await fetch(`${BASE_URL}/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: 'email=qa.tester%40example.com&password=WrongPassword123',
    redirect: 'manual',
  });
  const gt03Html = await gt03Res.text();
  const gt03BugPresent = !gt03Html.includes('<p role="alert"');
  report('GT03', gt03BugPresent, `<p role="alert"> present=${gt03Html.includes('<p role="alert"')}`);

  // GT04: Login fails when email has capital letters
  const gt04Res = await fetch(`${BASE_URL}/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: 'email=QA.Tester%40Example.com&password=Passw0rd!23',
    redirect: 'manual',
  });
  const gt04BugPresent = gt04Res.status !== 302;
  report('GT04', gt04BugPresent, `status=${gt04Res.status}`);

  // GT05: Dashboard accepts an empty item title
  const gt05Res = await fetch(`${BASE_URL}/dashboard/items`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
      'Cookie': seedCookie,
    },
    body: 'title=',
    redirect: 'manual',
  });
  const gt05BugPresent = gt05Res.status === 302;
  report('GT05', gt05BugPresent, `status=${gt05Res.status}`);

  // GT06: Delete removes first item instead of clicked one
  await fetch(`${BASE_URL}/__reset`, { method: 'POST' });
  const loginRes2 = await fetch(`${BASE_URL}/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: 'email=qa.tester%40example.com&password=Passw0rd!23',
    redirect: 'manual',
  });
  const cookie2 = getCookie(loginRes2);

  // Add ItemOne (id 1)
  await fetch(`${BASE_URL}/dashboard/items`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded', 'Cookie': cookie2 },
    body: 'title=ItemOne',
    redirect: 'manual',
  });
  // Add ItemTwo (id 2)
  await fetch(`${BASE_URL}/dashboard/items`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded', 'Cookie': cookie2 },
    body: 'title=ItemTwo',
    redirect: 'manual',
  });
  // Delete item 2
  await fetch(`${BASE_URL}/dashboard/items/2/delete`, {
    method: 'POST',
    headers: { 'Cookie': cookie2 },
    redirect: 'manual',
  });
  // Get dashboard and see which item remains
  const dashRes = await fetch(`${BASE_URL}/dashboard`, {
    headers: { 'Cookie': cookie2 },
  });
  const dashHtml = await dashRes.text();
  const gt06BugPresent = !dashHtml.includes('<span>ItemOne</span>') && dashHtml.includes('<span>ItemTwo</span>');
  report('GT06', gt06BugPresent, `ItemOne remains=${dashHtml.includes('<span>ItemOne</span>')}, ItemTwo remains=${dashHtml.includes('<span>ItemTwo</span>')}`);

  // GT07: After logout, Back shows cached dashboard (response is cacheable)
  const gt07Res = await fetch(`${BASE_URL}/dashboard`, {
    headers: { 'Cookie': cookie2 },
  });
  const cacheControl = gt07Res.headers.get('cache-control') || '';
  const gt07BugPresent = cacheControl.includes('max-age');
  report('GT07', gt07BugPresent, `Cache-Control="${cacheControl}"`);

  // GT08: Settings page logs console error and throws uncaught TypeError on load
  const settingsRes = await fetch(`${BASE_URL}/settings`, {
    headers: { 'Cookie': cookie2 },
  });
  const settingsHtml = await settingsRes.text();
  const gt08BugPresent = settingsHtml.includes('Failed to load preferences');
  report('GT08', gt08BugPresent, `contains error script=${gt08BugPresent}`);

  // GT09: Every second settings save fails with HTTP 500
  await fetch(`${BASE_URL}/__reset`, { method: 'POST' });
  const loginRes3 = await fetch(`${BASE_URL}/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: 'email=qa.tester%40example.com&password=Passw0rd!23',
    redirect: 'manual',
  });
  const cookie3 = getCookie(loginRes3);

  const save1 = await fetch(`${BASE_URL}/settings`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded', 'Cookie': cookie3 },
    body: 'displayName=FirstSave',
    redirect: 'manual',
  });
  const save2 = await fetch(`${BASE_URL}/settings`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded', 'Cookie': cookie3 },
    body: 'displayName=SecondSave',
    redirect: 'manual',
  });
  const gt09BugPresent = save1.status === 200 && save2.status === 500;
  report('GT09', gt09BugPresent, `save1 status=${save1.status}, save2 status=${save2.status}`);

  console.log(`\nSummary: ${passes} passed, ${failures} failed.`);
  if (failures > 0) {
    process.exit(1);
  }
}

run().catch(err => {
  console.error('Selftest error:', err);
  process.exit(1);
});
