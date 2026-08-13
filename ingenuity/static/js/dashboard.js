const elements = {
    cpu: document.getElementById("cpu-value"),
    ram: document.getElementById("ram-value"),
    temperature: document.getElementById("temperature-value"),
    uptime: document.getElementById("uptime-value"),

    robotStatus: document.getElementById("robot-status"),
    robotMode: document.getElementById("robot-mode"),

    motorsStatus: document.getElementById("motors-status"),
    cameraStatus: document.getElementById("camera-status"),
    aiStatus: document.getElementById("ai-status"),

    aiObjects: document.getElementById("ai-objects"),
    aiInferenceFps: document.getElementById("ai-inference-fps"),
    aiObjectList: document.getElementById("ai-object-list"),

    networkIp: document.getElementById("network-ip"),

    connectionStatus: document.getElementById(
        "connection-status"
    ),
};


function setText(element, value) {

    if (element) {
        element.textContent = value;
    }
}


/*
 * ======================================
 * DASHBOARD UPDATE
 * ======================================
 */

function updateDashboard(data) {

    /*
     * SYSTEM
     */

    const cpu = Number(
        data.cpu ?? 0
    );

    const ram = Number(
        data.ram ?? 0
    );

    const temperature =
        data.temperature;

    const uptime = Number(
        data.uptime ?? 0
    );


    setText(
        elements.cpu,
        `${cpu.toFixed(1)}%`
    );


    setText(
        elements.ram,
        `${ram.toFixed(1)}%`
    );


    setText(
        elements.temperature,
        temperature !== null &&
        temperature !== undefined
            ? `${Number(temperature).toFixed(1)} °C`
            : "--"
    );


    setText(
        elements.uptime,
        formatUptime(uptime)
    );


    /*
     * NETWORK
     */

    setText(
        elements.networkIp,
        data.ip ?? "--"
    );


    /*
     * ROBOT
     */

    setText(
        elements.robotStatus,
        "Online"
    );


    setText(
        elements.robotMode,
        "manual"
    );


    /*
     * COMPONENTS
     */

    setText(
        elements.motorsStatus,
        "standby"
    );


    setText(
        elements.cameraStatus,
        data.camera
            ? "online"
            : "offline"
    );


    /*
     * AI / OBJECT DETECTION
     */

    const cameraData =
        data.camera_data ?? {};

    const detections =
        Array.isArray(cameraData.objects)
            ? cameraData.objects
            : [];

    const objectCount =
        detections.length;

    const inferenceFps =
        Number(
            cameraData.inference_fps ?? 0
        );


    setText(
        elements.aiStatus,
        data.camera
            ? "online"
            : "offline"
    );


    setText(
        elements.aiObjects,
        `${objectCount} ${
            objectCount === 1
                ? "oggetto"
                : "oggetti"
        }`
    );


    setText(
        elements.aiInferenceFps,
        `${inferenceFps.toFixed(1)} FPS`
    );


    updateObjectList(
        detections
    );


    /*
     * CONNECTION
     */

    if (elements.connectionStatus) {

        elements.connectionStatus.textContent =
            "ONLINE";

        elements.connectionStatus.classList.add(
            "connected"
        );

        elements.connectionStatus.classList.remove(
            "disconnected"
        );
    }
}


/*
 * ======================================
 * OBJECT LIST
 * ======================================
 */

function updateObjectList(
    detections
) {

    if (!elements.aiObjectList) {
        return;
    }


    if (detections.length === 0) {

        elements.aiObjectList.textContent =
            "Nessun oggetto rilevato";

        return;
    }


    const names = detections.map(
        detection => {

            if (
                typeof detection ===
                "string"
            ) {
                return detection;
            }


            if (
                detection &&
                typeof detection ===
                "object"
            ) {

                return (
                    detection.name ??
                    detection.class_name ??
                    detection.label ??
                    (
                        detection.class_id !==
                        undefined
                            ? `Classe ${detection.class_id}`
                            : "Oggetto"
                    )
                );
            }


            return "Oggetto";
        }
    );


    const counts = {};


    names.forEach(
        name => {

            counts[name] =
                (counts[name] ?? 0) + 1;
        }
    );


    elements.aiObjectList.innerHTML =
        Object.entries(counts)
            .map(
                ([name, count]) =>
                    `<div>${name} × ${count}</div>`
            )
            .join("");
}


/*
 * ======================================
 * UPTIME
 * ======================================
 */

function formatUptime(
    seconds
) {

    let remaining =
        Math.max(
            0,
            Number(seconds) || 0
        );


    const days =
        Math.floor(
            remaining / 86400
        );

    remaining %= 86400;


    const hours =
        Math.floor(
            remaining / 3600
        );

    remaining %= 3600;


    const minutes =
        Math.floor(
            remaining / 60
        );


    if (days > 0) {

        return `${days}g ${hours}h ${minutes}m`;
    }


    if (hours > 0) {

        return `${hours}h ${minutes}m`;
    }


    return `${minutes}m`;
}


/*
 * ======================================
 * WEBSOCKET
 * ======================================
 */

let socket;


function connectWebSocket() {

    const protocol =
        window.location.protocol ===
        "https:"
            ? "wss"
            : "ws";


    const url =
        `${protocol}://${window.location.host}/ws/status`;


    console.log(
        "Connessione WebSocket:",
        url
    );


    socket =
        new WebSocket(url);


    socket.onopen = () => {

        console.log(
            "WebSocket telemetria connesso"
        );
    };


    socket.onmessage = (
        event
    ) => {

        try {

            const data =
                JSON.parse(
                    event.data
                );


            updateDashboard(
                data
            );

        } catch (error) {

            console.error(
                "Errore parsing telemetria:",
                error
            );
        }
    };


    socket.onclose = () => {

        console.warn(
            "WebSocket disconnesso"
        );


        if (
            elements.connectionStatus
        ) {

            elements.connectionStatus.textContent =
                "OFFLINE";

            elements.connectionStatus.classList.remove(
                "connected"
            );

            elements.connectionStatus.classList.add(
                "disconnected"
            );
        }


        setTimeout(
            connectWebSocket,
            2000
        );
    };


    socket.onerror = (
        error
    ) => {

        console.error(
            "Errore WebSocket:",
            error
        );
    };
}


/*
 * ======================================
 * START
 * ======================================
 */

connectWebSocket();