from ingenuity.vision.camera_manager import CameraManager
from ingenuity.vision.capture import Capture
import cv2

camera = CameraManager()
capture = Capture()

while True:
    frame = camera.read()

    cv2.imshow("Capture Test", frame)

    key = cv2.waitKey(1)

    if key == ord("s"):
        capture.save(frame)

    if key == ord("q"):
        break

camera.release()
cv2.destroyAllWindows()
