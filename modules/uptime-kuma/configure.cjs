// Bounded desired-state client for the pinned Uptime Kuma 2.5.5 Socket.IO API.
// Credentials and notification secrets arrive on stdin. Never print endpoints,
// credentials, provider responses, or server error text.
const request = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const { io } = require('socket.io-client');
const socket = io('http://127.0.0.1:3001', {
    transports: ['websocket'], reconnection: false, timeout: 10000,
});
const deadline = setTimeout(() => finish(false), 60000);
let stage = 'connect';
let monitors = {};
let notifications = [];
let monitorRevision = 0;
let notificationRevision = 0;
socket.on('monitorList', value => { monitors = value || {}; monitorRevision += 1; });
socket.on('notificationList', value => { notifications = value || []; notificationRevision += 1; });

function finish(ok, result) {
    clearTimeout(deadline);
    socket.disconnect();
    if (ok) process.stdout.write(JSON.stringify(result));
    else process.stderr.write('Kuma configuration operation failed at safe stage ' + stage + '; inspect private module state.');
    process.exit(ok ? 0 : 2);
}

function call(event, ...args) {
    return new Promise((resolve, reject) => socket.timeout(15000).emit(event, ...args,
        (error, result) => error || result?.ok === false ? reject(new Error('API rejected')) : resolve(result)));
}

function waitFor(test, milliseconds = 12000) {
    const started = Date.now();
    return new Promise((resolve, reject) => {
        const check = () => {
            if (test()) return resolve();
            if (Date.now() - started > milliseconds) return reject(new Error('API state timeout'));
            setTimeout(check, 50);
        };
        check();
    });
}

function same(left, right) {
    return JSON.stringify(left) === JSON.stringify(right);
}

function notificationProjection(value) {
    const stored = typeof value.config === 'string' ? JSON.parse(value.config) : value;
    const normalized = {...stored, name: value.name ?? stored.name,
        isDefault: Boolean(value.isDefault ?? stored.isDefault)};
    const fields = normalized.type === 'webhook'
        ? ['name', 'type', 'isDefault', 'webhookURL', 'httpMethod', 'webhookContentType',
           'webhookCustomBody', 'webhookAdditionalHeaders']
        : ['name', 'type', 'isDefault', 'smtpHost', 'smtpPort', 'smtpSecure',
           'smtpIgnoreTLSError', 'smtpIgnoreSTARTTLS', 'smtpUsername', 'smtpPassword',
           'smtpFrom', 'smtpTo', 'smtpCC', 'smtpBCC', 'customSubject', 'customBody', 'htmlBody'];
    return Object.fromEntries(fields.map(key => [key, normalized[key] ?? null]));
}

function monitorProjection(value) {
    const notifications = Object.entries(value.notificationIDList || {})
        .filter(([, enabled]) => Boolean(enabled)).map(([id]) => Number(id)).sort((a, b) => a - b);
    return {
        name: value.name, type: value.type, url: value.url, interval: value.interval,
        retryInterval: value.retryInterval, maxretries: value.maxretries, timeout: value.timeout,
        method: value.method, active: Boolean(value.active), ignoreTls: Boolean(value.ignoreTls),
        accepted_statuscodes: value.accepted_statuscodes, upsideDown: Boolean(value.upsideDown),
        maxredirects: value.maxredirects, resendInterval: value.resendInterval,
        notificationIDs: notifications,
    };
}

async function refreshMonitors() {
    const revision = monitorRevision;
    await call('getMonitorList');
    await waitFor(() => monitorRevision > revision);
}

async function configure() {
    stage = 'validate-request';
    if (!['apply-config', 'inspect-config', 'test-notifications'].includes(request.action)) throw new Error('action');
    if (!request.configuration || request.configuration.schema_version !== 1) throw new Error('configuration');
    stage = 'authenticate';
    const needsSetup = await call('needSetup');
    if (needsSetup) throw new Error('not initialized');
    const notificationReady = notificationRevision;
    await call('login', {username: request.username, password: request.password, token: ''});
    await refreshMonitors();
    await waitFor(() => notificationRevision > notificationReady);

    stage = 'inventory';
    const desiredNotifications = request.configuration.notifications;
    const desiredMonitors = request.configuration.monitors;
    const allowedNotificationNames = new Set(desiredNotifications.map(row => row.api.name));
    const allowedMonitorNames = new Set(desiredMonitors.map(row => row.api.name));
    if (notifications.some(row => !allowedNotificationNames.has(row.name))) throw new Error('foreign notification');
    if (Object.values(monitors).some(row => !allowedMonitorNames.has(row.name))) throw new Error('foreign monitor');
    for (const name of allowedNotificationNames) {
        if (notifications.filter(row => row.name === name).length > 1) throw new Error('duplicate notification');
    }
    for (const name of allowedMonitorNames) {
        if (Object.values(monitors).filter(row => row.name === name).length > 1) throw new Error('duplicate monitor');
    }

    if (request.action === 'apply-config') {
        stage = 'apply-notifications';
        for (const desired of desiredNotifications) {
            const existing = notifications.find(row => row.name === desired.api.name);
            await call('addNotification', desired.api, existing?.id ?? null);
        }
        // A successful mutation emits a fresh notification list.
        await waitFor(() => desiredNotifications.every(row => notifications.some(item => item.name === row.api.name)));
    }

    stage = 'verify-notifications';
    const notificationIDs = {};
    for (const desired of desiredNotifications) {
        const existing = notifications.find(row => row.name === desired.api.name);
        if (!existing) throw new Error('missing notification');
        notificationIDs[desired.id] = Number(existing.id);
        if (!same(notificationProjection(existing), notificationProjection(desired.api))) throw new Error('notification drift');
    }

    if (request.action === 'test-notifications') {
        stage = 'test-notifications';
        for (const desired of desiredNotifications) await call('testNotification', desired.api);
        return {
            configuration_hash: request.configuration.configuration_hash,
            tested_notification_count: desiredNotifications.length,
            notifications: desiredNotifications.map(row => ({id: row.id, name: row.api.name, type: row.api.type})),
        };
    }

    stage = 'apply-monitors';
    const monitorIDs = {};
    for (const desired of desiredMonitors) {
        const wantedNotificationIDs = desired.notification_ids.map(id => notificationIDs[id]).sort((a, b) => a - b);
        let existing = Object.values(monitors).find(row => row.name === desired.api.name);
        if (!existing && request.action === 'apply-config') {
            const notificationIDList = Object.fromEntries(wantedNotificationIDs.map(id => [id, true]));
            const added = await call('add', {...desired.api, notificationIDList});
            monitorIDs[desired.id] = Number(added.monitorID);
            await refreshMonitors();
            existing = Object.values(monitors).find(row => Number(row.id) === monitorIDs[desired.id]);
        } else if (existing && request.action === 'apply-config') {
            const response = await call('getMonitor', existing.id);
            const notificationIDList = Object.fromEntries(wantedNotificationIDs.map(id => [id, true]));
            await call('editMonitor', {...response.monitor, ...desired.api, id: existing.id, notificationIDList});
            await refreshMonitors();
            existing = Object.values(monitors).find(row => Number(row.id) === Number(existing.id));
        }
        if (!existing) throw new Error('missing monitor');
        monitorIDs[desired.id] = Number(existing.id);
        const actual = monitorProjection(existing);
        const expected = monitorProjection({...desired.api,
            notificationIDList: Object.fromEntries(wantedNotificationIDs.map(id => [id, true]))});
        if (!same(actual, expected)) throw new Error('monitor drift');
    }

    stage = 'apply-status-page';
    const page = request.configuration.status_page;
    let pageResponse = await fetch('http://127.0.0.1:3001/api/status-page/' + encodeURIComponent(page.slug));
    if (!pageResponse.ok && request.action === 'apply-config') {
        await call('addStatusPage', page.title, page.slug);
        pageResponse = await fetch('http://127.0.0.1:3001/api/status-page/' + encodeURIComponent(page.slug));
    }
    if (!pageResponse.ok) throw new Error('missing status page');
    if (request.action === 'apply-config') {
        const {config} = await call('getStatusPage', page.slug);
        const groups = page.groups.map(group => ({name: group.name,
            monitorList: group.monitor_ids.map(id => ({id: monitorIDs[id], sendUrl: group.show_urls}))}));
        await call('saveStatusPage', page.slug, {...config,
            title: page.title, description: page.description, theme: page.theme,
            autoRefreshInterval: page.refresh_seconds, showTags: page.show_tags,
            showPoweredBy: page.show_powered_by, footerText: page.footer,
            customCSS: '', domainNameList: [], analyticsType: null, analyticsId: '',
            analyticsScriptUrl: '', showOnlyLastHeartbeat: page.show_only_last_heartbeat,
            showCertificateExpiry: page.show_certificate_expiry, rssTitle: page.title}, '', groups);
        pageResponse = await fetch('http://127.0.0.1:3001/api/status-page/' + encodeURIComponent(page.slug));
    }
    const actualPage = await pageResponse.json();
    const actualGroups = (actualPage.publicGroupList || []).map(group => ({name: group.name,
        monitor_ids: group.monitorList.map(item => Number(item.id)),
        show_urls: group.monitorList.every(item => Boolean(item.sendUrl))}));
    const expectedGroups = page.groups.map(group => ({name: group.name,
        monitor_ids: group.monitor_ids.map(id => monitorIDs[id]), show_urls: group.show_urls}));
    if (actualPage.config?.title !== page.title || actualPage.config?.description !== page.description ||
        actualPage.config?.theme !== page.theme || !same(actualGroups, expectedGroups)) throw new Error('status page drift');

    stage = 'complete';
    return {
        configuration_hash: request.configuration.configuration_hash,
        monitor_count: desiredMonitors.length,
        notification_count: desiredNotifications.length,
        status_page: page.slug,
        monitors: desiredMonitors.map(row => ({id: row.id, name: row.api.name})),
        notifications: desiredNotifications.map(row => ({id: row.id, name: row.api.name, type: row.api.type})),
        applied: request.action === 'apply-config',
    };
}

socket.on('connect_error', () => finish(false));
socket.on('connect', async () => {
    try { finish(true, await configure()); }
    catch (_) { finish(false); }
});
