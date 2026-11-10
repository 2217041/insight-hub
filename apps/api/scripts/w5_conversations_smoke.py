"""W5 收尾验收：会话落库（列表/创建/详情/删/权限隔离）。

用法（API 在跑）：
    cd apps/api
    .\\.venv\\Scripts\\python.exe scripts\\w5_conversations_smoke.py
"""

from __future__ import annotations

import json
import sys
import uuid

import httpx

BASE = "http://127.0.0.1:8000"


def new_user(client: httpx.Client) -> tuple[str, str]:
    email = f"conv-{uuid.uuid4().hex[:8]}@example.com"
    client.post("/api/auth/register", json={"email": email, "password": "Passw0rd!23"})
    tok = client.post("/api/auth/login", json={"email": email, "password": "Passw0rd!23"}).json()[
        "access_token"
    ]
    return email, tok


def main() -> int:
    c = httpx.Client(base_url=BASE, timeout=60)
    email, token = new_user(c)
    h = {"Authorization": f"Bearer {token}"}
    print(f"[1] 用户 {email}")

    # 2. 建会话
    r = c.post("/api/conversations", json={"title": "新对话"}, headers=h)
    conv = r.json()
    conv_id = conv["id"]
    print(f"[2] 创建会话 {r.status_code} id={conv_id[:8]}")

    # 3. 发消息（SSE），同时验证落库
    body = {"message": "你好，帮我记一下这是第一条消息", "conversation_id": conv_id}
    chunks = 0
    with c.stream("POST", "/api/chat/stream", json=body, headers=h) as s:
        for line in s.iter_lines():
            if line.startswith("data:"):
                ev = json.loads(line[5:])
                if ev["type"] == "delta":
                    chunks += 1
                if ev["type"] == "done":
                    break
    print(f"[3] 流式完成，收到 {chunks} 个 delta")

    # 4. 详情：应包含 user + assistant 两条
    detail = c.get(f"/api/conversations/{conv_id}", headers=h).json()
    msgs = detail["messages"]
    roles = [m["role"] for m in msgs]
    print(f"[4] 消息落库：{len(msgs)} 条，角色={roles}")
    for m in msgs:
        print(f"    {m['role']:<9} {m['content'][:40]!r}")

    # 5. 列表
    lst = c.get("/api/conversations", headers=h).json()
    print(f"[5] 会话列表 total={lst['total']} 标题={lst['items'][0]['title']!r}")

    # 6. 再发一轮，验证上下文累加
    body2 = {"message": "这是第二条", "conversation_id": conv_id}
    with c.stream("POST", "/api/chat/stream", json=body2, headers=h) as s:
        for line in s.iter_lines():
            if line.startswith("data:"):
                ev = json.loads(line[5:])
                if ev["type"] == "done":
                    break
    detail2 = c.get(f"/api/conversations/{conv_id}", headers=h).json()
    print(f"[6] 第二轮后消息数 = {len(detail2['messages'])}（期望 4）")

    # 7. 另一个用户不能访问
    _, token2 = new_user(c)
    r = c.get(f"/api/conversations/{conv_id}", headers={"Authorization": f"Bearer {token2}"})
    print(f"[7] 越权访问 -> HTTP {r.status_code}（期望 404）")

    # 8. 删除
    r = c.delete(f"/api/conversations/{conv_id}", headers=h)
    print(f"[8] 删除 -> HTTP {r.status_code}（期望 204）")
    r = c.get(f"/api/conversations/{conv_id}", headers=h)
    print(f"    删除后查询 -> HTTP {r.status_code}（期望 404）")

    ok = roles == ["user", "assistant"] and len(detail2["messages"]) == 4
    print("\n✅ 会话落库验收通过" if ok else "\n❌ 验收失败")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())