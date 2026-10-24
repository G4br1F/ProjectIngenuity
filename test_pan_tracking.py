import time

from ingenuity.vision.camera import Camera
from ingenuity.vision.tracking import TrackingManager
from ingenuity.hardware.gimbal import Gimbal


# ============================================================
# CONFIGURAZIONE
# ============================================================

IMAGE_WIDTH = 960

# Zona morta attorno al centro.
# Se l'oggetto è dentro questa zona, il PAN non si muove.
DEADBAND = 40

# Massimo movimento del servo per una singola correzione.
MAX_STEP = 3.0

# Quanto velocemente reagisce all'errore.
GAIN = 0.015

# Limiti meccanici già definiti nel Gimbal.
PAN_MIN = 10
PAN_MAX = 170


# ============================================================
# AVVIO
# ============================================================

camera = Camera()
gimbal = Gimbal()
tracker = TrackingManager(max_match_distance=180)

last_target_center_x = None

print()
print("========================================")
print("       INGenuity - PAN TRACKING")
print("========================================")
print()
print("Comandi:")
print("  numero  -> seleziona detection")
print("  s       -> STOP tracking")
print("  q       -> esci")
print()
print("Il TILT NON viene utilizzato.")
print()


try:

    while True:

        # ----------------------------------------------------
        # Detection attuali
        # ----------------------------------------------------

        detections = camera.get_detections()

        print(
            f"\rDetection: {len(detections)}",
            end="",
            flush=True
        )


        # ----------------------------------------------------
        # INPUT UTENTE NON BLOCCANTE
        # ----------------------------------------------------

        # Per il primo test usiamo input() manualmente.
        # Se non c'è target, il gimbal non viene comandato.

        if tracker.snapshot()["mode"] == "IDLE":

            print("\n")

            if detections:

                for i, detection in enumerate(detections):

                    print(
                        f"[{i}] "
                        f"{detection['class']} "
                        f"{detection['confidence']:.2f} "
                        f"center={detection['center']}"
                    )

                command = input(
                    "\nSeleziona target (numero), "
                    "s=stop, q=esci: "
                ).strip()

                if command == "q":
                    break

                if command == "s":
                    tracker.stop()
                    continue

                if command.isdigit():

                    index = int(command)

                    try:

                        target = tracker.select(
                            detections,
                            index
                        )

                        print(
                            "\nTARGET SELEZIONATO:",
                            target["target"]
                        )

                        last_target_center_x = None

                    except ValueError as error:

                        print(
                            f"Errore: {error}"
                        )

            else:

                time.sleep(0.1)

                continue


        # ----------------------------------------------------
        # AGGIORNA TRACKING
        # ----------------------------------------------------

        state = tracker.update(
            camera.get_detections()
        )


        # ----------------------------------------------------
        # TARGET PERSO
        # ----------------------------------------------------

        if state["mode"] == "LOST":

            print(
                "\nTARGET PERSO - PAN FERMO"
            )

            last_target_center_x = None

            time.sleep(0.1)

            continue


        # ----------------------------------------------------
        # TARGET
        # ----------------------------------------------------

        target = state["target"]

        if target is None:

            time.sleep(0.1)

            continue


        target_x = target["center"][0]

        image_center_x = IMAGE_WIDTH / 2

        error_x = target_x - image_center_x


        # ----------------------------------------------------
        # DEAD BAND
        # ----------------------------------------------------

        if abs(error_x) <= DEADBAND:

            print(
                f"\rTARGET CENTRATO | "
                f"X={target_x:.0f} "
                f"errore={error_x:+.0f}      ",
                end="",
                flush=True
            )

            time.sleep(0.05)

            continue


        # ----------------------------------------------------
        # CALCOLO CORREZIONE PAN
        # ----------------------------------------------------

        correction = error_x * GAIN

        correction = max(
            -MAX_STEP,
            min(MAX_STEP, correction)
        )


        current_angle = gimbal.pan_angle

        new_angle = current_angle + correction

        new_angle = max(
            PAN_MIN,
            min(PAN_MAX, new_angle)
        )


        # ----------------------------------------------------
        # MOVIMENTO PAN
        # ----------------------------------------------------

        gimbal.pan(new_angle)


        print(
            f"\rPAN "
            f"{current_angle:6.2f}° -> "
            f"{new_angle:6.2f}° | "
            f"X={target_x:6.0f} | "
            f"errore={error_x:+6.0f} | "
            f"step={correction:+.2f}°",
            end="",
            flush=True
        )


        time.sleep(0.05)


finally:

    print("\n\nArresto tracking...")

    tracker.stop()

    # Ferma il segnale PWM.
    gimbal.stop()
    gimbal.close()

    camera.stop()

    print("Test terminato.")
