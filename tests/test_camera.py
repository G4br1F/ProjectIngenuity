from ingenuity.vision.camera_manager import CameraManager
import cv2

camera = CameraManager()

while True:
    frame = camera.read()

    if frame is None:
        print("Errore lettura frame")
        break

    cv2.imshow("Test Camera", frame)

    if cv2.waitKey(1) == ord("q"):
        break

camera.release()
cv2.destroyAllWindows()
