import { getAccessToken } from "./auth";
import type { StreamEvent } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000";

export class StreamError extends Error {
  constructor(
    message: string,
    readonly httpStatus?: number,
  ) {
    super(message);
    this.name = "StreamError";
  }
}

/**
 * 读取 SSE 流。
 *
 * 为什么不用 EventSource：
 *   EventSource 只支持 GET，没法带 JSON 消息体，且不能自定义请求头。
 * 所以用 fetch + ReadableStream 手动解析 `data: {...}\n\n` 帧。
 */
export async function* streamChat(
  payload: { message: string; conversation_id?: string },
  signal: AbortSignal,
): AsyncGenerator<StreamEvent> {
  let res: Response;
  try {
    const token = getAccessToken();
    res = await fetch(`${API_BASE}/api/chat/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        // W5 收尾：对话接口需要登录，消息要落库到该用户所属租户
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(payload),
      signal,
    });
  } catch (err) {
    if (signal.aborted) throw err;
    throw new StreamError(
      `连不上后端（${API_BASE}）。确认 API 窗口里 uvicorn 在运行。`,
    );
  }

  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new StreamError(
      `后端返回 ${res.status}${detail ? `：${detail.slice(0, 200)}` : ""}`,
      res.status,
    );
  }
  if (!res.body) {
    throw new StreamError("当前浏览器不支持 ReadableStream。");
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      // SSE 用空行分隔事件帧
      let sep: number;
      while ((sep = buffer.indexOf("\n\n")) !== -1) {
        const frame = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);

        const dataLine = frame
          .split("\n")
          .find((line) => line.startsWith("data:"));
        if (!dataLine) continue;

        const raw = dataLine.slice(5).trim();
        if (!raw) continue;

        try {
          yield JSON.parse(raw) as StreamEvent;
        } catch {
          // 半截 JSON 或心跳注释，跳过即可
        }
      }
    }
  } finally {
    reader.cancel().catch(() => undefined);
  }
}