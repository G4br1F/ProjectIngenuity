"""Manual check using the calibrated continuous-servo driver."""
import time
from ingenuity.hardware.gimbal import Gimbal

def main():
    from dotenv import load_dotenv
    from pathlib import Path
    load_dotenv(Path(__file__).resolve().parent / ".env")
    gimbal = Gimbal()
    try:
        gimbal.stop()
        print("Neutri calibrati su PAN=0 e TILT=1; osservazione per 10 secondi")
        time.sleep(10)
    finally:
        gimbal.close()

if __name__ == "__main__":
    main()
