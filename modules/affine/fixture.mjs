import crypto from 'node:crypto';
import {createRequire} from 'node:module';
import process from 'node:process';

const require = createRequire('/app/package.json');
const WebSocket = require('ws');
const Y = require('yjs');

const BASE = 'http://127.0.0.1:3010';
const MARKER = 'HomeLab AFFiNE Phase 5 recovery marker v1';
const EMAIL = 'affine-recovery@example.invalid';
const PASSWORD = process.env.HOMELAB_FIXTURE_PASSWORD;
const ROOT_UPDATE = Buffer.from(
  'AwbChK7tptz3DQAnAQRtZXRhBXBhZ2VzACgBBG1ldGEEbmFtZQF3EkRldiBXb3Jrc3BhY2UgRGVtbyEAwoSu7abc9w0AAQAEIQEGc3BhY2VzCm43RDJHT25KLUoBAAEK1NDZ6tqM+QsAAAKBjeqMoITIzgEAAQAEIQEGc3BhY2VzCmllSHphSlUtOC0BAAhHwoSu7abc9w0CASgA1NDZ6tqM+QsQAmlkAXcKZURSWTg2Rzg3YygA1NDZ6tqM+QsQBXRpdGxlAXcAKADU0Nnq2oz5CxAKY3JlYXRlRGF0ZQF7QnldYlT5cAAnANTQ2erajPkLEAR0YWdzAASN6oyghMjOAQCBwoSu7abc9w0CAQAEKQEGc3BhY2VzCmVEUlk4Nkc4N2MKZURSWTg2Rzg3Y3YAAAEDwoSu7abc9w0BAgfU0Nnq2oz5CwEAEI3qjKCEyM4BAgAFBgE=',
  'base64'
);

function fail(message) {
  throw new Error(message);
}

function cookieHeader(response) {
  const values = response.headers.getSetCookie?.() ?? [];
  if (!values.length) {
    const single = response.headers.get('set-cookie');
    if (single) values.push(single);
  }
  const cookies = values.map(value => value.split(';', 1)[0]).filter(Boolean);
  if (!cookies.length) fail('AFFiNE sign-in returned no session cookie');
  return cookies.join('; ');
}

async function login() {
  if (!PASSWORD) fail('AFFiNE fixture password is unavailable');
  const response = await fetch(`${BASE}/api/auth/sign-in`, {
    method: 'POST',
    headers: {'content-type': 'application/json'},
    body: JSON.stringify({email: EMAIL, password: PASSWORD}),
    redirect: 'manual',
  });
  if (!response.ok) {
    const body = (await response.text()).slice(0, 500).replace(/[\r\n]+/g, ' ');
    fail(`AFFiNE sign-in failed with HTTP ${response.status}: ${body}`);
  }
  const user = await response.json();
  return {cookie: cookieHeader(response), userId: user.id};
}

async function initializeAdmin() {
  if (!PASSWORD) fail('AFFiNE fixture password is unavailable');
  const response = await fetch(`${BASE}/api/setup/create-admin-user`, {
    method: 'POST',
    headers: {'content-type': 'application/json'},
    body: JSON.stringify({name: 'AFFiNE Recovery Fixture', email: EMAIL, password: PASSWORD}),
    redirect: 'manual',
  });
  if (!response.ok) {
    const body = await response.text();
    if (response.status === 403 && body.includes('First user already created')) return;
    fail(`AFFiNE first-admin setup failed with HTTP ${response.status}: ${body.slice(0, 500).replace(/[\r\n]+/g, ' ')}`);
  }
}

async function createWorkspace(cookie) {
  const form = new FormData();
  form.set('operations', JSON.stringify({
    query: 'mutation CreateFixture($init: Upload) { createWorkspace(init: $init) { id } }',
    variables: {init: null},
  }));
  form.set('map', JSON.stringify({'0': ['variables.init']}));
  form.set('0', new Blob([ROOT_UPDATE], {type: 'application/octet-stream'}), 'workspace.bin');
  const response = await fetch(`${BASE}/graphql`, {
    method: 'POST', headers: {cookie}, body: form,
  });
  if (!response.ok) fail(`AFFiNE workspace creation failed with HTTP ${response.status}`);
  const body = await response.json();
  if (body.errors?.length || !body.data?.createWorkspace?.id) {
    fail('AFFiNE workspace creation returned an invalid response');
  }
  return body.data.createWorkspace.id;
}

class SyncSession {
  constructor(cookie) {
    this.cookie = cookie;
    this.nextId = 1;
    this.pending = new Map();
  }

  async connect() {
    this.socket = new WebSocket('ws://127.0.0.1:3010/socket.io/?EIO=4&transport=websocket', {
      headers: {Cookie: this.cookie},
    });
    await new Promise((resolve, reject) => {
      const timeout = setTimeout(() => reject(new Error('AFFiNE sync connection timed out')), 15000);
      this.socket.on('error', reject);
      this.socket.on('message', raw => {
        const value = raw.toString();
        if (value.startsWith('0')) {
          this.socket.send('40');
        } else if (value === '2') {
          this.socket.send('3');
        } else if (value.startsWith('40')) {
          clearTimeout(timeout);
          resolve();
        } else if (value.startsWith('43')) {
          const match = /^43(\d+)(.*)$/.exec(value);
          if (!match) return;
          const pending = this.pending.get(Number(match[1]));
          if (!pending) return;
          this.pending.delete(Number(match[1]));
          try {
            const payload = JSON.parse(match[2]);
            pending.resolve(payload[0]);
          } catch (error) {
            pending.reject(error);
          }
        }
      });
      this.socket.on('close', () => {
        for (const pending of this.pending.values()) pending.reject(new Error('AFFiNE sync socket closed'));
        this.pending.clear();
      });
    });
  }

  emit(event, payload) {
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`AFFiNE sync acknowledgement timed out for ${event}`));
      }, 15000);
      this.pending.set(id, {
        resolve: value => { clearTimeout(timeout); resolve(value); },
        reject: error => { clearTimeout(timeout); reject(error); },
      });
      this.socket.send(`42${id}${JSON.stringify([event, payload])}`);
    });
  }

  close() {
    this.socket?.close();
  }
}

function payloadData(value, operation) {
  if (!value?.data) fail(`AFFiNE ${operation} returned no data`);
  return value.data;
}

async function pushFixture(cookie, workspaceId, docId) {
  const document = new Y.Doc();
  document.getText('homelab-recovery').insert(0, MARKER);
  const update = Buffer.from(Y.encodeStateAsUpdate(document)).toString('base64');
  const session = new SyncSession(cookie);
  await session.connect();
  try {
    const joined = payloadData(await session.emit('space:join', {
      spaceType: 'workspace', spaceId: workspaceId, clientVersion: '0.27.4',
    }), 'join');
    if (!joined.success) fail('AFFiNE sync join was rejected');
    const pushed = payloadData(await session.emit('space:push-doc-update', {
      spaceType: 'workspace', spaceId: workspaceId, docId, update,
    }), 'push');
    if (!pushed.accepted) fail('AFFiNE document update was rejected');
  } finally {
    session.close();
  }
}

async function readFixture(cookie, workspaceId, docId) {
  const session = new SyncSession(cookie);
  await session.connect();
  try {
    const joined = payloadData(await session.emit('space:join', {
      spaceType: 'workspace', spaceId: workspaceId, clientVersion: '0.27.4',
    }), 'join');
    if (!joined.success) fail('AFFiNE second-session sync join was rejected');
    const loaded = payloadData(await session.emit('space:load-doc', {
      spaceType: 'workspace', spaceId: workspaceId, docId,
    }), 'load');
    const document = new Y.Doc();
    Y.applyUpdate(document, Buffer.from(loaded.missing, 'base64'));
    const value = document.getText('homelab-recovery').toString();
    if (value !== MARKER) fail('AFFiNE recovered document marker differs');
    return {
      marker: value,
      marker_sha256: crypto.createHash('sha256').update(value).digest('hex'),
      state_sha256: crypto.createHash('sha256').update(Buffer.from(Y.encodeStateAsUpdate(document))).digest('hex'),
    };
  } finally {
    session.close();
  }
}

async function main() {
  const mode = process.argv[2];
  if (mode === 'seed') {
    await initializeAdmin();
    const first = await login();
    const workspaceId = await createWorkspace(first.cookie);
    const docId = crypto.randomUUID();
    await pushFixture(first.cookie, workspaceId, docId);
    const second = await login();
    const evidence = await readFixture(second.cookie, workspaceId, docId);
    console.log(JSON.stringify({
      kind: 'affine-synthetic-document-v1', workspace_id: workspaceId, doc_id: docId,
      first_user_id: first.userId, second_user_id: second.userId,
      independent_sessions: true, ...evidence,
    }));
    return;
  }
  if (mode === 'verify') {
    const workspaceId = process.argv[3];
    const docId = process.argv[4];
    if (!workspaceId || !docId) fail('verify requires workspace and document ids');
    const session = await login();
    const evidence = await readFixture(session.cookie, workspaceId, docId);
    console.log(JSON.stringify({
      kind: 'affine-synthetic-document-v1', workspace_id: workspaceId, doc_id: docId,
      second_user_id: session.userId, independent_sessions: true, ...evidence,
    }));
    return;
  }
  fail('Expected seed or verify mode');
}

main().catch(error => {
  console.error(error.message);
  process.exitCode = 1;
});
