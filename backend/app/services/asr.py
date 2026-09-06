import base64
import mimetypes
from pathlib import Path

import requests

from ..provider_config import provider_config


class ASRClient:
    def __init__(self):
        self.config = provider_config()

    def transcribe(self, audio_path: Path) -> dict:
        if self.config["asr_provider"] == "mimo":
            return self._mimo(audio_path)
        return self._openai_transcription(audio_path)

    def _mimo(self, audio_path: Path) -> dict:
        if not self.config["mimo_api_key"]:
            raise RuntimeError("服务器尚未配置 MIMO_API_KEY")
        raw = audio_path.read_bytes()
        encoded = base64.b64encode(raw).decode("ascii")
        if len(encoded) > 10 * 1024 * 1024:
            raise RuntimeError("音频分段超过 MiMo 10MB 限制")
        mime = mimetypes.guess_type(audio_path.name)[0] or "audio/mpeg"
        payload = {
            "model": self.config["mimo_model"],
            "messages": [{
                "role": "user",
                "content": [{"type": "input_audio", "input_audio": {"data": f"data:{mime};base64,{encoded}"}}],
            }],
            "asr_options": {"language": self.config["asr_language"]},
        }
        response = requests.post(
            f"{self.config['mimo_base_url'].rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {self.config['mimo_api_key']}"},
            json=payload, timeout=300,
        )
        if response.status_code != 200:
            raise RuntimeError(f"MiMo ASR 请求失败 ({response.status_code}): {response.text[:400]}")
        content = response.json()["choices"][0]["message"]["content"]
        if isinstance(content, list):
            content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
        return {"text": str(content).strip(), "segments": []}

    def _openai_transcription(self, audio_path: Path) -> dict:
        if not self.config["custom_asr_base_url"] or not self.config["custom_asr_api_key"]:
            raise RuntimeError("自定义 ASR 尚未配置 Base URL 或 API Key")
        with audio_path.open("rb") as handle:
            response = requests.post(
                f"{self.config['custom_asr_base_url'].rstrip('/')}/audio/transcriptions",
                headers={"Authorization": f"Bearer {self.config['custom_asr_api_key']}"},
                files={"file": (audio_path.name, handle, "audio/mpeg")},
                data={
                    "model": self.config["custom_asr_model"],
                    "response_format": "verbose_json",
                    "timestamp_granularities[]": "segment",
                },
                timeout=300,
            )
        if response.status_code != 200:
            raise RuntimeError(f"自定义 ASR 请求失败 ({response.status_code}): {response.text[:400]}")
        payload = response.json()
        segments = []
        for item in payload.get("segments") or []:
            try:
                start = float(item["start"])
                end = float(item["end"])
                text = str(item.get("text", "")).strip()
            except (KeyError, TypeError, ValueError):
                continue
            if text and end > start:
                segments.append({"start_seconds": start, "end_seconds": end, "text": text})
        return {"text": str(payload.get("text", "")).strip(), "segments": segments}
