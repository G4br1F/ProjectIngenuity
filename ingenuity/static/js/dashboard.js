/* Versioned selections: never use an index against a different detection batch. */
const byId = id => document.getElementById(id);
const setText = (id, text) => { const el = byId(id); if (el) el.textContent = text; };
let displayedVersion = -1;
let renderedKey = null;
let lastMessage = 0;
let reconnectTimer;
let socket;
let closing = false;

function message(text) { setText('tracking-message', text); }
function connection(online) {
    setText('connection-status', online ? 'ONLINE' : 'OFFLINE');
    byId('connection-status')?.classList.toggle('connected', online);
    byId('connection-status')?.classList.toggle('disconnected', !online);
    if (!online) {
        renderedKey = null;
        setText('robot-status', 'Offline');
        setText('camera-status', 'stato sconosciuto');
        setText('ai-status', 'stato sconosciuto');
        document.querySelectorAll('.tracking-button').forEach(b => { b.disabled = true; });
    }
}
async function trackingRequest(path, body) {
    const response = await fetch(path, {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)
    });
    if (response.status === 401) {
        window.location.assign('/login');
        throw new Error('Sessione scaduta');
    }
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Richiesta non valida');
    return data;
}
function updateObjects(camera, tracking) {
    const container = byId('ai-object-list');
    if (!container) return;
    const key = `${camera.version}:${camera.ai_online}:${tracking.actuation}`;
    if (key === renderedKey) return;
    renderedKey = key;
    container.replaceChildren();
    const detections = Array.isArray(camera.objects) ? camera.objects : [];
    displayedVersion = camera.version;
    if (!detections.length) {
        container.textContent = 'Nessun oggetto rilevato';
        return;
    }
    detections.forEach((detection, index) => {
        const row = document.createElement('div');
        row.className = 'ai-object-item';
        const label = document.createElement('span');
        label.textContent = `${detection.class} ${(Number(detection.confidence) * 100).toFixed(1)}%`;
        const button = document.createElement('button');
        button.className = 'tracking-button';
        button.type = 'button';
        button.textContent = 'SEGUI';
        button.disabled = !camera.ai_online || tracking.actuation !== 'enabled';
        const version = displayedVersion;
        button.addEventListener('click', async () => {
            button.disabled = true;
            try {
                const result = await trackingRequest('/api/tracking/select', {index, version});
                setText('tracking-status', result.tracking.mode);
                message('Bersaglio selezionato');
            } catch (error) { message(error.message); }
            finally { if (button.isConnected) button.disabled = false; }
        });
        row.append(label, button);
        container.append(row);
    });
}
function updateDashboard(data) {
    lastMessage = Date.now();
    connection(true);
    setText('cpu-value', `${Number(data.cpu).toFixed(1)}%`);
    setText('ram-value', `${Number(data.ram).toFixed(1)}%`);
    setText('temperature-value', data.temperature == null ? '--' : `${Number(data.temperature).toFixed(1)} °C`);
    const seconds = Math.max(0, Number(data.uptime) || 0);
    setText('uptime-value', `${Math.floor(seconds / 86400)}g ${Math.floor(seconds / 3600) % 24}h ${Math.floor(seconds / 60) % 60}m`);
    setText('network-ip', data.ip ?? '--');
    setText('robot-status', 'Online');
    const tracking = data.tracking ?? {};
    const camera = data.camera_data ?? {};
    setText('robot-mode', tracking.mode === 'TRACKING' ? 'tracking' : 'manual');
    setText('motors-status', tracking.pan_speed || tracking.tilt_speed ? 'comando movimento attivo' : 'standby');
    setText('camera-status', camera.online ? 'online' : 'offline');
    byId('camera-status')?.classList.toggle('status-ok', Boolean(camera.online));
    setText('ai-status', camera.ai_online ? 'online' : 'offline');
    setText('ai-objects', `${camera.objects?.length ?? 0} oggetti`);
    setText('ai-inference-fps', `${Number(camera.inference_fps ?? 0).toFixed(1)} FPS`);
    setText('tracking-status', tracking.mode ?? 'IDLE');
    if (tracking.mode === 'TRACKING' && !tracking.reason && !tracking.error && !camera.ai_error && !camera.camera_error) {
        message(tracking.control_reason === 'person_at_horizontal_edge'
            ? 'Persona al bordo: movimento sospeso finche rientra nell’inquadratura'
            : 'Inseguimento attivo');
    }
    if (tracking.reason || tracking.error || camera.ai_error || camera.camera_error) {
        message(tracking.reason || tracking.error || camera.ai_error || camera.camera_error);
    }
    updateObjects(camera, tracking);
}
function connectWebSocket() {
    if (closing) return;
    socket = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/status`);
    socket.onmessage = event => {
        try { updateDashboard(JSON.parse(event.data)); }
        catch (error) { message(`Telemetria non valida: ${error.message}`); }
    };
    socket.onclose = event => {
        connection(false);
        if (event.code === 1008) { location.assign('/login'); return; }
        if (!closing) reconnectTimer = setTimeout(connectWebSocket, 2000);
    };
    socket.onerror = () => socket.close();
}
byId('tracking-stop')?.addEventListener('click', async () => {
    try {
        const result = await trackingRequest('/api/tracking/stop');
        setText('tracking-status', result.tracking.mode);
        message('Gimbal fermata');
    } catch (error) { message(`STOP non confermato: ${error.message}`); }
});
const watchdog = setInterval(() => {
    if (!lastMessage || Date.now() - lastMessage > 3000) connection(false);
}, 1000);
window.addEventListener('pagehide', () => {
    closing = true;
    clearInterval(watchdog);
    clearTimeout(reconnectTimer);
    socket?.close();
});
connection(false);
connectWebSocket();
