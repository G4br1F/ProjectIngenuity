"""Manual hardware diagnostic; invoke explicitly."""

def main():
    from ingenuity.vision.camera_manager import CameraManager
    import cv2

    camera = CameraManager()

    try:
        while True:
            frame = camera.read()

            if frame is None:
                print("Errore lettura frame")
                break

            cv2.imshow("Test Camera", frame)

            if cv2.waitKey(1) == ord("q"):
                break

    finally:
        camera.release()
        cv2.destroyAllWindows()



if __name__ == "__main__":
    main()
