"""W11 冒烟：上传文档 → 向量化 → 检索 → 带引用回答 → 无答案拒答。"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path

import httpx

BASE = os.environ.get("BASE", "http://127.0.0.1:8000")
KB = Path(r"D:\aistudy\texun-project\repo\examples\knowledge-base")
DOCX = KB / "云雀科技-差旅费用报销手册.docx"


def ask(c: httpx.Client, conv_id: str, q: str) -> dict:
    content, done = "", {}
    with c.stream("POST", "/api/chat/stream", json={"message": q, "conversation_id": conv_id}) as s:
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
    c = httpx.Client(base_url=BASE, timeout=180)
    email = f"w11-{uuid.uuid4().hex[:6]}@example.com"
    c.post("/api/auth/register", json={"email": email, "password": "Passw0rd!23"})
    tok = c.post("/api/auth/login", json={"email": email, "password": "Passw0rd!23"}).json()[
        "access_token"
    ]
    c.headers["Authorization"] = f"Bearer {tok}"
    print(f"用户 {email}")

    data = DOCX.read_bytes()
    r = c.post(
        "/api/documents",
        files={"file": (DOCX.name, data,
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    doc = r.json()["document"]
    print(f"[1] 上传 {r.status_code}")

    t0 = time.time()
    while time.time() - t0 < 300:
        d = c.get(f"/api/documents/{doc['id']}").json()
        if d["status"] in ("ready", "failed"):
            break
        print(f"    {d['status']} {d['progress']}%")
        time.sleep(2)
    print(f"[2] 解析+向量化完成：{d['status']}，子块 {d['chunk_count']}，耗时 {time.time()-t0:.0f}s")

    conv = c.post("/api/conversations", json={"title": "W11"}, headers=c.headers).json()

    print("\n[3] 问：一次预算 10000 元的出差，需要谁审批？")
    a1 = ask(c, conv["id"], "一次预算 10000 元的出差，需要谁审批？")
    print("    答：" + a1["content"].replace("\n", " ")[:200])
    print(f"    召回 {a1['done'].get('retrieved')} 块")
    hit = ("部门负责人" in a1["content"]) and ("8000" in a1["content"])

    print("\n[4] 问：杭州的住宿上限是多少？")
    a2 = ask(c, conv["id"], "杭州的住宿上限是多少？")
    print("    答：" + a2["content"].replace("\n", " ")[:200])
    hit2 = "480" in a2["content"]

    print("\n[5] 问：公司的年假有几天？（文档里没有）")
    a3 = ask(c, conv["id"], "公司的年假有几天？")
    print("    答：" + a3["content"].replace("\n", " ")[:160])
    refused = ("未找到" in a3["content"]) or ("没有" in a3["content"])

    detail = c.get(f"/api/conversations/{conv['id']}").json()
    with_cites = [m for m in detail["messages"] if m.get("citations")]
    if with_cites:
        cites = with_cites[0]["citations"]
        print(f"\n[6] 引用记录 {len(cites)} 条，首条：{cites[0]['doc_name']} 第{cites[0]['page']}页 {cites[0]['section_path']}")
    else:
        print("\n[6] ❌ 没有引用记录")

    ok = hit and hit2 and refused and bool(with_cites)
    print(f"\n{'✅ W11 冒烟通过' if ok else '❌ 有问题'} （多条件={hit} 表格={hit2} 拒答={refused} 引用={bool(with_cites)}）")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())