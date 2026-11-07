import threading
from types import SimpleNamespace
import pytest
from ingenuity.hardware.gimbal import Gimbal


def driver():
    g=Gimbal.__new__(Gimbal);g._lock=threading.RLock();g._closed=False
    g.pan_neutral=1558;g.tilt_neutral=1600
    g.pan_servo=SimpleNamespace(duty_cycle=0);g.tilt_servo=SimpleNamespace(duty_cycle=0)
    return g


@pytest.mark.parametrize('value',[float('nan'),float('inf'),90,-2])
def test_reject_angles_and_nonfinite_speed(value):
    g=driver()
    with pytest.raises(ValueError):g.pan(value)
    assert g.pan_servo.duty_cycle==0


def test_neutrals_and_channels():
    g=driver();g.stop()
    assert g.pan_servo.duty_cycle==round(1558/20000*65535)
    assert g.tilt_servo.duty_cycle==round(1600/20000*65535)
    assert Gimbal.PAN_CHANNEL!=Gimbal.TILT_CHANNEL


def test_both_axes_stopped_even_when_pan_fails():
    g=driver();calls=[]
    def failed(): raise OSError('bus failure')
    g.stop_pan=failed;g.stop_tilt=lambda:calls.append('tilt')
    with pytest.raises(OSError):g.stop()
    assert calls==['tilt']
