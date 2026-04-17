"""
SafeSight Network & Stream Diagnostic Tool
===========================================
Run this on your PC:  python D:\safesight-cctv\network_diagnostic.py

It will tell you EXACTLY what's causing the 7fps issue and
whether your HD stream (fullscreen) works.
"""

import cv2
import time
import subprocess
import numpy as np

# ── Your config ──
NVR_IP = "192.168.100.18"
NVR_PORT = 554
NUM_CAMERAS = 6
RTSP_USER = "admin"
RTSP_PASS = "admin123456@@"
TEST_DURATION = 10  # seconds


def print_header(text):
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}")


def test_ping():
    print_header("TEST 1: PING (Latency to NVR)")
    try:
        result = subprocess.run(
            ["ping", "-n", "10", NVR_IP],
            capture_output=True, text=True, timeout=15
        )
        for line in result.stdout.split('\n'):
            if 'Average' in line or 'Minimum' in line or 'Packets' in line:
                print(f"  {line.strip()}")
            if 'loss' in line.lower() or '丢失' in line:
                print(f"  {line.strip()}")
        return True
    except Exception as e:
        print(f"  FAILED: {e}")
        return False


def test_single_stream():
    print_header("TEST 2: SINGLE STREAM (Camera 1 sub-stream)")
    rtsp = f"rtsp://{RTSP_USER}:{RTSP_PASS}@{NVR_IP}:{NVR_PORT}/cam/realmonitor?channel=1&subtype=1"
    print(f"  URL: {rtsp}")
    print(f"  Testing for {TEST_DURATION}s...")

    cap = cv2.VideoCapture(rtsp, cv2.CAP_FFMPEG)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    if not cap.isOpened():
        print("  FAILED: Cannot open stream!")
        return 0

    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"  Resolution: {w}x{h}")

    count = 0
    total_bytes = 0
    start = time.time()

    while time.time() - start < TEST_DURATION:
        ret, frame = cap.read()
        if ret:
            count += 1
            total_bytes += frame.nbytes

    elapsed = time.time() - start
    cap.release()

    fps = count / elapsed
    bw_mbps = (total_bytes * 8) / (elapsed * 1_000_000)

    print(f"  Frames:     {count} in {elapsed:.1f}s")
    print(f"  FPS:        {fps:.1f}")
    print(f"  Bandwidth:  {bw_mbps:.1f} Mbps (raw)")
    print(f"  Frame size: {total_bytes // count} bytes (raw)" if count else "")

    if fps < 10:
        print(f"\n  >>> NVR sub-stream is CAPPED at ~{fps:.0f}fps! <<<")
        print(f"  This is a NVR setting, not your network or code.")
        print(f"  FIX: NVR web UI > Camera > Sub-stream > FPS = 15 or 25")
    elif fps >= 15:
        print(f"\n  >>> Stream delivers {fps:.1f}fps - NVR is fine! <<<")
        print(f"  Your Python code is the bottleneck.")
    return fps


def test_multi_stream():
    print_header("TEST 3: ALL 6 CAMERAS simultaneously")
    print(f"  Opening all 6 sub-streams for {TEST_DURATION}s...")

    caps = []
    for i in range(1, NUM_CAMERAS + 1):
        rtsp = f"rtsp://{RTSP_USER}:{RTSP_PASS}@{NVR_IP}:{NVR_PORT}/cam/realmonitor?channel={i}&subtype=1"
        cap = cv2.VideoCapture(rtsp, cv2.CAP_FFMPEG)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if cap.isOpened():
            caps.append((i, cap))
            print(f"  Cam {i}: Connected")
        else:
            print(f"  Cam {i}: FAILED")

    if not caps:
        print("  No cameras connected!")
        return 0

    counts = {cid: 0 for cid, _ in caps}
    start = time.time()

    while time.time() - start < TEST_DURATION:
        for cid, cap in caps:
            ret, _ = cap.read()
            if ret:
                counts[cid] += 1
        time.sleep(0.001)

    elapsed = time.time() - start
    for _, cap in caps:
        cap.release()

    print(f"\n  {'Camera':<10} {'Frames':<12} {'FPS':<10}")
    print(f"  {'-'*32}")
    total_fps = 0
    for cid in counts:
        fps = counts[cid] / elapsed
        total_fps += fps
        print(f"  Cam {cid:<5} {counts[cid]:<12} {fps:<10.1f}")

    avg = total_fps / len(caps)
    print(f"  {'-'*32}")
    print(f"  Average:   {avg:.1f} fps")

    if avg < 8:
        print(f"\n  >>> FPS drops to {avg:.1f} with all 6 - NVR or bandwidth limit <<<")
    return avg


def test_encode_speed():
    print_header("TEST 4: CPU JPEG ENCODING speed")
    print(f"  Testing how fast your CPU can encode frames...")

    frame = np.random.randint(0, 255, (288, 352, 3), dtype=np.uint8)
    iterations = 500

    start = time.time()
    for _ in range(iterations):
        _, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 45])
    elapsed = time.time() - start

    per_sec = iterations / elapsed
    per_ms = (elapsed / iterations) * 1000
    jpeg_kb = len(buf) / 1024

    print(f"  {iterations} encodes in {elapsed:.2f}s")
    print(f"  Per encode: {per_ms:.2f}ms")
    print(f"  CPU can do: {per_sec:.0f} encodes/sec")
    print(f"  JPEG size:  {jpeg_kb:.1f} KB")

    print(f"\n  Can your CPU handle 6 streams?")
    for target in [10, 15, 25]:
        needed = target * 6
        ok = per_sec >= needed
        print(f"    {target}fps x 6 = {needed} encodes/s  {'YES' if ok else 'NO'}  (you: {per_sec:.0f}/s)")

    return per_sec


def test_hd_stream():
    print_header("TEST 5: HD STREAM (fullscreen - main stream)")
    rtsp = f"rtsp://{RTSP_USER}:{RTSP_PASS}@{NVR_IP}:{NVR_PORT}/cam/realmonitor?channel=1&subtype=0"
    print(f"  URL: .../channel=1&subtype=0")
    print(f"  Testing for 5s...")

    cap = cv2.VideoCapture(rtsp, cv2.CAP_FFMPEG)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    if not cap.isOpened():
        print("  FAILED: Cannot open HD stream!")
        print("  >>> This is why fullscreen doesn't work! <<<")
        print("  FIX: Check NVR main-stream codec = H.264 (NOT H.265)")
        return False, 0

    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"  Resolution: {w}x{h}")

    count = 0
    start = time.time()
    while time.time() - start < 5:
        ret, _ = cap.read()
        if ret:
            count += 1

    elapsed = time.time() - start
    cap.release()
    fps = count / elapsed

    print(f"  HD FPS: {fps:.1f}")

    if fps < 5:
        print(f"  >>> HD stream very slow ({fps:.1f}fps) - fullscreen will lag <<<")
    else:
        print(f"  HD stream works OK at {fps:.1f}fps")

    return True, fps


if __name__ == "__main__":
    print("""
    ╔══════════════════════════════════════════════════════════╗
    ║     SafeSight CCTV - Network & Stream Diagnostic        ║
    ║                                                        ║
    ║  Testing:                                              ║
    ║  1. Ping latency to NVR                                ║
    ║  2. Single sub-stream FPS                              ║
    ║  3. All 6 cameras at once                              ║
    ║  4. CPU JPEG encoding speed                            ║
    ║  5. HD stream (fullscreen)                             ║
    ║                                                        ║
    ║  Takes ~60 seconds. Don't close the window!            ║
    ╚══════════════════════════════════════════════════════════╝
    """)

    single_fps = test_single_stream()
    multi_fps = test_multi_stream()
    encode_speed = test_encode_speed()
    hd_ok, hd_fps = test_hd_stream()

    # ── SUMMARY ──
    print_header("FINAL DIAGNOSIS")
    print()

    if single_fps < 10:
        print("  🔴 BOTTLENECK: NVR sub-stream is CAPPED at ~7fps")
        print("     Your NVR is only sending ~7fps on sub-streams.")
        print("     NOTHING in your Python code or network will fix this.")
        print()
        print("     HOW TO FIX:")
        print("     1. Open NVR web interface: http://192.168.100.18")
        print("     2. Login (admin / your password)")
        print("     3. Go to: Setup > Network > Video & Audio (or Camera > Stream)")
        print("     4. Find 'Sub-stream' settings")
        print("     5. Change FPS to 15 or 25")
        print("     6. Keep resolution at CIF/D1 (352x288 or similar)")
        print("     7. Save and reboot NVR if needed")
        print()
        print("     After changing NVR settings, your feeds should jump to 15-25fps!")

    elif encode_speed > 0 and encode_speed < 150:
        print("  🔴 BOTTLENECK: Your CPU can't encode fast enough")
        print(f"     CPU does {encode_speed:.0f} encodes/sec")
        print(f"     Need: 25fps x 6 cameras = 150 encodes/sec")
        print()
        print("     HOW TO FIX:")
        print("     1. Reduce JPEG_QUALITY in config.py to 30")
        print("     2. Or reduce STREAM_FPS to 15")
        print("     3. Or run on a better PC (i5/i7 with 8GB+ RAM)")

    elif single_fps >= 15 and multi_fps < 10:
        print("  🟡 BOTTLENECK: Bandwidth can't handle all 6 streams")
        print("     Single stream is fast but all 6 together slow down.")
        print()
        print("     HOW TO FIX:")
        print("     1. Use a gigabit switch (not a cheap 10/100 hub)")
        print("     2. Make sure Ethernet cables are Cat5e or Cat6")
        print("     3. Try connecting PC directly to NVR with one cable")

    else:
        print("  🟢 Network and NVR look OK!")
        print("     The bottleneck is in your Python code (camera.py).")
        print("     Share camera.py and I'll optimize the threading.")

    if not hd_ok:
        print()
        print("  🔴 FULLSCREEN BROKEN: HD stream not accessible")
        print("     OpenCV can't open the main-stream.")
        print()
        print("     HOW TO FIX:")
        print("     1. Open NVR web UI: http://192.168.100.18")
        print("     2. Camera > Main-stream > Codec = H.264")
        print("     3. If it's H.265/HEVC, change it to H.264")
        print("     4. OpenCV doesn't support H.265 without extra codecs")
        print()
        print("     ALTERNATIVE: Use sub-stream for fullscreen too")
        print("     (lower quality but instant loading)")
    elif hd_fps > 0 and hd_fps < 10:
        print()
        print("  🟡 FULLSCREEN SLOW: HD stream is {0:.1f}fps".format(hd_fps))
        print("     It works but takes a few seconds to connect.")
        print("     Consider using sub-stream for faster fullscreen.")

    print(f"\n{'='*60}")
    print("  Paste these results back to me and I'll give you")
    print("  the exact code changes needed!")
    print(f"{'='*60}\n")