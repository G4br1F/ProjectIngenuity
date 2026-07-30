// ======================================
// Project Ingenuity Dashboard
// ======================================

let socket = null;

// ---------- Utility ----------

function $(id) {
    return document.getElementById(id);
}

function setText(id, value) {
    const el = $(id);
    if (el) el.textContent = value;
}

function setProgress(id, value) {

    const bar = $(id);
    if (!bar) return;

    value = Math.max(0, Math.min(100, value));

    bar.style.width = value + "%";

    bar.classList.remove(
        "bg-success",
        "bg-warning",
        "bg-danger"
    );

    if (value < 60)
        bar.classList.add("bg-success");
    else if (value < 85)
        bar.classList.add("bg-warning");
    else
        bar.classList.add("bg-danger");
}

function formatUptime(seconds) {

    const days = Math.floor(seconds / 86400);
    seconds %= 86400;

    const hours = Math.floor(seconds / 3600);
    seconds %= 3600;

    const minutes = Math.floor(seconds / 60);
    seconds %= 60;

    return `${days}g ${hours}h ${minutes}m ${seconds}s`;
}

function log(message) {

    const area = $("system-log");

    if (!area)
        return;

    const now = new Date().toLocaleTimeString();

    area.innerHTML =
        `[${now}] ${message}<br>` +
        area.innerHTML;

}

// ---------- Dashboard ----------

function updateDashboard(data) {

    // Compatibile sia con il JSON attuale
    // sia con quello futuro (system.cpu ecc.)

    const system = data.system ?? data;

    setText("cpu", system.cpu + " %");
    setText("ram", system.ram + " %");
    setText("disk", system.disk + " %");

    if (system.temperature !== null)
        setText("temperature", system.temperature + " °C");
    else
        setText("temperature", "--");

    setProgress("cpu-bar", system.cpu);
    setProgress("ram-bar", system.ram);
    setProgress("disk-bar", system.disk);

    if (system.temperature !== null)
        setProgress("temp-bar", system.temperature);

    setText("hostname", system.hostname);

    setText("ip", system.ip);

    setText(
        "camera",
        system.camera ? "🟢 Online" : "🔴 Offline"
    );

    setText(
        "uptime",
        formatUptime(system.uptime)
    );

    if (data.camera?.fps !== undefined)
        setText("fps", data.camera.fps);

    if (data.vision?.objects !== undefined)
        setText(
            "yolo",
            data.vision.objects.length + " oggetti"
        );
}

// ---------- WebSocket ----------

function connect() {

    const protocol =
        location.protocol === "https:"
            ? "wss"
            : "ws";

    socket = new WebSocket(
        `${protocol}://${location.host}/ws/status`
    );

    socket.onopen = () => {

        log("Connessione WebSocket stabilita.");

    };

    socket.onmessage = (event) => {

        const data = JSON.parse(event.data);

        updateDashboard(data);

    };

    socket.onclose = () => {

        log("Connessione persa. Riconnessione...");

        setTimeout(connect, 3000);

    };

    socket.onerror = () => {

        socket.close();

    };

}

window.addEventListener("load", connect);
