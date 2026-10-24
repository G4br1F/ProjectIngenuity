import time
import ncnn
import numpy as np
import cv2


MODEL_DIR = "yolo26n_ncnn_model"


def benchmark(num_threads):

    print(f"\n{'=' * 50}")
    print(f"NCNN - {num_threads} thread")
    print(f"{'=' * 50}")

    net = ncnn.Net()

    # CPU only
    net.opt.use_vulkan_compute = False

    # Controlliamo esplicitamente i thread NCNN
    net.opt.num_threads = num_threads

    net.opt.use_fp16_arithmetic = True
    net.opt.use_fp16_storage = True
    net.opt.use_fp16_packed = True

    net.load_param(f"{MODEL_DIR}/model.ncnn.param")
    net.load_model(f"{MODEL_DIR}/model.ncnn.bin")

    # Frame fittizio 160x90
    image = np.random.randint(
        0, 256, (90, 160, 3), dtype=np.uint8
    )

    mat = ncnn.Mat.from_pixels_resize(
        image,
        ncnn.Mat.PixelType.PIXEL_BGR,
        160,
        90,
        160,
        90,
    )

    # Warm-up
    for _ in range(3):
        ex = net.create_extractor()
        ex.input("in0", mat)
        ex.extract("out0")

    # Benchmark
    times = []

    for i in range(10):

        ex = net.create_extractor()

        start = time.perf_counter()

        ex.input("in0", mat)
        ret, out = ex.extract("out0")

        elapsed = time.perf_counter() - start

        if ret != 0:
            print("Errore NCNN:", ret)
            return

        times.append(elapsed)

        print(
            f"  inferenza {i + 1:02d}: "
            f"{elapsed * 1000:.1f} ms"
        )

    avg = sum(times) / len(times)
    fps = 1.0 / avg

    print()
    print(f"Media: {avg * 1000:.1f} ms")
    print(f"FPS teorici: {fps:.2f}")


for threads in (1, 2, 4):
    benchmark(threads)
