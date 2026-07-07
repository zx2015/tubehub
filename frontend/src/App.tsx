/**
 * App 入口
 *
 * 设计依据：docs/design/04-frontend-components.md §4.1/4.2
 *
 * 路由表：
 *  - /              → VideoLibrary
 *  - /downloads     → DownloadTasks
 *  - /watch/:id     → VideoPlayer
 *  - /settings      → Settings
 *  - *              → 404 fallback
 */
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import Layout from './components/Layout';
import VideoLibrary from './components/VideoLibrary';
import DownloadTasks from './components/DownloadTasks';
import VideoPlayer from './components/VideoPlayer';
import Settings from './components/Settings';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<VideoLibrary />} />
          <Route path="/downloads" element={<DownloadTasks />} />
          <Route path="/watch/:id" element={<VideoPlayer />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}