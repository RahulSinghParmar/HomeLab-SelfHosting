import crypto from 'node:crypto';
import fs from 'node:fs';
import net from 'node:net';
import tls from 'node:tls';
import { chromium } from 'playwright';

const reportFailure = error => {
  process.stdout.write(JSON.stringify({
    kind: 'vaultwarden-browser-error-v1',
    message: String(error?.message || error).slice(0, 800),
  }) + '\n');
  process.exit(1);
};
process.on('uncaughtException', reportFailure);
process.on('unhandledRejection', reportFailure);

const TITLE = 'HomeLab Vaultwarden Phase 5 recovery marker v1';
const BODY = 'Synthetic decrypted note survives backup and fresh restore.';
const ATTACHMENT = 'phase5-vaultwarden-attachment.txt';
const ATTACHMENT_BODY = Buffer.from('HomeLab Vaultwarden Phase 5 attachment marker v1\n');
const action = process.env.VAULTWARDEN_BROWSER_ACTION;
const email = process.env.VAULTWARDEN_BROWSER_EMAIL;
const password = process.env.VAULTWARDEN_BROWSER_PASSWORD;
const localPort = Number(process.env.VAULTWARDEN_BROWSER_LOCAL_PORT);
const upstreamHost = process.env.VAULTWARDEN_BROWSER_UPSTREAM_HOST;
const screenshot = process.env.VAULTWARDEN_BROWSER_SCREENSHOT;

function requireInput(ok, message) {
  if (!ok) throw new Error(message);
}

requireInput(['seed', 'verify'].includes(action), 'invalid action');
requireInput(email?.endsWith('@example.invalid'), 'invalid synthetic email');
requireInput(password?.length >= 24, 'invalid synthetic password');
requireInput(Number.isInteger(localPort) && localPort >= 1024 && localPort <= 65535,
  'invalid local port');
requireInput(/^[a-z0-9-]+$/.test(upstreamHost || ''), 'invalid upstream host');
requireInput(screenshot?.startsWith('/evidence/') && screenshot.endsWith('.png'),
  'invalid evidence path');

const sha256 = value => crypto.createHash('sha256').update(value).digest('hex');
const visibleClick = async (page, selector, text) => {
  const clicked = await page.evaluate(({ selector, text }) => {
    const node = [...document.querySelectorAll(selector)]
      .find(item => item.offsetParent !== null && item.textContent?.trim() === text);
    if (!node) return false;
    node.click();
    return true;
  }, { selector, text });
  requireInput(clicked, `visible ${text} action unavailable`);
};

const proxy = tls.createServer({
  key: fs.readFileSync('/tmp/key.pem'), cert: fs.readFileSync('/tmp/cert.pem'),
}, client => {
  const upstream = net.connect(80, upstreamHost);
  client.pipe(upstream);
  upstream.pipe(client);
  const close = () => { client.destroy(); upstream.destroy(); };
  client.on('error', close);
  upstream.on('error', close);
});
await new Promise((resolve, reject) => {
  proxy.once('error', reject);
  proxy.listen(localPort, '127.0.0.1', resolve);
});
const baseUrl = `https://localhost:${localPort}`;

async function finishOnboarding(page) {
  await page.waitForFunction(() => /#\/(vault|setup-extension)/.test(location.hash),
    null, { timeout: 60_000 });
  if (page.url().includes('#/setup-extension')) {
    await page.getByRole('button', { name: 'Add it later', exact: true }).click();
    await page.getByRole('link', { name: 'Skip to web app', exact: true }).click();
  }
  await page.waitForFunction(() => /#\/vault/.test(location.hash),
    null, { timeout: 60_000 });
  await page.waitForTimeout(2500);
  const skip = page.getByRole('button', { name: 'Skip', exact: true });
  if (await skip.isVisible().catch(() => false)) {
    await skip.click();
    await page.waitForTimeout(500);
  }
}

async function register(page) {
  await page.goto(`${baseUrl}/#/signup`, { waitUntil: 'domcontentloaded', timeout: 60_000 });
  await page.locator('#register-start_form_input_email').fill(email);
  await page.locator('#register-start_form_input_name').fill('Phase 5 Vaultwarden');
  await page.getByRole('button', { name: 'Continue', exact: true }).click();
  await page.locator('#input-password-form_new-password').fill(password);
  await page.locator('#input-password-form_new-password-confirm').fill(password);
  const breach = page.locator('#input-password-form_check-for-breaches');
  if (await breach.isChecked().catch(() => false)) await breach.uncheck();
  await visibleClick(page, 'button[type="submit"]', 'Create account');
  await finishOnboarding(page);
}

async function login(page) {
  await page.goto(`${baseUrl}/#/login`, { waitUntil: 'domcontentloaded', timeout: 60_000 });
  await page.locator('#email').fill(email);
  await page.getByRole('button', { name: 'Continue', exact: true }).click();
  await page.locator('#masterPassword').waitFor({ state: 'visible', timeout: 30_000 });
  await page.locator('#masterPassword').fill(password);
  await page.getByRole('button', { name: 'Log in', exact: true }).click();
  await finishOnboarding(page);
}

async function unlockIfLocked(page) {
  await page.waitForFunction(() => location.hash.startsWith('#/lock'),
    null, { timeout: 15_000 }).catch(() => null);
  if (!page.url().includes('#/lock')) return;
  const master = page.locator('input[type="password"]:visible').last();
  await master.waitFor({ state: 'visible', timeout: 30_000 });
  await master.fill(password);
  await page.getByRole('button', { name: 'Unlock', exact: true }).click();
  await page.waitForFunction(() => /#\/vault/.test(location.hash),
    null, { timeout: 60_000 });
  await page.locator('#newItemDropdown').waitFor({ state: 'visible', timeout: 30_000 });
}

async function openAttachments(page) {
  const clicked = await page.evaluate(() => {
    const buttons = [...document.querySelectorAll('button[aria-label="Options"]')]
      .filter(node => node.offsetParent !== null);
    const button = buttons.at(-1);
    if (!button) return false;
    button.click();
    return true;
  });
  requireInput(clicked, 'visible item options action unavailable');
  await page.waitForTimeout(500);
  await visibleClick(page, 'button', 'Attachments');
}

async function createFixture(page) {
  await page.locator('#newItemDropdown').click();
  await visibleClick(page, 'button', 'Note');
  const nameField = page.locator('input[formcontrolname="name"]:visible').last();
  const noteField = page.locator('textarea[formcontrolname="notes"]:visible').last();
  await nameField.waitFor({ state: 'visible', timeout: 30_000 });
  await noteField.waitFor({ state: 'visible', timeout: 30_000 });
  await nameField.fill(TITLE);
  await noteField.fill(BODY);
  await visibleClick(page, 'button[type="submit"]', 'Save');
  await page.locator(`button[title="Edit item - ${TITLE}"]`).waitFor({ timeout: 30_000 });
  await page.waitForTimeout(1500);
  await page.locator(`button[title="Edit item - ${TITLE}"]`).click({ force: true });
  await page.locator('#notes').waitFor({ state: 'visible', timeout: 30_000 });
  await openAttachments(page);
  const path = '/tmp/' + ATTACHMENT;
  fs.writeFileSync(path, ATTACHMENT_BODY, { mode: 0o600 });
  await page.locator('#file').setInputFiles(path);
  await visibleClick(page, 'button[type="submit"]', 'Upload');
  await page.getByText('Attachment saved', { exact: false }).waitFor({ timeout: 60_000 });
}

async function verifyFixture(page) {
  await page.goto(`${baseUrl}/#/vault`, { waitUntil: 'domcontentloaded', timeout: 60_000 });
  await page.reload({ waitUntil: 'domcontentloaded', timeout: 60_000 });
  await unlockIfLocked(page);
  await page.waitForTimeout(1500);
  const items = page.locator(`button[title="Edit item - ${TITLE}"]`);
  try {
    await items.first().waitFor({ state: 'visible', timeout: 30_000 });
  } catch (error) {
    const body = (await page.locator('body').innerText().catch(() => '')).slice(0, 600);
    throw new Error(`vault item unavailable at ${page.url()}: ${body}`);
  }
  requireInput(await items.count() === 1, 'expected exactly one synthetic vault item');
  const itemId = (await items.first().getAttribute('id') || '').replace(/^cipher-btn-/, '');
  requireInput(/^[0-9a-f-]{36}$/.test(itemId), 'vault item identifier unavailable');
  await items.first().click({ force: true });
  const notes = page.locator('#notes');
  await notes.waitFor({ state: 'visible', timeout: 30_000 });
  requireInput(await notes.inputValue() === BODY, 'decrypted secure note body mismatch');
  await openAttachments(page);
  const downloadButton = page.locator(
    `button[aria-label="Download ${ATTACHMENT}"]:visible`).first();
  await downloadButton.waitFor({ state: 'visible', timeout: 30_000 });
  const downloadReady = page.waitForEvent('download', { timeout: 60_000 });
  await downloadButton.evaluate(node => node.click());
  const download = await downloadReady;
  const downloaded = '/tmp/downloaded-' + ATTACHMENT;
  await download.saveAs(downloaded);
  const bytes = fs.readFileSync(downloaded);
  requireInput(bytes.equals(ATTACHMENT_BODY), 'decrypted attachment bytes mismatch');
  await page.reload({ waitUntil: 'domcontentloaded', timeout: 60_000 });
  await unlockIfLocked(page);
  const reloaded = page.locator('#notes');
  if (!await reloaded.isVisible().catch(() => false)) {
    await page.goto(`${baseUrl}/#/vault?itemId=${itemId}&action=view`, {
      waitUntil: 'domcontentloaded', timeout: 60_000,
    });
    await unlockIfLocked(page);
  }
  await reloaded.waitFor({ state: 'visible', timeout: 30_000 });
  requireInput(await reloaded.inputValue() === BODY, 'reloaded decrypted note mismatch');
  return { itemId, attachmentBytes: bytes.length, attachmentSha256: sha256(bytes) };
}

const browser = await chromium.launch({ headless: true });
try {
  const first = await browser.newContext({ ignoreHTTPSErrors: true,
    viewport: { width: 1440, height: 1000 }, acceptDownloads: true });
  const firstPage = await first.newPage();
  if (action === 'seed') await register(firstPage); else await login(firstPage);
  if (action === 'seed') await createFixture(firstPage);
  const firstResult = await verifyFixture(firstPage);
  await first.close();

  const second = await browser.newContext({ ignoreHTTPSErrors: true,
    viewport: { width: 1440, height: 1000 }, acceptDownloads: true });
  const secondPage = await second.newPage();
  await login(secondPage);
  const secondResult = await verifyFixture(secondPage);
  requireInput(firstResult.itemId === secondResult.itemId, 'independent session item mismatch');
  await secondPage.screenshot({ path: screenshot, fullPage: true });
  await second.close();

  process.stdout.write(JSON.stringify({
    kind: 'vaultwarden-browser-vault-v1', item_id: secondResult.itemId,
    title: TITLE, body: BODY, title_sha256: sha256(TITLE), body_sha256: sha256(BODY),
    attachment: { filename: ATTACHMENT, bytes: secondResult.attachmentBytes,
      sha256: secondResult.attachmentSha256 }, browser: 'chromium', headless: true,
    rendered_title: true, decrypted_body: true, attachment_downloaded: true,
    reload_persistence: true, independent_sessions: true,
  }) + '\n');
} finally {
  await browser.close();
  await new Promise(resolve => proxy.close(resolve));
}
