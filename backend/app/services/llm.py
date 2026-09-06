import json
import re

import requests

from ..provider_config import provider_config


def _call(messages: list[dict]) -> str:
    cfg = provider_config()
    if not cfg["sub2api_base_url"] or not cfg["sub2api_api_key"]:
        raise RuntimeError("服务器尚未配置 Sub2API")
    errors = []
    providers = (
        (cfg["llm_primary_model"], cfg["sub2api_api_key"]),
        (cfg["llm_fallback_model"], cfg["sub2api_fallback_api_key"] or cfg["sub2api_api_key"]),
    )
    for model, api_key in providers:
        response = requests.post(
            f"{cfg['sub2api_base_url'].rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model, "messages": messages, "temperature": 0.35},
            timeout=240,
        )
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"]
        errors.append(f"{model}: {response.status_code} {response.text[:300]}")
    joined = "；".join(errors)
    if "INSUFFICIENT_BALANCE" in joined:
        raise RuntimeError("Sub2API API Key 余额不足。后台账号测试成功不等于 API Key 有额度，请为该 Key 所属用户充值内部余额或分配有效订阅。")
    raise RuntimeError(f"首选与备用模型均调用失败：{joined}")


def _json(text: str):
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.I | re.S)
    return json.loads(cleaned)


def find_highlights(title: str, segments: list[dict]) -> list[dict]:
    transcript = "\n".join(f"[{s['start']}] {s['text']}" for s in segments)
    messages = [
        {"role": "system", "content": "你是短视频内容编辑。只能使用给定时间码，不得编造原话。只输出合法 JSON。"},
        {"role": "user", "content": f"""请从《{title}》听写稿中找出 5-12 个最值得保留的亮点。每项包含 start、end、original_text、reason、title、category、score（1-10）。start/end 必须取自听写稿相邻时间段。输出 JSON 数组。\n\n{transcript}"""},
    ]
    data = _json(_call(messages))
    return data if isinstance(data, list) else data.get("highlights", [])


def rewrite_script(title: str, transcript: str, direction: str) -> str:
    messages = [
        {"role": "system", "content": "你是中文短视频脚本编辑。复刻的是结构、节奏和表达策略，不照抄具体措辞或虚构事实。"},
        {"role": "user", "content": f"""原稿标题：{title}\n改编方向：{direction or '保留核心主题，改成更自然有吸引力的中文口播'}\n\n原稿：\n{transcript}\n\n请输出可直接使用的新口播稿，并在末尾附上三条结构说明。"""},
    ]
    return _call(messages).strip()
