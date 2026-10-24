
import time
from adafruit_servokit import ServoKit

kit = ServoKit(channels=16)

PAN = 0
TILT = 1

# Impostiamo il neutro nominale
kit.continuous_servo[PAN].throttle = 0
kit.continuous_servo[TILT].throttle = 0

print("Segnale neutro attivo su PAN e TILT.")
print("Il programma rimane attivo.")
print("Premi CTRL+C per terminare.")

try:
    while True:
        time.sleep(1)

except KeyboardInterrupt:
    print("Interruzione richiesta.")
    kit.continuous_servo[PAN].throttle = 0
    kit.continuous_servo[TILT].throttle = 0
