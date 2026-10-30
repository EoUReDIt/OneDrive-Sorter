// End-to-end test of local mode: real backend (python -m sorter serve) + real page in headless Chromium.
// Run: node tests/gui_local.js   (needs python 3.11+, the `playwright` package and a Chromium)
const { chromium } = require('playwright');
const { spawn } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');
const assert = require('assert');

const repo = path.resolve(__dirname, '..');
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'sorter-gui-'));
const root = path.join(tmp, 'OneDrive');
fs.mkdirSync(root);
for (const f of ['Example Resume.pdf', 'Employer Notes', 'Clearance Form.pdf', 'Course Deck.pptx']) fs.writeFileSync(path.join(root, f), 'x');
fs.mkdirSync(path.join(root, 'Interview Folder'));
// A plan as the MCP server would have saved it (proposal_*.csv plus a note beside it).
const props = path.join(tmp, 'proposals');
fs.mkdirSync(props);
const pname = 'proposal_20261030_120000_000000.csv';
fs.copyFileSync(path.join(__dirname, 'fixtures', 'sample_manifest.csv'), path.join(props, pname));
fs.writeFileSync(path.join(props, pname.replace('.csv', '.json')),
  JSON.stringify({ note: 'Claude says <img src=x onerror=alert(1)> hello', created: '2026-10-30T12:00:00', summary: { ready: 4, 'not selected': 1 } }));
const exists = rel => fs.existsSync(path.join(root, ...rel.split('/')));

function startServer() {
  const child = spawn(process.env.PYTHON || 'python3',
    ['-u', '-m', 'sorter', 'serve', '--root', root, '--port', '0', '--log-dir', path.join(tmp, 'logs'), '--proposals-dir', props], { cwd: repo });
  return new Promise((resolve, reject) => {
    let out = '';
    child.stdout.on('data', d => {
      out += d;
      const m = out.match(/http:\/\/127\.0\.0\.1:\d+\/#token=\S+/);
      if (m) resolve({ child, url: m[0] });
    });
    child.stderr.on('data', d => process.stderr.write(d));
    child.on('exit', c => reject(new Error('server exited early: ' + c + '\n' + out)));
    setTimeout(() => reject(new Error('server did not start:\n' + out)), 15000);
  });
}

(async () => {
  const { child, url } = await startServer();
  const browser = await chromium.launch({ args: ['--no-sandbox'] });
  try {
    const page = await browser.newPage();
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    page.on('dialog', d => d.accept());

    // Without the token the page must stay in cloud mode and cannot reach the API.
    const bare = url.split('#')[0];
    await page.goto(bare);
    await page.waitForTimeout(500);
    assert.strictEqual(await page.isVisible('#card-cloud'), true, 'cloud card shown without a token');
    assert.strictEqual(await page.isVisible('#card-local'), false, 'local card hidden without a token');

    // With the token it switches to local mode and removes the token from the address bar.
    await page.goto(url);
    await page.waitForSelector('#card-local', { state: 'visible', timeout: 10000 });
    assert.strictEqual(await page.isVisible('#card-cloud'), false, 'cloud card hidden in local mode');
    assert.ok(!page.url().includes('token'), 'token removed from the address bar');
    assert.ok((await page.innerText('#local-root')).includes('OneDrive'), 'root shown');

    // Claude's proposal appears in the picker; its note is shown as plain text, never as markup.
    await page.waitForFunction(() => document.getElementById('proposal-select').options.length === 1 && !document.getElementById('proposal-select').options[0].disabled, null, { timeout: 10000 });
    await page.click('button:has-text("Load proposal")');
    await page.waitForFunction(() => document.getElementById('log').innerText.includes('Loaded 5'), null, { timeout: 10000 });
    assert.ok((await page.innerText('#proposal-note')).includes('<img src=x onerror=alert(1)>'), 'note shown literally');
    assert.strictEqual(await page.locator('#proposal-note img').count(), 0, 'note was not rendered as HTML');
    assert.ok(!exists('Career'), 'loading a proposal changed nothing on disk');
    // The file-upload path still works too.
    await page.setInputFiles('#manifest-file', path.join(__dirname, 'fixtures', 'sample_manifest.csv'));
    await page.waitForFunction(() => document.getElementById('log').innerText.includes('Loaded 5'), null, { timeout: 10000 });
    assert.ok((await page.innerText('#log')).includes('1 need review'), 'flagged row reported by the backend');
    await page.evaluate(() => updateRate(0));

    await page.click('#btn-check');
    await page.waitForFunction(() => document.getElementById('log').innerText.includes('Check finished'), null, { timeout: 10000 });
    const table = await page.innerText('#plan tbody');
    assert.strictEqual((table.match(/ready/g) || []).length, 4, 'four rows ready:\n' + table);
    assert.ok((await page.innerText('#log')).includes('Folders that will be created'), 'create-folder summary');
    assert.ok(!exists('Career'), 'check changed nothing on disk');

    await page.click('#btn-run');
    await page.waitForFunction(() => document.getElementById('log').innerText.includes('Done.'), null, { timeout: 20000 });
    assert.ok((await page.innerText('#log')).includes('Moved 4; failed 0'), await page.innerText('#log'));
    assert.ok(exists('Career/Resume Workspace/Example Resume.pdf'), 'resume moved');
    assert.ok(exists('Career/Employers/Acme/Employer Notes'), 'nested folder created');
    assert.ok(exists('Course Deck.pptx'), 'flagged row left alone');
    assert.ok(!exists('Example Resume.pdf'), 'source gone');

    await page.click('#btn-undo');
    await page.waitForFunction(() => document.getElementById('log').innerText.includes('Undone 4'), null, { timeout: 20000 });
    assert.ok(exists('Example Resume.pdf') && exists('Interview Folder'), 'everything back');

    assert.deepStrictEqual(errors, [], 'no page errors');
    console.log('gui local: OK');
  } finally {
    await browser.close();
    child.kill();
    fs.rmSync(tmp, { recursive: true, force: true });
  }
})().catch(e => { console.error(e); process.exit(1); });
