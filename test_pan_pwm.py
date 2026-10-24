import time
import board
import busio
from adafruit_pca9685 import PCA9685

i2c = busio.I2C(board.SCL, board.SDA)
pca = PCA9685(i2c)
pca.frequency = 50

pan = pca.channels[0]

def set_pulse(pulse_us):
    pan.duty_cycle = round(pulse_us / 20000 * 65535)

print("PAN: verifica neutro a 1545 us per 10 secondi")
set_pulse(1545)
time.sleep(10)
