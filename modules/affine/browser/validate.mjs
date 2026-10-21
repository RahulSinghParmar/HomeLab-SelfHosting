import crypto from 'node:crypto';
import fs from 'node:fs/promises';
import net from 'node:net';
import path from 'node:path';
import process from 'node:process';
import { chromium } from 'playwright';

const LOCAL_PORT = Number.parseInt(process.env.AFFINE_BROWSER_LOCAL_PORT ?? '3010', 10);
const BASE = process.env.AFFINE_BROWSER_BASE_URL ?? `http://127.0.0.1:${LOCAL_PORT}`;
const UPSTREAM = process.env.AFFINE_BROWSER_UPSTREAM_HOST ?? 'affine';
const EMAIL = 'affine-recovery@example.invalid';
const PASSWORD = process.env.AFFINE_BROWSER_PASSWORD;
const WORKSPACE_ID = process.env.AFFINE_BROWSER_WORKSPACE_ID;
const SOURCE_DOC_ID = process.env.AFFINE_BROWSER_SOURCE_DOC_ID;
const ACTION = process.env.AFFINE_BROWSER_ACTION;
const EXPECTED_DOC_ID = process.env.AFFINE_BROWSER_EXPECTED_DOC_ID;
const SCREENSHOT = process.env.AFFINE_BROWSER_SCREENSHOT;
const TITLE = 'AFFiNE browser recovery proof';
const BODY = 'Browser-rendered synthetic document survives encrypted off-host recovery.';
let diagnosticPage;

function required(value, name) {
  if (!value) throw new Error(`${name} is required`);
  return value;
}

function digest(value) {
  return crypto.createHash('sha256').update(value, 'utf8').digest('hex');
}

async function startProxy() {
  if (!Number.isInteger(LOCAL_PORT) || LOCAL_PORT < 1024 || LOCAL_PORT > 65535) {
    throw new Error('AFFINE_BROWSER_LOCAL_PORT is invalid');
  }
  const server = net.createServer(client => {
    const upstream = net.connect(3010, UPSTREAM);
    client.pipe(upstream);
    upstream.pipe(client);
    const close = () => {
      client.destroy();
      upstream.destroy();
    };
    client.on('error', close);
    upstream.on('error', close);
  });
  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(LOCAL_PORT, '127.0.0.1', resolve);
  });
  return server;
}

async function login(page) {
  await page.goto(`${BASE}/sign-in`, { waitUntil: 'domcontentloaded', timeout: 60_000 });
  let email = page.getByPlaceholder('Enter your email address');
  if (!(await email.isVisible({ timeout: 10_000 }).catch(() => false))) {
    email = page.locator('form input[name="username"][type="email"]').first();
  }
  if (!(await email.isVisible({ timeout: 30_000 }).catch(() => false))) {
    const diagnostics = await page.evaluate(() => ({
      url: location.href,
      title: document.title,
      testids: [...document.querySelectorAll('[data-testid]')]
        .slice(0, 40).map(node => node.getAttribute('data-testid')),
      text: document.body.innerText.slice(0, 300),
    }));
    throw new Error(`sign-in form unavailable: ${JSON.stringify(diagnostics)}`);
  }
  await email.waitFor({ state: 'visible', timeout: 60_000 });
  await email.fill(EMAIL);
  await page.getByTestId('continue-login-button').click();
  await page.getByTestId('password-input').fill(required(PASSWORD, 'AFFINE_BROWSER_PASSWORD'));
  await page.getByTestId('sign-in-button').click();
  await page.getByTestId('sign-in-button').waitFor({ state: 'detached', timeout: 60_000 });
}

async function waitForSync(page, docId) {
  await page.evaluate(async id => {
    const workspace = window.currentWorkspace;
    if (!workspace?.engine?.doc) throw new Error('AFFiNE browser sync engine is unavailable');
    await workspace.engine.doc.waitForSynced(id, AbortSignal.timeout(120_000));
  }, docId);
}

async function dismissOpenInApp(page) {
  const card = page.getByTestId('open-in-app-card');
  const hidden = await card.evaluate(node => node.getAttribute('data-hidden')).catch(() => null);
  if (hidden !== null && hidden !== 'true') {
    const checkbox = card.getByRole('checkbox', { name: 'Remember choice' }).locator('input');
    if (!(await checkbox.isChecked())) await checkbox.click();
    await page.getByRole('button', { name: 'Dismiss' }).click();
    await page.locator('[data-testid="open-in-app-card"][data-hidden="true"]').waitFor({
      state: 'attached', timeout: 15_000,
    });
    await page.reload({ waitUntil: 'domcontentloaded', timeout: 60_000 });
  }
}

async function enableCloudWorkspace(page) {
  await page.getByTestId('slider-bar-workspace-setting-button').click();
  await page.getByTestId('workspace-setting:preference').click();
  await page.getByTestId('publish-enable-affine-cloud-button').click();
  await page.getByTestId('confirm-enable-affine-cloud-button').click();
  await page.waitForTimeout(5_000);
  const close = page.getByTestId('modal-close-button').last();
  if (await close.isVisible().catch(() => false)) await close.click();
}

async function createInitialSyncedWorkspace(page) {
  const create = page.getByTestId('new-workspace');
  if (!(await create.isVisible({ timeout: 5_000 }).catch(() => false))) return false;
  await create.click();
  const name = page.getByTestId('create-workspace-input');
  await name.waitFor({ state: 'visible', timeout: 30_000 });
  await name.fill('AFFiNE Browser Recovery');
  const submit = page.getByTestId('create-workspace-create-button');
  await submit.click();
  await submit.waitFor({ state: 'detached', timeout: 60_000 });
  await page.waitForSelector('v-line', { timeout: 60_000 });
  return true;
}

async function visibleDocument(page, workspaceId, docId) {
  await page.goto(`${BASE}/workspace/${workspaceId}/${docId}`, {
    waitUntil: 'domcontentloaded', timeout: 60_000,
  });
  await dismissOpenInApp(page);
  await page.locator('doc-title .inline-editor').first().waitFor({ state: 'visible', timeout: 60_000 });
  await page.locator('doc-title .inline-editor').first().filter({ hasText: TITLE }).waitFor({
    state: 'visible', timeout: 60_000,
  });
  await page.locator('affine-note affine-paragraph').filter({ hasText: BODY }).waitFor({
    state: 'visible', timeout: 60_000,
  });
  await waitForSync(page, docId);
}

async function verifyIndependentSession(browser, workspaceId, docId) {
  const context = await browser.newContext();
  try {
    const page = await context.newPage();
    await login(page);
    await visibleDocument(page, workspaceId, docId);
  } finally {
    await context.close();
  }
}

async function run() {
  required(WORKSPACE_ID, 'AFFINE_BROWSER_WORKSPACE_ID');
  required(ACTION, 'AFFINE_BROWSER_ACTION');
  if (!['seed', 'verify'].includes(ACTION)) throw new Error('Unsupported browser validation action');

  const proxy = await startProxy();
  const browser = await chromium.launch({ headless: true });
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
    const page = await context.newPage();
    diagnosticPage = page;
    await login(page);
    let docId = EXPECTED_DOC_ID;
    let workspaceId = WORKSPACE_ID;

    if (ACTION === 'seed') {
      await page.goto(BASE, { waitUntil: 'domcontentloaded', timeout: 60_000 });
      await dismissOpenInApp(page);
      const createdSyncedWorkspace = await createInitialSyncedWorkspace(page);
      let newPage = page.getByTestId('sidebar-new-page-button');
      if (!(await newPage.isVisible({ timeout: 15_000 }).catch(() => false))) {
        newPage = page.getByTestId('new-page-button-trigger');
      }
      if (!(await newPage.isVisible({ timeout: 15_000 }).catch(() => false))) {
        if (SCREENSHOT) await page.screenshot({ path: SCREENSHOT, fullPage: true });
        const diagnostics = await page.evaluate(() => ({
          url: location.href,
          title: document.title,
          testids: [...document.querySelectorAll('[data-testid]')]
            .slice(0, 40).map(node => node.getAttribute('data-testid')),
          text: document.body.innerText.slice(0, 300),
        }));
        throw new Error(`new-page control unavailable: ${JSON.stringify(diagnostics)}`);
      }
      await newPage.click();
      const title = page.locator('doc-title .inline-editor').first();
      await title.waitFor({ state: 'visible', timeout: 60_000 });
      await title.fill(TITLE);
      await title.press('Enter');
      await page.keyboard.type(BODY, { delay: 5 });
      const parts = new URL(page.url()).pathname.split('/').filter(Boolean);
      docId = parts.at(-1);
      workspaceId = parts.at(-2);
      required(docId, 'created AFFiNE document ID');
      required(workspaceId, 'created AFFiNE workspace ID');
      if (!createdSyncedWorkspace) await enableCloudWorkspace(page);
      await waitForSync(page, docId);
    } else {
      required(docId, 'AFFINE_BROWSER_EXPECTED_DOC_ID');
    }

    await visibleDocument(page, workspaceId, docId);
    await page.reload({ waitUntil: 'domcontentloaded', timeout: 60_000 });
    await visibleDocument(page, workspaceId, docId);
    if (SCREENSHOT) {
      await fs.mkdir(path.dirname(SCREENSHOT), { recursive: true });
      await page.screenshot({ path: SCREENSHOT, fullPage: true });
    }
    await context.close();
    await verifyIndependentSession(browser, workspaceId, docId);

    const evidence = {
      kind: 'affine-browser-document-v1',
      workspace_id: workspaceId,
      doc_id: docId,
      title: TITLE,
      body: BODY,
      title_sha256: digest(TITLE),
      body_sha256: digest(BODY),
      browser: 'chromium',
      headless: true,
      rendered_title: true,
      rendered_body: true,
      reload_persistence: true,
      independent_sessions: true,
    };
    process.stdout.write(`${JSON.stringify(evidence)}\n`);
  } finally {
    await browser.close();
    await new Promise(resolve => proxy.close(resolve));
  }
}

run().catch(async error => {
  if (diagnosticPage && SCREENSHOT) {
    await diagnosticPage.screenshot({ path: SCREENSHOT, fullPage: true }).catch(() => {});
  }
  process.stdout.write(`${JSON.stringify({
    kind: 'affine-browser-error-v1',
    message: String(error.message).slice(0, 800),
  })}\n`);
  process.exitCode = 1;
});
