import time
import board
import busio
from adafruit_pca9685 import PCA9685

i2c = busio.I2C(board.SCL, board.SDA)
pca = PCA9685(i2c)
pca.frequency = 50
pan = pca.channels[0]

try:
    for pulse_us in (1540, 1543, 1545, 1547, 1550):
        print(f"PAN: {pulse_us} us per 5 secondi")
        pan.duty_cycle = round(pulse_us / 20000 * 65535)
        time.sleep(5)
finally:
    pan.duty_cycle = 0
    pca.deinit()
    i2c.deinit()
    print("Test terminato")
