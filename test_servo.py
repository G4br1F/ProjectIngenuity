import time
import board
import busio
from adafruit_pca9685 import PCA9685


# ==========================
# I2C
# ==========================

i2c = busio.I2C(
    board.SCL,
    board.SDA
)


# ==========================
# PCA9685
# ==========================

pca = PCA9685(i2c)

pca.frequency = 50


# ==========================
# Servo
# ==========================

pan = pca.channels[0]
tilt = pca.channels[1]


def set_servo_angle(servo, angle):

    min_pulse = 500
    max_pulse = 2500

    pulse = (
        min_pulse
        + (angle / 180)
        * (max_pulse - min_pulse)
    )

    duty_cycle = int(
        pulse / 20000 * 65535
    )

    servo.duty_cycle = duty_cycle


def set_gimbal(pan_angle, tilt_angle):

    set_servo_angle(
        pan,
        pan_angle
    )

    set_servo_angle(
        tilt,
        tilt_angle
    )


# ==========================
# TEST
# ==========================

print("Center")

set_gimbal(90, 90)

time.sleep(2)


print("Position 1")

set_gimbal(60, 60)

time.sleep(2)


print("Position 2")

set_gimbal(120, 120)

time.sleep(2)


print("Center")

set_gimbal(90, 90)

time.sleep(2)


# ==========================
# STOP
# ==========================

pan.duty_cycle = 0
tilt.duty_cycle = 0

pca.deinit()

print("Test completed.")
