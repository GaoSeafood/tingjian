import base64
import mimetypes
import re
import time
from pathlib import Path

import requests

from ..provider_config import provider_config


class ASRClient:
    def __init__(self):
        self.config = provider_config()

    def transcribe(self, audio_path: Path) -> dict:
        if self.config["asr_provider"] == "mimo":
            return self._mimo(audio_path)
        if self.config["asr_provider"] == "assemblyai":
            return self._assemblyai(audio_path)
        return self._openai_transcription(audio_path)

    def _assemblyai(self, audio_path: Path) -> dict:
        api_key = self.config.get("assemblyai_api_key")
        if not api_key:
            raise RuntimeError("AssemblyAI 尚未配置 API Key")
        base_url = self.config.get("assemblyai_base_url", "https://api.assemblyai.com").rstrip("/")
        headers = {"authorization": api_key}
        try:
            with audio_path.open("rb") as handle:
                upload = requests.post(
                    f"{base_url}/v2/upload",
                    headers={**headers, "content-type": "application/octet-stream"},
                    data=handle,
                    timeout=600,
                )
            if upload.status_code not in (200, 201):
                raise RuntimeError(f"AssemblyAI 上传失败 ({upload.status_code}): {upload.text[:400]}")
            audio_url = upload.json().get("upload_url")
            if not audio_url:
                raise RuntimeError("AssemblyAI 未返回音频地址")

            body = {
                "audio_url": audio_url,
                "speech_models": [self.config.get("assemblyai_model") or "universal-2"],
                "speaker_labels": True,
                "punctuate": True,
                "format_text": True,
            }
            language = self.config.get("asr_language")
            if language and language != "auto":
                body["language_code"] = "zh" if language == "zh" else language
            else:
                # AssemblyAI defaults to English when neither language_code
                # nor language_detection is supplied. Explicitly enable
                # detection so Mandarin recordings are segmented correctly.
                body["language_detection"] = True
            submit = requests.post(
                f"{base_url}/v2/transcript",
                headers={**headers, "content-type": "application/json"},
                json=body,
                timeout=120,
            )
            if submit.status_code not in (200, 201):
                raise RuntimeError(f"AssemblyAI 创建任务失败 ({submit.status_code}): {submit.text[:400]}")
            transcript_id = submit.json().get("id")
            if not transcript_id:
                raise RuntimeError("AssemblyAI 未返回任务 ID")

            deadline = time.monotonic() + 2 * 60 * 60
            while time.monotonic() < deadline:
                result = requests.get(
                    f"{base_url}/v2/transcript/{transcript_id}", headers=headers, timeout=120,
                )
                if result.status_code != 200:
                    raise RuntimeError(f"AssemblyAI 查询失败 ({result.status_code}): {result.text[:400]}")
                payload = result.json()
                status = payload.get("status")
                if status == "completed":
                    return self._assemblyai_result(payload)
                if status == "error":
                    raise RuntimeError(f"AssemblyAI 转写失败：{payload.get('error') or '未知错误'}")
                time.sleep(3)
            raise RuntimeError("AssemblyAI 转写超时（超过 2 小时）")
        except requests.RequestException as exc:
            raise RuntimeError(f"AssemblyAI 网络请求失败：{exc}") from exc

    @staticmethod
    def _assemblyai_result(payload: dict) -> dict:
        segments = []
        for item in payload.get("utterances") or []:
            try:
                start = float(item.get("start", 0)) / 1000
                end = float(item.get("end", 0)) / 1000
                text = ASRClient._normalize_text(item.get("text", ""))
            except (TypeError, ValueError):
                continue
            if not text or end <= start:
                continue
            speaker = str(item.get("speaker") or "").strip()
            segment = {"start_seconds": start, "end_seconds": end, "text": text}
            if speaker:
                segment["speaker"] = f"说话人 {speaker}"
            segments.append(segment)
        text = ASRClient._normalize_text(payload.get("text", ""))
        if segments and any(item.get("speaker") for item in segments):
            # Keep speaker labels in the plain-text transcript as well, so
            # TXT export and downstream LLM features retain the dialogue
            # structure instead of silently flattening it.
            text = "\n".join(
                f"[{item.get('speaker')}] {item['text']}" if item.get("speaker") else item["text"]
                for item in segments
            )
        elif not text and segments:
            text = "\n".join(item["text"] for item in segments)
        return {"text": text, "segments": segments}

    @staticmethod
    def _normalize_text(value: object) -> str:
        """Remove tokenization spaces inserted between adjacent CJK chars."""
        text = str(value or "").strip()
        text = re.sub(r"(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff])", "", text)
        text = re.sub(r"\s+([，。！？、；：,.!?;:])", r"\1", text)
        text = re.sub(r"([（【“‘])\s+", r"\1", text)
        return text.strip()

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
