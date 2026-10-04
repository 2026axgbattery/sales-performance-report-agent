"""녹화본(webm)과 장면별 나레이션(wav)을 하나의 MP4로 합친다 (Phase 27).

timeline.json의 장면 시작 시각에 맞춰 나레이션을 배치하고, 녹화 앞부분의 빈 화면은 잘라낸다.
사용법: python build_video.py --work <record.mjs의 --out 폴더> --audio <wav 폴더> --out <결과.mp4>
"""
from __future__ import annotations

import argparse
import json
import subprocess
import wave
from pathlib import Path

import imageio_ffmpeg

LEAD_IN_S = 0.2  # 첫 장면 시작 직전 여유


def read_wav(path: Path) -> tuple[bytes, int]:
    with wave.open(str(path), "rb") as w:
        assert w.getnchannels() == 1 and w.getsampwidth() == 2, "mono 16-bit wav만 지원"
        return w.readframes(w.getnframes()), w.getframerate()


def build_audio(timeline: dict, audio_dir: Path, trim_s: float, out_wav: Path) -> float:
    rate = 22050
    total_s = timeline["endMs"] / 1000 - trim_s
    buf = bytearray(int(total_s * rate) * 2)
    for scene in timeline["scenes"]:
        frames, r = read_wav(audio_dir / f"{scene['id']}.wav")
        assert r == rate, f"샘플레이트 불일치: {r}"
        offset = max(0, int((scene["startMs"] / 1000 - trim_s) * rate)) * 2
        end = min(len(buf), offset + len(frames))
        buf[offset:end] = frames[: end - offset]
    with wave.open(str(out_wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(buf))
    return total_s


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True, type=Path)
    ap.add_argument("--audio", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()

    timeline = json.loads((args.work / "timeline.json").read_text(encoding="utf-8"))
    trim_s = max(0.0, timeline["scenes"][0]["startMs"] / 1000 - LEAD_IN_S)
    narration_wav = args.work / "narration.wav"
    total_s = build_audio(timeline, args.audio, trim_s, narration_wav)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        imageio_ffmpeg.get_ffmpeg_exe(), "-y",
        "-ss", f"{trim_s:.3f}", "-i", timeline["video"],
        "-i", str(narration_wav),
        "-t", f"{total_s:.3f}",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-r", "30",
        "-c:a", "aac", "-b:a", "160k",
        "-movflags", "+faststart",
        str(args.out),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    print(f"완성: {args.out} ({total_s:.1f}초)")


if __name__ == "__main__":
    main()
