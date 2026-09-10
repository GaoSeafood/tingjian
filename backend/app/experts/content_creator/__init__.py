"""Server-side runtime adapter for the 文爆爆 content creator expert."""

from functools import lru_cache
from pathlib import Path


ROOT = Path(__file__).parent


@lru_cache(maxsize=1)
def system_prompt() -> str:
    """Load the private expert instructions once per worker process."""
    agent = (ROOT / "agent.md").read_text(encoding="utf-8").strip()
    humanizer = (ROOT / "humanizer.md").read_text(encoding="utf-8").strip()
    return f"{agent}\n\n## 去 AI 味编辑规则\n{humanizer}"


__all__ = ["system_prompt"]
