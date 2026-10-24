import time
import board
import busio
from adafruit_pca9685 import PCA9685

i2c = busio.I2C(board.SCL, board.SDA)
pca = PCA9685(i2c)
pca.frequency = 50

pan = pca.channels[1]
tilt = pca.channels[1]

try:
    pan.duty_cycle = 0
    tilt.duty_cycle = 0
    time.sleep(1)

    for pulse_us in (1600,):
        print(f"\nPAN: test a {pulse_us} us")

        pan.duty_cycle = int(
            pulse_us / 20000 * 65535
        )

        time.sleep(10)

        pan.duty_cycle = 0
        print("PWM disattivato; osserva se il servo si e fermato.")
        time.sleep(2)

finally:
    pan.duty_cycle = 0
    tilt.duty_cycle = 0
    pca.deinit()
    print("Test concluso.")
