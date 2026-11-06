"""Cleans the raw speech clips: mono, 22.05 kHz or less, silence trimmed, equal loudness.

    python tools/finish_audio.py

Equal loudness matters: a louder name would be easier to catch whatever the condition.
Prints the duration of every clip group, because clip length drives the time measures.
"""
import array
import glob
import math
import os
import statistics
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "audio_raw")
OUT = os.path.join(os.path.dirname(HERE), "audio")
TARGET_RMS = 0.10
MAX_RATE = 22050
PAD_S = 0.01


def read(path):
    with wave.open(path) as w:
        ch, width, rate, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        raw = w.readframes(n)
    if width != 2:
        raise ValueError(f"{path}: expected 16-bit audio, got {width * 8}-bit")
    samples = array.array("h")
    samples.frombytes(raw)
    data = [v / 32768 for v in samples]
    if ch > 1:
        data = [sum(data[i:i + ch]) / ch for i in range(0, len(data), ch)]
    return data, rate


def downsample(data, rate):
    """Averages neighbouring samples to halve the rate until it is at or under MAX_RATE."""
    while rate > MAX_RATE and rate % 2 == 0:
        data = [(data[i] + data[i + 1]) / 2 for i in range(0, len(data) - 1, 2)]
        rate //= 2
    return data, rate


def trim(data, rate):
    frame = max(1, int(rate * 0.01))
    energy = [math.sqrt(sum(v * v for v in data[i:i + frame]) / frame) for i in range(0, len(data) - frame, frame)]
    floor = max(energy) * 0.02
    active = [i for i, e in enumerate(energy) if e > floor]
    pad = int(rate * PAD_S)
    return data[max(0, active[0] * frame - pad):min(len(data), (active[-1] + 1) * frame + pad)]


def write(path, data, rate):
    fade = int(rate * 0.005)
    n = len(data)
    rms = math.sqrt(sum(v * v for v in data) / n)
    gain = TARGET_RMS / rms
    peak = max(abs(v) for v in data) * gain
    if peak > 0.99:
        gain *= 0.99 / peak  # never clip; report below if this happens often
    out = array.array("h", (int(max(-1, min(1, v * gain * min(1, i / fade, (n - 1 - i) / fade))) * 32767)
                            for i, v in enumerate(data)))
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(out.tobytes())
    return n / rate, peak > 0.99


def main():
    os.makedirs(OUT, exist_ok=True)
    durations = {"a": [], "n": [], "t": []}
    limited = 0
    files = sorted(glob.glob(os.path.join(RAW, "*.wav")))
    for path in files:
        name = os.path.basename(path)
        data, rate = read(path)
        data, rate = downsample(data, rate)
        seconds, was_limited = write(os.path.join(OUT, name), trim(data, rate), rate)
        durations[name[0]].append(seconds)
        limited += was_limited
    print(f"{len(files)} clips at {rate} Hz -> {OUT}; {limited} peak-limited below target loudness")
    for key, label in (("a", "fixed phrases"), ("n", "option names"), ("t", "task requests")):
        d = durations[key]
        print(f"  {label}: n={len(d)} mean {statistics.mean(d):.2f}s min {min(d):.2f}s max {max(d):.2f}s")


if __name__ == "__main__":
    main()
