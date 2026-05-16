import sys
from pathlib import Path

from moviepy import (
    AudioFileClip,
    CompositeVideoClip,
    ImageClip,
    concatenate_videoclips,
    vfx,
)


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def load_images(images_dir: str) -> list[Path]:
    images = sorted([
        f for f in Path(images_dir).iterdir()
        if f.suffix.lower() in IMAGE_EXTENSIONS
    ])
    if not images:
        print(f"エラー: '{images_dir}' に画像が見つかりませんでした")
        sys.exit(1)
    return images


def make_video(
    images_dir: str,
    audio_path: str,
    output_path: str = "output.mp4",
    fade_duration: float = 0.5,
):
    images = load_images(images_dir)
    audio = AudioFileClip(str(audio_path))
    total_duration = audio.duration
    duration_per_image = total_duration / len(images)

    print(f"画像枚数       : {len(images)} 枚")
    print(f"音声の長さ     : {total_duration:.1f} 秒")
    print(f"1枚あたりの時間: {duration_per_image:.1f} 秒")
    print()

    clips = []
    for img_path in images:
        clip = (
            ImageClip(str(img_path), duration=duration_per_image)
            .with_effects([
                vfx.FadeIn(fade_duration),
                vfx.FadeOut(fade_duration),
            ])
        )
        clips.append(clip)

    video = concatenate_videoclips(clips, method="compose")
    video = video.with_audio(audio)

    print(f"動画を書き出し中... → {output_path}")
    video.write_videofile(
        output_path,
        fps=24,
        codec="libx264",
        audio_codec="aac",
        threads=4,
        logger="bar",
    )

    audio.close()
    video.close()
    print(f"\n完成！ → {output_path}")


def print_usage():
    print("使い方:")
    print("  python make_video.py <画像フォルダ> <音声ファイル> [出力ファイル名]")
    print()
    print("例:")
    print("  python make_video.py ./images voice.mp3")
    print("  python make_video.py ./images voice.mp3 my_video.mp4")
    print()
    print("対応している画像形式: JPG, PNG, WebP, BMP")
    print("対応している音声形式: MP3, WAV, AAC, M4A")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print_usage()
        sys.exit(1)

    images_dir = sys.argv[1]
    audio_path = sys.argv[2]
    output = sys.argv[3] if len(sys.argv) > 3 else "output.mp4"

    if not Path(images_dir).is_dir():
        print(f"エラー: フォルダ '{images_dir}' が見つかりません")
        sys.exit(1)

    if not Path(audio_path).is_file():
        print(f"エラー: 音声ファイル '{audio_path}' が見つかりません")
        sys.exit(1)

    make_video(images_dir, audio_path, output)
