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

    networkIp: document.getElementById("network-ip"),

    connectionStatus: document.getElementById("connection-status"),
};


function setText(element, value) {

    if (element) {
        element.textContent = value;
    }
}


function updateDashboard(data) {

    /*
     * ==============================
     * SYSTEM
     * ==============================
     */

    const cpu = Number(data.cpu ?? 0);
    const ram = Number(data.ram ?? 0);
    const temperature = data.temperature;
    const uptime = Number(data.uptime ?? 0);


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
        temperature !== null
            ? `${Number(temperature).toFixed(1)} °C`
            : "--"
    );


    setText(
        elements.uptime,
        formatUptime(uptime)
    );


    /*
     * ==============================
     * NETWORK
     * ==============================
     */

    setText(
        elements.networkIp,
        data.ip ?? "--"
    );


    /*
     * ==============================
     * ROBOT
     * ==============================
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
     * ==============================
     * COMPONENTS
     * ==============================
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


    setText(
        elements.aiStatus,
        "online"
    );


    /*
     * ==============================
     * CONNECTION
     * ==============================
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


    /*
     * ==============================
     * CAMERA / AI
     * ==============================
     */

    if (data.camera_data) {

        console.log(
            "Camera:",
            data.camera_data
        );

    }
}


function formatUptime(seconds) {

    const days = Math.floor(
        seconds / 86400
    );

    seconds %= 86400;


    const hours = Math.floor(
        seconds / 3600
    );

    seconds %= 3600;


    const minutes = Math.floor(
        seconds / 60
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
 * ==============================
 * WEBSOCKET
 * ==============================
 */

let socket;


function connectWebSocket() {

    const protocol =
        window.location.protocol === "https:"
            ? "wss"
            : "ws";


    const url =
        `${protocol}://${window.location.host}/ws/status`;


    console.log(
        "Connessione WebSocket:",
        url
    );


    socket = new WebSocket(url);


    socket.onopen = () => {

        console.log(
            "WebSocket telemetria connesso"
        );

    };


    socket.onmessage = (event) => {

        try {

            const data =
                JSON.parse(event.data);


            updateDashboard(data);

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


        if (elements.connectionStatus) {

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


    socket.onerror = (error) => {

        console.error(
            "Errore WebSocket:",
            error
        );
    };
}


connectWebSocket();