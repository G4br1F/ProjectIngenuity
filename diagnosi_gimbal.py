
import time
from adafruit_servokit import ServoKit

kit = ServoKit(channels=16)

def test_channel(channel):
    print(f"Test canale {channel}")

    # Comando neutro iniziale
    kit.continuous_servo[channel].throttle = 0
    time.sleep(2)

    # Breve impulso a bassa velocita'
    kit.continuous_servo[channel].throttle = 0.10
    time.sleep(0.25)

    # Ritorno al neutro
    kit.continuous_servo[channel].throttle = 0
    print("Neutro impostato")

try:
    test_channel(0)
    time.sleep(3)
    test_channel(1)

finally:
    kit.continuous_servo[0].throttle = 0
    kit.continuous_servo[1].throttle = 0
    print("Comandi di arresto inviati")
