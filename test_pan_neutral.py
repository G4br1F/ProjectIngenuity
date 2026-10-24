import time
import board
import busio
from adafruit_pca9685 import PCA9685

i2c = busio.I2C(board.SCL, board.SDA)
pca = PCA9685(i2c)
pca.frequency = 50
pan = pca.channels[0]

try:
    print("PAN a 1550 us: osservazione per 15 secondi")
    pan.duty_cycle = round(1550 / 20000 * 65535)
    time.sleep(15)
finally:
    pan.duty_cycle = 0
    pca.deinit()
    i2c.deinit()
    print("Test terminato")
