import { Suspense } from "react";

import { ChunksClient } from "./ChunksClient";

/**
 * 页面本身不碰路由参数，把 `useParams()` 留到客户端组件里、并套在 Suspense 内。
 *
 * 背景（Next 16 + cacheComponents）：
 * 1. 客户端组件里用 `useParams()` 必须在 `<Suspense>` 内，否则预渲染报错；
 * 2. 服务端 `await params` 会让整个路由变成"blocking route"，同样过不了预渲染。
 * 所以这里只渲染一个 Suspense 外壳，真正的参数读取发生在客户端。
 */
export default function Page() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center">
          <div className="h-5 w-5 animate-spin rounded-full border-2 border-gray-300 border-t-gray-800" />
        </div>
      }
    >
      <ChunksClient />
    </Suspense>
  );
}