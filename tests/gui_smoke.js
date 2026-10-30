// Headless smoke test for index.html with MSAL and Microsoft Graph mocked.
// Run: node tests/gui_smoke.js   (needs the `playwright` package and a Chromium)
const { chromium } = require('playwright');
const path = require('path');
const assert = require('assert');

(async () => {
  const browser = await chromium.launch({ args: ['--no-sandbox'] });
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('dialog', d => d.accept());
  await page.route('**/msal-browser.min.js', r => r.fulfill({ contentType: 'text/javascript', body:
    `window.msal={PublicClientApplication:function(){this.initialize=async()=>{};this.loginPopup=async()=>({account:{username:'t@x'}});this.acquireTokenSilent=async()=>({accessToken:'tok'});}}` }));
  await page.addInitScript(() => {
    const fs = { 'Example Resume.pdf': 'a', 'Employer Notes': 'a', 'Clearance Form.pdf': 'a', 'Career': 'F' };
    let n = 100; const ids = {};
    const idOf = p => ids[p] || (ids[p] = 'id' + (n++));
    const byId = id => Object.keys(fs).find(k => idOf(k) === id);
    window.getFs = () => fs;
    window.fetch = async (url, o = {}) => {
      const m = o.method || 'GET'; const u = decodeURIComponent(url.replace('https://graph.microsoft.com/v1.0', ''));
      const J = (s, b) => ({ ok: s < 300, status: s, headers: { get: () => null }, json: async () => b, text: async () => JSON.stringify(b) });
      let mm;
      if (m === 'GET' && (mm = u.match(/^\/me\/drive\/root:\/(.*)$/))) {
        const k = mm[1]; if (!(k in fs)) return J(404, {});
        const par = k.includes('/') ? k.slice(0, k.lastIndexOf('/')) : '';
        return J(200, { id: idOf(k), name: k.split('/').pop(), folder: fs[k] === 'F' ? {} : undefined, parentReference: { path: '/drive/root:' + (par ? '/' + par : '') } });
      }
      if (m === 'POST') {
        const body = JSON.parse(o.body); const pid = (u.match(/items\/(.*)\/children/) || [])[1];
        const par = pid ? byId(pid) : ''; const k = par ? par + '/' + body.name : body.name;
        fs[k] = 'F'; return J(201, { id: idOf(k), name: body.name, folder: {} });
      }
      if (m === 'PATCH') {
        const old = byId(u.replace('/me/drive/items/', '')); const body = JSON.parse(o.body);
        const nk = byId(body.parentReference.id) + '/' + old.split('/').pop();
        if (nk in fs) return J(409, {}); fs[nk] = fs[old]; delete fs[old]; ids[nk] = ids[old]; return J(200, {});
      }
      return J(500, {});
    };
  });
  await page.goto('file://' + path.resolve(__dirname, '..', 'sorter', 'web', 'index.html'));
  await page.fill('#client-id', 'test-client');
  await page.click('button:has-text("Connect OneDrive")');
  await page.setInputFiles('#manifest-file', path.resolve(__dirname, 'fixtures', 'sample_manifest.csv'));
  await page.evaluate(() => updateRate(500));

  await page.waitForFunction(() => document.getElementById('log').innerText.includes('Loaded'), null, { timeout: 10000 });
  const log = await page.innerText('#log');
  assert(log.includes('Loaded 5 manifest row(s); 1 need review.'), 'validation summary: ' + log);

  await page.click('#btn-check');
  await page.waitForFunction(() => !document.getElementById('btn-check').disabled, null, { timeout: 30000 });
  const table = await page.innerText('#plan tbody');
  assert((table.match(/ready/g) || []).length === 3, 'three rows ready:\n' + table);
  assert(table.includes('source not found'), 'missing source reported');
  assert(table.includes('needs review'), 'flagged row held');
  assert((await page.innerText('#log')).includes('Folders that will be created'), 'create-folder summary');

  // rclone export covers the rows that are still ready (do it before they are moved)
  const [dl] = await Promise.all([page.waitForEvent('download'), page.click('#btn-rclone')]);
  assert.strictEqual(dl.suggestedFilename(), 'onedrive_sorter_rclone.sh');

  await page.click('#btn-run');
  await page.waitForFunction(() => document.getElementById('log').innerText.includes('Done.'), null, { timeout: 30000 });
  assert((await page.innerText('#log')).includes('Moved 3; failed 0'), 'moved three');
  const fs = await page.evaluate(() => getFs());
  assert('Career/Resume Workspace/Example Resume.pdf' in fs, 'resume moved into created folder');
  assert('Career/Employers/Acme/Employer Notes' in fs, 'nested folder created');
  assert(!('Example Resume.pdf' in fs), 'source gone from root');

  assert.deepStrictEqual(errors, [], 'no page errors');
  await browser.close();
  console.log('gui smoke: OK');
})().catch(e => { console.error(e); process.exit(1); });
