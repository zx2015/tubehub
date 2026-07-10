/**
 * Layout — 全站布局（顶部 Header + 左侧 Sidebar 常驻 + 右侧路由出口）
 *
 * 仿 YouTube 设计语言，支持侧边栏折叠/展开（汉堡按钮）。
 */
import { useState } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';

const SIDEBAR_COLLAPSED_KEY = 'tubehub_sidebar_collapsed';

export function Layout() {
  const navigate = useNavigate();
  const [collapsed, setCollapsed] = useState<boolean>(() => {
    return localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === 'true';
  });

  const toggleSidebar = () => {
    setCollapsed((prev) => {
      const next = !prev;
      localStorage.setItem(SIDEBAR_COLLAPSED_KEY, String(next));
      return next;
    });
  };

  return (
    <div className="app-container">
      {/* 固定顶部 Header */}
      <header className="navbar">
        <div className="navbar__left">
          <button
            type="button"
            className="sidebar__toggle-btn"
            onClick={toggleSidebar}
            aria-label={collapsed ? '展开侧边栏' : '折叠侧边栏'}
            title={collapsed ? '展开侧边栏' : '折叠侧边栏'}
          >
            <span />
            <span />
            <span />
          </button>
          <div className="navbar__brand" onClick={() => navigate('/')} style={{ cursor: 'pointer' }}>
            <span className="navbar__logo">📺</span>
            <span className="navbar__title">TubeHub</span>
          </div>
        </div>
        <div className="navbar__search-placeholder" />
        <div className="navbar__actions" />
      </header>

      {/* 下方双栏：左 Sidebar，右 Main Content */}
      <div className="app-body">
        <aside className={`sidebar${collapsed ? ' sidebar--collapsed' : ''}`}>
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
    </div>
  );
}

export default Layout;
