import crypto from 'node:crypto';
import fs from 'node:fs';
import { chromium } from 'playwright';

const fail = error => {
  process.stdout.write(JSON.stringify({kind: 'karakeep-browser-error-v1',
    message: String(error?.message || error).slice(0, 800)}) + '\n');
  process.exit(1);
};
process.on('uncaughtException', fail);
process.on('unhandledRejection', fail);

const TITLE = 'HomeLab Karakeep Phase 5 recovery marker v1';
const BODY = 'Synthetic searchable bookmark survives database and search-index recovery.';
const ASSET_NAME = 'phase5-karakeep-asset.png';
const ASSET = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Z7j8AAAAASUVORK5CYII=', 'base64');
const SEARCH = 'search-index recovery';
const action = process.env.KARAKEEP_BROWSER_ACTION;
const baseUrl = process.env.KARAKEEP_BROWSER_BASE_URL;
const screenshot = process.env.KARAKEEP_BROWSER_SCREENSHOT;
const inputPath = '/credentials/credentials.json';
const secretOutput = '/evidence/private-credentials.json';

function requireInput(ok, message) { if (!ok) throw new Error(message); }
requireInput(['seed', 'verify', 'restore'].includes(action), 'invalid action');
requireInput(baseUrl === 'http://karakeep-web:3000', 'invalid internal application URL');
requireInput(screenshot?.startsWith('/evidence/') && screenshot.endsWith('.png'),
  'invalid screenshot path');
const credentials = JSON.parse(fs.readFileSync(inputPath, 'utf8'));
requireInput(credentials.fixture_email?.endsWith('@example.invalid'), 'invalid synthetic email');
requireInput(credentials.fixture_password?.length >= 28, 'invalid synthetic password');
const sha256 = value => crypto.createHash('sha256').update(value).digest('hex');

async function api(path, options = {}) {
  const response = await fetch(baseUrl + path, { ...options, headers: {
    Authorization: `Bearer ${credentials.api_key}`, ...(options.headers || {}) }});
  if (!response.ok) throw new Error(`${options.method || 'GET'} ${path} failed ${response.status}: ${(await response.text()).slice(0, 300)}`);
  return response;
}

async function registerAndCreateKey(page) {
  await page.goto(baseUrl + '/signup', { waitUntil: 'domcontentloaded', timeout: 60_000 });
  await page.getByLabel('Full Name').fill('Phase 5 Karakeep');
  await page.getByLabel('Email').fill(credentials.fixture_email);
  await page.getByLabel('Password', { exact: true }).fill(credentials.fixture_password);
  await page.getByLabel('Confirm Password').fill(credentials.fixture_password);
  await page.getByRole('button', { name: 'Sign up', exact: true }).click();
  await page.waitForURL(url => !url.pathname.endsWith('/signup'), { timeout: 60_000 });
  await page.goto(baseUrl + '/settings/api-keys', { waitUntil: 'networkidle', timeout: 60_000 });
  await page.getByRole('button', { name: 'New API Key', exact: true }).click();
  await page.getByRole('dialog').getByLabel('Name').fill('HomeLab Recovery');
  await page.getByRole('dialog').getByRole('button', { name: 'Create', exact: true }).click();
  const key = await page.getByRole('dialog').locator('input[readonly]').inputValue({ timeout: 30_000 });
  requireInput(key.length >= 24, 'API key was not rendered');
  credentials.api_key = key;
  fs.writeFileSync(secretOutput, JSON.stringify(credentials, null, 2) + '\n', { mode: 0o600 });
}

async function login(page) {
  await page.goto(baseUrl + '/signin', {waitUntil: 'domcontentloaded', timeout: 60_000});
  await page.getByLabel('Email').fill(credentials.fixture_email);
  await page.getByLabel('Password').fill(credentials.fixture_password);
  await page.getByRole('button', {name: 'Sign In', exact: true}).click();
  await page.waitForURL(url => !url.pathname.endsWith('/signin'), {timeout: 60_000});
}

async function seed() {
  const text = await api('/api/v1/bookmarks', { method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({type: 'text', title: TITLE, text: BODY, source: 'api'}) });
  const textBookmark = await text.json();
  const file = new File([ASSET], ASSET_NAME, {type: 'image/png'});
  const form = new FormData(); form.append('file', file);
  const uploaded = await (await api('/api/v1/assets', {method: 'POST', body: form})).json();
  const asset = await api('/api/v1/bookmarks', { method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({type: 'asset', assetType: 'image', assetId: uploaded.assetId,
      fileName: ASSET_NAME, title: 'Phase 5 Karakeep exact asset'}) });
  const assetBookmark = await asset.json();
  return {textId: textBookmark.id, assetId: uploaded.assetId, assetBookmarkId: assetBookmark.id};
}

async function reindex() {
  await api('/api/v1/admin/jobs/trigger/reindex', {method: 'POST',
    headers: {'Content-Type': 'application/json'}, body: '{}'});
}

async function waitForSearch(expectedId) {
  const deadline = Date.now() + 90_000;
  while (Date.now() < deadline) {
    const result = await (await api('/api/v1/bookmarks/search?q=' + encodeURIComponent(SEARCH))).json();
    if (result.bookmarks?.some(item => item.id === expectedId && item.title === TITLE)) return true;
    await new Promise(resolve => setTimeout(resolve, 2000));
  }
  throw new Error('full-text search did not return the synthetic bookmark');
}

async function verify(page, expected) {
  const listing = await (await api('/api/v1/bookmarks?limit=100')).json();
  const text = listing.bookmarks.find(item => item.id === expected.textId);
  const assetBookmark = listing.bookmarks.find(item => item.id === expected.assetBookmarkId);
  requireInput(text?.title === TITLE && text.content?.text === BODY, 'text bookmark mismatch');
  requireInput(assetBookmark?.content?.assetId === expected.assetId, 'asset bookmark mismatch');
  await waitForSearch(expected.textId);
  const downloaded = Buffer.from(await (await api('/api/v1/assets/' + expected.assetId)).arrayBuffer());
  requireInput(downloaded.equals(ASSET), 'asset bytes mismatch');
  await page.goto(baseUrl + '/dashboard/preview/' + expected.textId,
    {waitUntil: 'networkidle', timeout: 60_000});
  const rendered = page.getByText(TITLE, {exact: true});
  await rendered.first().waitFor({state: 'visible', timeout: 60_000});
  requireInput(await rendered.count() === 1, 'expected exactly one rendered bookmark title');
  await page.screenshot({path: screenshot, fullPage: true});
  return {rendered: true, downloaded};
}

async function logicalBackup() {
  const created = await (await api('/api/v1/backups', {method: 'POST'})).json();
  const deadline = Date.now() + 120_000;
  while (Date.now() < deadline) {
    const current = await (await api('/api/v1/backups/' + created.id)).json();
    if (current.status === 'failure') throw new Error('application backup worker failed');
    if (current.status === 'success' && current.assetId) {
      const response = await api('/api/v1/backups/' + created.id + '/download');
      fs.writeFileSync('/evidence/application-export.zip', Buffer.from(await response.arrayBuffer()), {mode: 0o600});
      return {id: created.id, bookmarkCount: current.bookmarkCount, size: current.size};
    }
    await new Promise(resolve => setTimeout(resolve, 2000));
  }
  throw new Error('application backup did not complete');
}

const browser = await chromium.launch({headless: true});
try {
  const context = await browser.newContext({viewport: {width: 1440, height: 1000}});
  const page = await context.newPage();
  let identifiers = credentials.identifiers;
  if (action === 'seed') {
    await registerAndCreateKey(page);
    identifiers = await seed();
    credentials.identifiers = identifiers;
    fs.writeFileSync(secretOutput, JSON.stringify(credentials, null, 2) + '\n', {mode: 0o600});
  } else {
    await login(page);
  }
  requireInput(identifiers?.textId && identifiers?.assetId && identifiers?.assetBookmarkId,
    'fixture identifiers unavailable');
  if (action === 'restore') await reindex();
  const verified = await verify(page, identifiers);
  const logical = action === 'seed' ? await logicalBackup() : null;
  await context.close();
  process.stdout.write(JSON.stringify({
    kind: 'karakeep-browser-bookmarks-v1', text_id: identifiers.textId,
    asset_id: identifiers.assetId, asset_bookmark_id: identifiers.assetBookmarkId,
    title: TITLE, body: BODY, title_sha256: sha256(TITLE), body_sha256: sha256(BODY),
    asset: {filename: ASSET_NAME, bytes: verified.downloaded.length, sha256: sha256(verified.downloaded)},
    rendered_title: verified.rendered, full_text_search: true, asset_downloaded: true,
    search_reindexed: action === 'restore', browser: 'chromium', headless: true,
    application_export: logical ? {created: true, bookmark_count: logical.bookmarkCount,
      bytes: fs.statSync('/evidence/application-export.zip').size} : null,
  }) + '\n');
} finally { await browser.close(); }
