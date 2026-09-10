import json
import re

import requests

from ..provider_config import provider_config


def _call(messages: list[dict]) -> str:
    cfg = provider_config()
    if not cfg["sub2api_base_url"] or not cfg["sub2api_api_key"]:
        raise RuntimeError("服务器尚未配置 Sub2API")
    errors = []
    providers = [(cfg["llm_primary_model"], cfg["sub2api_api_key"])]
    # Sub2API keys are bound to a group. Do not send a GPT model through the
    # Gemini-group key when no dedicated fallback key was configured.
    if cfg["sub2api_fallback_api_key"]:
        providers.append((cfg["llm_fallback_model"], cfg["sub2api_fallback_api_key"]))
    for model, api_key in providers:
        if not model:
            errors.append("未配置模型")
            continue
        try:
            response = requests.post(
                f"{cfg['sub2api_base_url'].rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": model, "messages": messages, "temperature": 0.35},
                timeout=(10, 120),
            )
        except requests.RequestException as exc:
            errors.append(f"{model}: 请求超时或网络错误（{str(exc)[:120]}）")
            continue
        if response.status_code == 200:
            try:
                return response.json()["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError, ValueError) as exc:
                errors.append(f"{model}: 返回格式异常（{exc}）")
                continue
        try:
            detail = response.json().get("error", {}).get("message", "")
        except ValueError:
            detail = response.text
        errors.append(f"{model}: {response.status_code} {detail[:180]}")
    joined = "；".join(errors)
    if "INSUFFICIENT_BALANCE" in joined:
        raise RuntimeError("Sub2API API Key 余额不足。后台账号测试成功不等于 API Key 有额度，请为该 Key 所属用户充值内部余额或分配有效订阅。")
    if "model_not_found" in joined or "模型" in joined and "supported" in joined:
        raise RuntimeError(f"Sub2API 模型不可用，请在对应分组中确认模型名称：{joined}")
    raise RuntimeError(f"首选与备用模型均调用失败：{joined}")


def _json(text: str):
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.I | re.S)
    return json.loads(cleaned)


def find_highlights(title: str, segments: list[dict], visual_analysis: list[dict] | None = None) -> list[dict]:
    transcript = "\n".join(f"[{s['start']}] {s['text']}" for s in segments)
    visual_context = "\n".join(
        f"[{item.get('timestamp', '')}] 画面：{item.get('description', '')}；视觉吸引力：{item.get('visual_hook', '')}"
        for item in (visual_analysis or [])
    )
    visual_instruction = f"\n\n画面分析（可用于判断视觉亮点）：\n{visual_context}" if visual_context else ""
    messages = [
        {"role": "system", "content": "你是短视频内容编辑。只能使用给定时间码，不得编造原话。只输出合法 JSON。"},
        {"role": "user", "content": f"""请从《{title}》听写稿中找出 5-12 个最值得保留的亮点。优先选择台词和画面同时有吸引力的片段，并在 reason 中说明画面贡献。每项包含 start、end、original_text、reason、title、category、score（1-10）。start/end 必须取自听写稿相邻时间段。输出 JSON 数组。\n\n{transcript}{visual_instruction}"""},
    ]
    data = _json(_call(messages))
    return data if isinstance(data, list) else data.get("highlights", [])


def rewrite_script(title: str, transcript: str, direction: str) -> str:
    messages = [
        {"role": "system", "content": "你是中文短视频脚本编辑。复刻的是结构、节奏和表达策略，不照抄具体措辞或虚构事实。"},
        {"role": "user", "content": f"""原稿标题：{title}\n改编方向：{direction or '保留核心主题，改成更自然有吸引力的中文口播'}\n\n原稿：\n{transcript}\n\n请输出可直接使用的新口播稿，并在末尾附上三条结构说明。"""},
    ]
    return _call(messages).strip()
