import base64
import mimetypes
import shutil
import subprocess
from pathlib import Path

from ..config import settings
from .llm import _call, _json


def _clock(seconds: float) -> str:
    total = max(0, int(seconds))
    return f"{total // 3600:02d}:{(total % 3600) // 60:02d}:{total % 60:02d}"


def sample_keyframes(media_path: Path, task_dir: Path, duration: float) -> list[tuple[float, Path]]:
    """Extract a bounded set of JPEG keyframes without decoding the full video into memory."""
    frame_dir = task_dir / "visual"
    shutil.rmtree(frame_dir, ignore_errors=True)
    frame_dir.mkdir(parents=True, exist_ok=True)
    max_frames = max(8, settings.visual_max_frames)
    interval = max(float(settings.visual_min_interval_seconds), duration / max_frames if duration else 0)
    pattern = frame_dir / "frame-%03d.jpg"
    subprocess.run([
        "ffmpeg", "-y", "-i", str(media_path),
        "-vf", f"fps=1/{interval:g},scale=768:768:force_original_aspect_ratio=decrease",
        "-q:v", "5", "-frames:v", str(max_frames), str(pattern),
    ], capture_output=True, timeout=7200, check=True)
    frames = sorted(frame_dir.glob("frame-*.jpg"))
    return [((index - 1) * interval, path) for index, path in enumerate(frames, 1)]


def analyze_visuals(title: str, transcript: str, segments: list[dict], media_path: Path, task_dir: Path) -> list[dict]:
    if not media_path.exists():
        raise RuntimeError("原视频已删除，无法进行画面分析")
    duration = 0.0
    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(media_path)],
            capture_output=True, text=True, timeout=60, check=True,
        )
        duration = float(probe.stdout.strip() or 0)
    except (subprocess.SubprocessError, ValueError):
        pass
    frames = sample_keyframes(media_path, task_dir, duration)
    if not frames:
        raise RuntimeError("没有抽取到可分析的画面帧")

    transcript_lines = "\n".join(
        f"[{item.get('start', _clock(item.get('start_seconds', 0)))}] {str(item.get('text', '')).strip()}"
        for item in segments
        if str(item.get("text", "")).strip()
    )
    transcript_lines = transcript_lines[:16000]
    prompt = f"""你是视频内容分析师。请结合视频关键帧和听写时间轴，识别画面信息、视觉亮点，并总结这条视频的画面风格。
标题：{title}
听写时间轴（可能已截断）：
{transcript_lines or transcript[:16000]}

我会提供带时间点的关键帧。只输出合法 JSON 对象，格式必须是：
{{
  "style_analysis": {{
    "overall_style": "一句话概括整体视觉风格",
    "color_lighting": "色彩、明暗、光线和质感",
    "composition_camera": "构图、景别、机位和主体呈现方式",
    "editing_rhythm": "根据关键帧时间间隔能判断的节奏与镜头变化；看不出来就明确说未知",
    "text_graphics": "字幕、贴纸、UI、字体和包装方式；没有则写无明显包装",
    "replication_tips": "如果要复刻，最值得借鉴的 3-5 条视觉做法"
  }},
  "scenes": [
    {{
      "timestamp": "关键帧时间码",
      "description": "画面发生了什么",
      "onscreen_text": "画面文字，没有则为空字符串",
      "visual_hook": "为什么这个画面有吸引力",
      "suggested_use": "适合开头/转场/高潮/结尾/补充画面中的一种或多种",
      "confidence": 0.0
    }}
  ]
}}
不要编造看不见的内容；timestamp 必须使用我提供的关键帧时间码。style_analysis 只能总结关键帧中确实能观察到的风格，最多输出 12 项最有价值的 scenes。"""
    content: list[dict] = [{"type": "text", "text": prompt}]
    for seconds, frame_path in frames:
        encoded = base64.b64encode(frame_path.read_bytes()).decode("ascii")
        mime = mimetypes.guess_type(frame_path.name)[0] or "image/jpeg"
        content.append({"type": "text", "text": f"关键帧时间：{_clock(seconds)}"})
        content.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}})
    result = _json(_call([{"role": "user", "content": content}]))
    if isinstance(result, dict):
        style = result.get("style_analysis")
        scenes = result.get("scenes") or result.get("visual_analysis") or result.get("items") or []
        if not isinstance(scenes, list):
            scenes = []
        if isinstance(style, dict) and style:
            scenes = [{"kind": "style_analysis", **style}, *scenes]
        result = scenes
    if not isinstance(result, list):
        raise RuntimeError("画面分析返回格式异常")
    # Keep the dedicated style card plus up to twelve timestamped scenes.
    return result[:13]
