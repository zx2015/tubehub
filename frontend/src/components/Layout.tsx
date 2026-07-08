/**
 * Layout — 全站布局（顶部 Header + 左侧 Sidebar 常驻 + 右侧路由出口）
 *
 * 仿 YouTube 设计语言，提供极致沉浸观影体验。
 */
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { AddDownloadPanel } from './AddDownloadDialog';

export function Layout() {
  const navigate = useNavigate();

  return (
    <div className="app-container">
      {/* 固定顶部 Header */}
      <header className="navbar">
        <div className="navbar__brand" onClick={() => navigate('/')} style={{ cursor: 'pointer' }}>
          <span className="navbar__logo">📺</span>
          <span className="navbar__title">TubeHub</span>
        </div>
        <div className="navbar__search-placeholder">
          {/* 为后期全局搜索预留 */}
        </div>
        <div className="navbar__actions">
          {/* 可以加顶部操作，如系统健康等 */}
        </div>
      </header>

      {/* 下方双栏：左 Sidebar，右 Main Content */}
      <div className="app-body">
        <aside className="sidebar">
          <nav className="sidebar__nav">
            <NavLink
              to="/"
              end
              className={({ isActive }) =>
                `sidebar__item${isActive ? ' sidebar__item--active' : ''}`
              }
            >
              <span className="sidebar__icon">🏠</span>
              <span className="sidebar__text">视频库</span>
            </NavLink>
            <NavLink
              to="/downloads"
              className={({ isActive }) =>
                `sidebar__item${isActive ? ' sidebar__item--active' : ''}`
              }
            >
              <span className="sidebar__icon">📥</span>
              <span className="sidebar__text">下载任务</span>
            </NavLink>
            <NavLink
              to="/settings"
              className={({ isActive }) =>
                `sidebar__item${isActive ? ' sidebar__item--active' : ''}`
              }
            >
              <span className="sidebar__icon">⚙️</span>
              <span className="sidebar__text">系统设置</span>
            </NavLink>
          </nav>
          <hr className="sidebar__divider" />
          <div className="sidebar__footer">
            <p>© 2026 TubeHub</p>
            <p>私有视频流媒体平台</p>
          </div>
        </aside>

        <main className="main-content">
          <Outlet />
        </main>
      </div>

      {/* 全站右下角常驻：快速下载悬浮窗 (写邮件风格) */}
      <AddDownloadPanel />
    </div>
  );
}

export default Layout;