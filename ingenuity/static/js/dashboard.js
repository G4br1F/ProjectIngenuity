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


function setStatus(element, status) {

    if (!element) {
        return;
    }

    element.textContent = status;
}


async function updateDashboard() {

    try {

        const response = await fetch(
            "/api/status",
            {
                cache: "no-store",
            }
        );

        if (!response.ok) {
            throw new Error(
                `HTTP ${response.status}`
            );
        }

        const data = await response.json();

        const system = data.system;
        const robot = data.robot;
        const components = data.components;
        const network = data.network;


        /*
         * SYSTEM
         */

        setStatus(
            elements.cpu,
            `${system.cpu}%`
        );

        setStatus(
            elements.ram,
            `${system.memory.percent}%`
        );

        setStatus(
            elements.temperature,
            system.temperature !== null
                ? `${system.temperature} °C`
                : "--"
        );

        setStatus(
            elements.uptime,
            system.uptime_formatted
        );


        /*
         * ROBOT
         */

        setStatus(
            elements.robotStatus,
            robot.status === "online"
                ? "Online"
                : "Offline"
        );

        setStatus(
            elements.robotMode,
            robot.mode
        );


        /*
         * COMPONENTS
         */

        setStatus(
            elements.motorsStatus,
            components.motors.status
        );

        setStatus(
            elements.cameraStatus,
            components.camera.status
        );

        setStatus(
            elements.aiStatus,
            components.ai.status
        );


        /*
         * NETWORK
         */

        setStatus(
            elements.networkIp,
            network.ip
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

    } catch (error) {

        console.error(
            "Errore telemetria:",
            error
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
    }
}


updateDashboard();


setInterval(
    updateDashboard,
    2000
);