"""
動画処理コア:
  1. Whisper で音声を文字起こし
  2. moviepy で字幕（黒ボックス+白文字）をフレームに焼き込み
  3. BGM があれば音声ミックス
"""

import subprocess
import json
from pathlib import Path

import whisper
from moviepy import (
    AudioFileClip,
    CompositeAudioClip,
    CompositeVideoClip,
    TextClip,
    VideoFileClip,
    afx,
)

WHISPER_MODEL_SIZE = "small"   # tiny / base / small / medium / large
FONT_PATH = "C:/Windows/Fonts/YuGothB.ttc"
FONT_SIZE = 32
BGM_VOLUME = 0.15

_whisper_model = None


def get_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        _whisper_model = whisper.load_model(WHISPER_MODEL_SIZE)
    return _whisper_model


def transcribe(video_path: str) -> list[dict]:
    model = get_whisper_model()
    result = model.transcribe(video_path, language="ja", verbose=False)
    return result["segments"]


def split_long_segment(seg: dict, max_chars: int = 20) -> list[dict]:
    """長すぎるセグメントを2分割する"""
    text = seg["text"].strip()
    if len(text) <= max_chars:
        return [seg]
    mid = len(text) // 2
    mid_time = (seg["start"] + seg["end"]) / 2
    return [
        {"start": seg["start"], "end": mid_time, "text": text[:mid]},
        {"start": mid_time, "end": seg["end"], "text": text[mid:]},
    ]


def has_audio(video_path: str) -> bool:
    """動画に音声トラックがあるか確認する"""
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_streams", "-select_streams", "a", video_path
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        data = json.loads(result.stdout.decode("utf-8", errors="replace"))
        return len(data.get("streams", [])) > 0
    except Exception:
        return False


def process_video(
    input_path: str,
    output_path: str,
    bgm_path: str | None = None,
    on_status=None,
) -> None:
    def status(msg: str):
        if on_status:
            on_status(msg)

    # 音声トラックがある場合のみ文字起こし
    if has_audio(input_path):
        status("音声を文字起こし中... (初回はモデルのダウンロードで数分かかります)")
        raw_segments = transcribe(input_path)
        segments = []
        for seg in raw_segments:
            segments.extend(split_long_segment(seg))
    else:
        status("音声なし動画のため字幕をスキップします")
        segments = []

    status(f"字幕 {len(segments)} 件を動画に合成中...")
    _render(input_path, output_path, segments, bgm_path)
    status("完成！")


def _render(
    input_path: str,
    output_path: str,
    segments: list[dict],
    bgm_path: str | None,
) -> None:
    video = VideoFileClip(str(input_path))
    clips = [video]

    # 動画幅の90%を字幕の最大幅にする
    max_text_width = int(video.w * 0.9)

    for seg in segments:
        text = seg["text"].strip()
        if not text:
            continue
        duration = seg["end"] - seg["start"]
        if duration <= 0:
            continue

        # 白文字 + 黒縁どり（背景なし）
        txt = (
            TextClip(
                font=FONT_PATH,
                text=text,
                font_size=FONT_SIZE,
                color="white",
                stroke_color="black",
                stroke_width=3,
                method="caption",
                size=(max_text_width, None),
            )
            .with_duration(duration)
            .with_start(seg["start"])
            .with_position(("center", 0.82), relative=True)
        )
        clips.append(txt)

    result = CompositeVideoClip(clips)

    # BGM ミックス
    if bgm_path and video.audio is not None:
        bgm = AudioFileClip(str(bgm_path)).with_effects([
            afx.MultiplyVolume(BGM_VOLUME),
        ])
        # 動画より短い BGM はループさせる
        if bgm.duration < result.duration:
            bgm = bgm.with_effects([afx.AudioLoop(duration=result.duration)])
        bgm = bgm.with_duration(result.duration)
        mixed = CompositeAudioClip([video.audio, bgm])
        result = result.with_audio(mixed)

    write_kwargs = dict(
        fps=video.fps or 30,
        codec="libx264",
        threads=4,
        logger="bar",
    )
    if result.audio is not None:
        write_kwargs["audio_codec"] = "aac"
    else:
        write_kwargs["audio"] = False

    result.write_videofile(str(output_path), **write_kwargs)

    video.close()
    result.close()
