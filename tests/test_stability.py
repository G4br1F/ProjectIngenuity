"""Manual hardware diagnostic; invoke explicitly."""

def main():
    from ingenuity.vision.camera_manager import CameraManager

    camera = CameraManager()

    count = 0

    try:
        while True:

            frame = camera.read()

            if frame is None:
                print("Errore")
                break

            count += 1

            if count % 100 == 0:
                print(f"{count} frame acquisiti")

    finally:
        camera.release()



if __name__ == "__main__":
    main()
