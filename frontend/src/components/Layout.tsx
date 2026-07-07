/**
 * Layout — 全站布局（顶部导航 + 路由出口）
 *
 * 设计依据：docs/design/04-frontend-components.md §4.2
 *
 * 顶部导航包含：Logo、视频库、下载任务、设置。
 */
import { NavLink, Outlet } from 'react-router-dom';

export function Layout() {
  return (
    <div className="layout">
      <header className="navbar">
        <div className="navbar__brand">
          <span className="navbar__logo">📺</span>
          <span className="navbar__title">TubeHub</span>
        </div>
        <nav className="navbar__nav">
          <NavLink
            to="/"
            end
            className={({ isActive }) =>
              `navbar__link${isActive ? ' navbar__link--active' : ''}`
            }
          >
            视频库
          </NavLink>
          <NavLink
            to="/downloads"
            className={({ isActive }) =>
              `navbar__link${isActive ? ' navbar__link--active' : ''}`
            }
          >
            下载任务
          </NavLink>
          <NavLink
            to="/settings"
            className={({ isActive }) =>
              `navbar__link${isActive ? ' navbar__link--active' : ''}`
            }
          >
            设置
          </NavLink>
        </nav>
      </header>
      <main className="layout__main">
        <Outlet />
      </main>
    </div>
  );
}

export default Layout;