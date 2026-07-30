import cv2


class Camera:

    def __init__(self):
        self.cap = cv2.VideoCapture(0)

    def frames(self):
        while True:

            success, frame = self.cap.read()

            if not success:
                break

            _, buffer = cv2.imencode(".jpg", frame)

            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n"
                + buffer.tobytes()
                + b"\r\n"
            )
