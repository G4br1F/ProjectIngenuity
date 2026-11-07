"""Manual hardware diagnostic; invoke explicitly."""

def main():
    from ingenuity.vision.camera_manager import CameraManager
    from ingenuity.vision.capture import Capture
    import cv2

    camera = CameraManager()
    capture = Capture()

    try:
        while True:
            frame = camera.read()

            if frame is None:
                raise RuntimeError("Acquisizione camera fallita")

            cv2.imshow("Capture Test", frame)

            key = cv2.waitKey(1)

            if key == ord("s"):
                capture.save(frame)

            if key == ord("q"):
                break

    finally:
        camera.release()
        cv2.destroyAllWindows()



if __name__ == "__main__":
    main()
