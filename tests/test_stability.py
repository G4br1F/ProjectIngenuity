from ingenuity.vision.camera_manager import CameraManager

camera = CameraManager()

count = 0

while True:

    frame = camera.read()

    if frame is None:
        print("Errore")
        break

    count += 1

    if count % 100 == 0:
        print(f"{count} frame acquisiti")

camera.release()
