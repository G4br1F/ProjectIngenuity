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
trackingStatus:
    document.getElementById(
        "tracking-status"
    ),

trackingStop:
    document.getElementById(
        "tracking-stop"
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

const tracking =
    data.tracking ?? {};

const trackingMode =
    tracking.mode ?? "IDLE";

setText(
    elements.trackingStatus,
    trackingMode
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


function updateObjectList(detections) {

    if (!elements.aiObjectList) {
        return;
    }

    if (detections.length === 0) {

        elements.aiObjectList.innerHTML =
            `<div class="ai-empty">
                Nessun oggetto rilevato
            </div>`;

        return;
    }

    elements.aiObjectList.innerHTML =
        detections.map((detection, index) => {

            const name =
                detection?.class ??
                "Oggetto";

            const confidence =
                Number(
                    detection?.confidence ?? 0
                );

            const percentage =
                (confidence * 100).toFixed(1);

            return `
                <div class="ai-object-item">

                    <div class="ai-object-info">

                        <strong>
                            ${name}
                        </strong>

                        <span>
                            ${percentage}%
                        </span>

                    </div>

                    <button
                        type="button"
                        class="tracking-button"
                        data-detection-index="${index}"
                    >
                        SEGUI
                    </button>

                </div>
            `;

        }).join("");

    attachTrackingButtons();
}
function attachTrackingButtons() {

    const buttons =
        document.querySelectorAll(
            ".tracking-button"
        );

    buttons.forEach(button => {

        button.addEventListener(
            "click",
            async () => {

                const index =
                    Number(
                        button.dataset.detectionIndex
                    );

                try {

                    const response =
                        await fetch(
                            "/api/tracking/select",
                            {
                                method: "POST",

                                headers: {
                                    "Content-Type":
                                        "application/json"
                                },

                                body: JSON.stringify({
                                    index: index
                                })
                            }
                        );

                    const data =
                        await response.json();

                    if (!response.ok) {

                        console.error(
                            "Errore selezione:",
                            data
                        );

                        return;
                    }

                    console.log(
                        "Target selezionato:",
                        data
                    );

                } catch (error) {

                    console.error(
                        "Errore tracking:",
                        error
                    );
                }

            }
        );

    });
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

async function stopTracking() {

    try {

        const response =
            await fetch(
                "/api/tracking/stop",
                {
                    method: "POST"
                }
            );

        const data =
            await response.json();

        if (!response.ok) {

            console.error(
                "Errore STOP:",
                data
            );

            return;
        }

        setText(
            elements.trackingStatus,
            "IDLE"
        );

        console.log(
            "Tracking fermato"
        );

    } catch (error) {

        console.error(
            "Errore STOP tracking:",
            error
        );
    }
}

/*
 * ======================================
 * START
 * ======================================
 */

if (elements.trackingStop) {

    elements.trackingStop.addEventListener(
        "click",
        stopTracking
    );
}

connectWebSocket();
