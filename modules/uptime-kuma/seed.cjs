// Original bounded client for the pinned 2.5.5 Socket.IO interface.
// Credentials arrive on stdin only. Never echo server errors or auth tokens.
const request = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const { io } = require('socket.io-client');
const socket = io('http://127.0.0.1:3001', { transports: ['websocket'], reconnection: false, timeout: 10000 });
const ready = new Promise(resolve => socket.once('info', resolve));
const deadline = setTimeout(() => finish(false), 45000);
function finish(ok, result) {
    clearTimeout(deadline);
    socket.disconnect();
    if (ok) process.stdout.write(JSON.stringify(result));
    else process.stderr.write('Synthetic Kuma API operation failed; inspect private trial state.');
    process.exit(ok ? 0 : 2);
}
function call(event, ...args) {
    return new Promise((resolve, reject) => socket.timeout(12000).emit(event, ...args,
        (error, result) => error || result?.ok === false ? reject(new Error('API rejected')) : resolve(result)));
}
let monitors = {};
socket.on('monitorList', value => { monitors = value; });
socket.on('connect_error', () => finish(false));
socket.on('connect', async () => {
    try {
        await ready; // Server awaits its initial info event before registering handlers.
        if (!['seed', 'inspect-monitors'].includes(request.action)) throw new Error('action');
        const needsSetup = await call('needSetup');
        if (needsSetup) {
            if (request.action !== 'seed') throw new Error('not initialized');
            await call('setup', request.username, request.password);
        }
        await call('login', {username: request.username, password: request.password, token: ''});
        await call('getMonitorList');
        const specifications = [
            {name: 'Blueprint fixture', url: 'http://fixture:8080'},
            {name: 'Blueprint self-check', url: 'http://127.0.0.1:3001'},
        ];
        if (Object.values(monitors).some(m => !specifications.some(s => s.name === m.name))) throw new Error('foreign monitor');
        const ids = {};
        for (const spec of specifications) {
            let matching = Object.values(monitors).filter(m => m.name === spec.name);
            if (matching.length > 1) throw new Error('duplicate monitor');
            if (matching.length === 0) {
                if (request.action !== 'seed') throw new Error('missing monitor');
                const added = await call('add', {...spec, type: 'http', interval: 20, retryInterval: 20,
                    maxretries: 0, timeout: 5, method: 'GET', active: true, ignoreTls: false,
                    accepted_statuscodes: ['200-299'], notificationIDList: {}, upsideDown: false,
                    maxredirects: 3, resendInterval: 0, conditions: [],
                    kafkaProducerBrokers: [], kafkaProducerSaslOptions: {}, rabbitmqNodes: []});
                ids[spec.name] = added.monitorID;
            } else ids[spec.name] = matching[0].id;
            const {monitor} = await call('getMonitor', ids[spec.name]);
            if (monitor.url !== spec.url || monitor.type !== 'http' || monitor.interval !== 20 ||
                monitor.maxretries !== 0 || monitor.ignoreTls || monitor.upsideDown ||
                Object.values(monitor.notificationIDList || {}).some(Boolean)) throw new Error('monitor drift');
        }
        const pageResponse = await fetch('http://127.0.0.1:3001/api/status-page/blueprint');
        let page = pageResponse.ok ? await pageResponse.json() : null;
        if (!page && request.action === 'seed') {
            await call('addStatusPage', 'Blueprint synthetic status', 'blueprint');
            const {config} = await call('getStatusPage', 'blueprint');
            await call('saveStatusPage', 'blueprint', {...config,
                title: 'Blueprint synthetic status', description: 'Isolated test service only. No production monitors.',
                theme: 'dark', autoRefreshInterval: 30, showTags: false, showPoweredBy: true,
                footerText: 'Local-only recovery rehearsal', customCSS: '', domainNameList: [],
                analyticsType: null, analyticsId: '', analyticsScriptUrl: '', showOnlyLastHeartbeat: false,
                showCertificateExpiry: false, rssTitle: 'Synthetic status'}, '',
                [{name: 'Synthetic services', monitorList: [{id: ids['Blueprint fixture'], sendUrl: false}]}]);
            page = await (await fetch('http://127.0.0.1:3001/api/status-page/blueprint')).json();
        }
        const visible = page?.publicGroupList?.flatMap(g => g.monitorList.map(m => m.id));
        if (page?.config?.title !== 'Blueprint synthetic status' || visible?.length !== 1 ||
            visible[0] !== ids['Blueprint fixture']) throw new Error('status page drift');
        const evidence = [];
        for (const spec of specifications) {
            const beats = await call('getMonitorBeats', ids[spec.name], 24);
            const list = beats.data || beats.heartbeatList || beats.list;
            if (!Array.isArray(list)) throw new Error('heartbeat contract');
            evidence.push({name: spec.name, id: ids[spec.name],
                latest_status: list.length ? list[list.length - 1].status : null,
                heartbeat_count: list.length,
                observed_states: [...new Set(list.map(b => b.status))].sort()});
        }
        finish(true, {monitor_count: evidence.length, monitors: evidence, selected_public_monitor_count: visible.length});
    } catch (_) { finish(false); }
});
