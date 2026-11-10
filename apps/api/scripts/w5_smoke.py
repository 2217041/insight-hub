"""W5 冒烟测试：上传 → 异步解析 → 状态流转 → 幂等 → 缓存 → SSE。

用法（API 和 worker 都要在跑）：
    cd apps/api
    .\\.venv\\Scripts\\python.exe scripts\\w5_smoke.py
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid

import httpx

BASE = os.environ.get("BASE", "http://127.0.0.1:8000")
SAMPLE = """# 差旅报销制度

## 一、适用范围

本制度适用于公司全体员工的国内差旅与因公外出。

## 二、报销标准

1. 一线城市住宿每晚不超过 600 元；
2. 二线城市住宿每晚不超过 400 元；
3. 交通费凭票报销，高铁二等座、飞机经济舱。

## 三、审批流程

员工提交 → 直属主管审批 → 财务复核 → 打款。超过 5000 元需部门负责人加签。

## 四、常见问题

**问：发票丢了怎么办？** 用复印件加情况说明，由主管签字后提交财务。

**问：可以住民宿吗？** 可以，但需提供正规发票，且金额不超过住宿标准。
"""


def main() -> int:
    client = httpx.Client(base_url=BASE, timeout=30)
    email = f"w5-{uuid.uuid4().hex[:8]}@example.com"

    # 1. 注册 + 登录
    r = client.post("/api/auth/register", json={"email": email, "password": "Passw0rd!23", "name": "W5"})
    print(f"[1] 注册 {r.status_code}")
    r = client.post("/api/auth/login", json={"email": email, "password": "Passw0rd!23"})
    token = r.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    print(f"[2] 登录 {r.status_code}")

    # 2. 上传
    files = {"file": ("差旅报销制度.md", SAMPLE.encode("utf-8"), "text/markdown")}
    r = client.post("/api/documents", files=files)
    if r.status_code != 201:
        print("上传失败:", r.status_code, r.text)
        return 1
    payload = r.json()
    doc_id = payload["document"]["id"]
    print(f"[3] 上传 {r.status_code} id={doc_id[:8]} queued={payload['queued']}")

    # 3. 轮询状态
    deadline = time.time() + 40
    last = None
    while time.time() < deadline:
        d = client.get(f"/api/documents/{doc_id}").json()
        state = (d["status"], d["progress"], d["chunk_count"])
        if state != last:
            print(f"    状态 {d['status']:<9} progress={d['progress']:>3}% chunks={d['chunk_count']}")
            last = state
        if d["status"] in ("ready", "failed"):
            break
        time.sleep(0.6)

    final = client.get(f"/api/documents/{doc_id}").json()
    if final["status"] != "ready":
        print("❌ 未到 ready:", final.get("error_reason"))
        return 1
    print(f"[4] 解析完成，块数 = {final['chunk_count']}")

    # 4. 幂等：同内容再传一次
    files = {"file": ("另一个名字.md", SAMPLE.encode("utf-8"), "text/markdown")}
    r2 = client.post("/api/documents", files=files)
    dedup = r2.json()
    print(f"[5] 重复上传 -> deduplicated={dedup['deduplicated']} id={dedup['document']['id'][:8]}")

    # 5. 缓存
    a = client.get("/api/documents").json()
    b = client.get("/api/documents").json()
    print(f"[6] 列表 total={a['total']} 第一次cached={a['cached']} 第二次cached={b['cached']}")

    # 6. SSE 进度（拿第一帧就够）
    with client.stream("GET", f"/api/documents/{doc_id}/progress") as s:
        for line in s.iter_lines():
            if line.startswith("data:"):
                print(f"[7] SSE 首帧 {line[:110]}")
                break

    # 7. 越权：换一个账号查这个文档
    other = f"w5b-{uuid.uuid4().hex[:8]}@example.com"
    client.post("/api/auth/register", json={"email": other, "password": "Passw0rd!23"})
    tok2 = client.post("/api/auth/login", json={"email": other, "password": "Passw0rd!23"}).json()["access_token"]
    r = client.get(f"/api/documents/{doc_id}", headers={"Authorization": f"Bearer {tok2}"})
    print(f"[8] 跨租户访问 -> HTTP {r.status_code}（期望 404）")

    print("\n✅ W5 冒烟通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())