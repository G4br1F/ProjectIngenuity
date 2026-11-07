"""Manual hardware diagnostic; invoke explicitly."""

def main():
    from dotenv import load_dotenv
    from pathlib import Path
    load_dotenv(Path(__file__).resolve().parent / ".env")
    import time
    from ingenuity.hardware.gimbal import Gimbal

    gimbal = None

    try:
        gimbal = Gimbal()

        print("PAN e TILT: neutro per 5 secondi")
        gimbal.stop()
        time.sleep(5)

        print("PAN: rotazione lenta per 1 secondo")
        gimbal.pan(0.10)
        time.sleep(1)

        print("PAN: arresto")
        gimbal.stop()
        time.sleep(3)

        print("Test terminato")

    finally:
        if gimbal is not None:
            gimbal.close()



if __name__ == "__main__":
    main()
