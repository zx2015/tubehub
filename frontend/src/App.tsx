import { BrowserRouter, Route, Routes } from 'react-router-dom';
import VideoJSPlayer from './components/VideoJSPlayer';

/**
 * App 入口（最小可运行骨架）
 *
 * 后续 Task 8+ 会引入：VideoLibrary / DownloadTasks / Settings 等真实路由。
 * 当前 Task 仅交付：
 *   - React + Vite 编译链路
 *   - VideoJSPlayer 核心包装层（已可在 /watch/:id 渲染）
 */
export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route
          path="/watch/:id"
          element={
            <VideoJSPlayer
              src="/api/videos/1/stream"
              startPosition={0}
              onProgress={(pos) => {
                // 在真实页面里会 PATCH /api/videos/{id}/progress
                // 这里仅做最小示例日志，避免 TypeScript 报未使用变量
                console.debug('[VideoJSPlayer] progress:', pos);
              }}
            />
          }
        />
        <Route
          path="/"
          element={
            <main style={{ padding: 24 }}>
              <h1>TubeHub</h1>
              <p>前端骨架已就绪。请前往 <code>/watch/:id</code> 测试播放器。</p>
            </main>
          }
        />
      </Routes>
    </BrowserRouter>
  );
}