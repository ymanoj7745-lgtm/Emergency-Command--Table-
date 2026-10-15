import sounddevice as sd
import numpy as np

CANDIDATES = [
    (1,  44100, "Realtek Mic Array - MME"),
    (2,  44100, "ASUS AI Noise-cancel - MME"),
    (7,  44100, "Realtek Mic - DirectSound"),
    (8,  44100, "ASUS AI Noise-cancel - DirectSound"),
    (14, 44100, "ASUS AI Noise-cancel - WASAPI"),
    (15, 44100, "Realtek Mic - WASAPI 44.1k"),
    (15, 48000, "Realtek Mic - WASAPI 48k"),
    (17, 48000, "Realtek HD Mic Array - WDM-KS"),
    (18, 48000, "Realtek HD Mic - WDM-KS"),
    (19, 44100, "Stereo Mix - WDM-KS"),
    (48, 44100, "ASUS AI Noise-cancel - WDM-KS"),
    (50, 44100, "System Virtual Line - WDM-KS"),
]

print("=" * 60)
print("Speak loudly for 2 seconds after each 'Recording...'")
print("=" * 60)

results = []

for dev, sr, label in CANDIDATES:
    try:
        print(f"[{dev:2d}] {label:38s} @{sr}...", end=" ", flush=True)
        frames = int(sr * 2.0)
        a = sd.rec(frames, samplerate=sr, channels=1, dtype='int32', device=dev)
        sd.wait()
        a = a.flatten().astype(np.float64) / 2147483648.0

        if not np.all(np.isfinite(a)):
            print("BAD DATA")
            continue

        rms = float(np.sqrt(np.mean(a ** 2)))
        results.append((dev, sr, rms, label))
        status = "✓ LOUD" if rms > 0.05 else "~ quiet" if rms > 0.005 else "· silent"
        print(f"RMS={rms:.4f}  {status}")

    except Exception as e:
        print(f"FAILED ({type(e).__name__})")

print("\n" + "=" * 60)
print("BEST CANDIDATES")
print("=" * 60)

results.sort(key=lambda x: -x[2])
for dev, sr, rms, label in results[:5]:
    mark = "★★★" if rms > 0.05 else "★" if rms > 0.005 else "·"
    print(f"  {mark}  device={dev:2d}  samplerate={sr}  RMS={rms:.4f}  ({label})")

if results and results[0][2] > 0.005:
    dev, sr, rms, label = results[0]
    print(f"\n>>> USE: DEVICE = {dev}  DEVICE_RATE = {sr}")
else:
    print("\n!!! NO WORKING DEVICE FOUND")
    print("Try rebooting Windows, then run this again.")