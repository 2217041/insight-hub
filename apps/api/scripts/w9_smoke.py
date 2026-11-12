"""W9 冒烟：验证 provider 接入、多轮历史、用量记录。

前置：
1. 假模型在 9999（或真实 API）
2. API 以 LLM_PROVIDER=openai / LLM_BASE_URL=<...> 启动

用法：
    $env:BASE="http://127.0.0.1:8000"
    python scripts/w9_smoke.py
"""

from __future__ import annotations

import json
import os
import sys
import uuid

import httpx

BASE = os.environ.get("BASE", "http://127.0.0.1:8000")


def stream_once(client: httpx.Client, token: str, conv_id: str, text: str) -> dict:
    """发一条消息，返回 {"content": ..., "done": {...}}。"""
    content = ""
    done: dict = {}
    with client.stream(
        "POST",
        "/api/chat/stream",
        json={"message": text, "conversation_id": conv_id},
        headers={"Authorization": f"Bearer {token}"},
    ) as s:
        for line in s.iter_lines():
            if not line.startswith("data:"):
                continue
            ev = json.loads(line[5:])
            if ev["type"] == "delta":
                content += ev["text"]
            elif ev["type"] == "done":
                done = ev
                break
            elif ev["type"] == "error":
                raise RuntimeError(ev["message"])
    return {"content": content, "done": done}


def main() -> int:
    c = httpx.Client(base_url=BASE, timeout=60)
    email = f"w9-{uuid.uuid4().hex[:8]}@example.com"
    c.post("/api/auth/register", json={"email": email, "password": "Passw0rd!23"})
    token = c.post("/api/auth/login", json={"email": email, "password": "Passw0rd!23"}).json()[
        "access_token"
    ]
    h = {"Authorization": f"Bearer {token}"}
    print(f"[1] 用户 {email}")

    conv = c.post("/api/conversations", json={"title": "W9"}, headers=h).json()
    conv_id = conv["id"]
    print(f"[2] 会话 {conv_id[:8]}")

    r1 = stream_once(c, token, conv_id, "第一句话")
    provider = r1["done"].get("provider")
    usage1 = r1["done"].get("usage", {})
    print(f"[3] 第一轮 provider={provider} 用量={usage1}")
    print(f"    回复片段: {r1['content'][:60]!r}")

    r2 = stream_once(c, token, conv_id, "我刚才说的第一句话是什么？请原样复述")
    usage2 = r2["done"].get("usage", {})
    print(f"[4] 第二轮 用量={usage2}")
    # 用"回忆上一句"验证多轮：任何模型都能答，不依赖假模型的特殊标记
    round_seen = "第一句话" in r2["content"]
    print(f"    历史是否带上: {'✅ 是' if round_seen else '❌ 否'}（能复述上一句）")

    detail = c.get(f"/api/conversations/{conv_id}", headers=h).json()
    msgs = detail["messages"]
    last = msgs[-1]
    print(f"[5] 落库 {len(msgs)} 条；最后一条 tokens: prompt={last.get('prompt_tokens')} "
          f"completion={last.get('completion_tokens')}")

    ok = (
        round_seen
        and len(msgs) == 4
        and provider not in (None, "mock")
        and usage1.get("prompt", 0) > 0
    )
    print("\n✅ W9 冒烟通过" if ok else "\n❌ 有问题")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())