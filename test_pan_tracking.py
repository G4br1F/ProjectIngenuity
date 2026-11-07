"""Interactive hardware check; run explicitly, never during test collection."""
from contextlib import ExitStack
from ingenuity.vision.camera import Camera
from ingenuity.vision.tracking import TrackingManager
from ingenuity.hardware.gimbal import Gimbal
from ingenuity.hardware.pan_tracker import PanTracker


def main():
    from dotenv import load_dotenv
    from pathlib import Path
    load_dotenv(Path(__file__).resolve().parent / ".env")
    with ExitStack() as cleanup:
        camera = Camera()
        cleanup.callback(camera.stop)
        gimbal = Gimbal()
        cleanup.callback(gimbal.close)
        controller = PanTracker(camera,gimbal,TrackingManager())
        cleanup.callback(controller.stop)
        while True:
            batch = camera.get_detection_snapshot()
            print(controller.snapshot())
            for index,item in enumerate(batch['objects']):
                print(index,item['class'],item['center'])
            command = input('Numero=segui, s=stop, invio=aggiorna, q=esci: ').strip()
            if command == 'q':
                return
            if command == 's':
                controller.stop_tracking()
            elif command.isdigit():
                try:
                    controller.select(int(command),batch['version'])
                except ValueError as error:
                    print(error)


if __name__ == '__main__':
    main()
