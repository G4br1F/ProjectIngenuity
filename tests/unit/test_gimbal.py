import threading
from types import SimpleNamespace
import pytest
from ingenuity.hardware.gimbal import Gimbal


def driver():
    g=Gimbal.__new__(Gimbal);g._lock=threading.RLock();g._closed=False
    g.pan_neutral=1500;g.tilt_neutral=1500
    g.pca=SimpleNamespace(frequency=50.03)
    g.pan_servo=SimpleNamespace(duty_cycle=0);g.tilt_servo=SimpleNamespace(duty_cycle=0)
    return g


@pytest.mark.parametrize('value',[float('nan'),float('inf'),90,-2])
def test_reject_angles_and_nonfinite_speed(value):
    g=driver()
    with pytest.raises(ValueError):g.pan(value)
    assert g.pan_servo.duty_cycle==0


def test_neutrals_and_channels():
    g=driver();g.stop()
    assert g.pan_servo.duty_cycle==0
    assert g.tilt_servo.duty_cycle==0
    assert Gimbal.PAN_CHANNEL!=Gimbal.TILT_CHANNEL


def test_both_axes_stopped_even_when_pan_fails():
    g=driver();calls=[]
    def failed(): raise OSError('bus failure')
    g.stop_pan=failed;g.stop_tilt=lambda:calls.append('tilt')
    with pytest.raises(OSError):g.stop()
    assert calls==['tilt']


def test_calibrated_pan_pulses_use_driver_frequency():
    g=driver()
    g.pan(.2)
    assert g.pan_servo.duty_cycle==round(1550*50.03*65535/1_000_000)
    g.pan(-.4)
    assert g.pan_servo.duty_cycle==round(1400*50.03*65535/1_000_000)
    g.stop()
    assert g.pan_servo.duty_cycle==0
