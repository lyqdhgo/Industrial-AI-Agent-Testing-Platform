import {
  FlaskConical,
  Gauge,
  GitCompareArrows,
  ListChecks,
  Menu,
  ShieldAlert,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { api } from "../api";
import { useAsync } from "../lib/useAsync";

const navigation = [
  {
    section: "测试工作台",
    items: [
      { to: "/", label: "总览", icon: Gauge, end: true },
      { to: "/runs", label: "运行记录", icon: ListChecks, end: false },
      { to: "/cases", label: "测试用例", icon: FlaskConical, end: false },
    ],
  },
  {
    section: "安全与证据",
    items: [
      { to: "/safety", label: "安全与联锁", icon: ShieldAlert, end: false },
      { to: "/regressions", label: "回归对比", icon: GitCompareArrows, end: false },
    ],
  },
];

const titles: { match: RegExp; title: string }[] = [
  { match: /^\/$/, title: "总览" },
  { match: /^\/runs$/, title: "运行记录" },
  { match: /^\/runs\/[^/]+\/cases\//, title: "用例证据" },
  { match: /^\/runs\/[^/]+\/report/, title: "测试报告" },
  { match: /^\/runs\//, title: "运行详情" },
  { match: /^\/cases/, title: "测试用例" },
  { match: /^\/safety/, title: "安全与联锁" },
  { match: /^\/regressions/, title: "回归对比" },
];

export function AppShell() {
  const [menuOpen, setMenuOpen] = useState(false);
  const location = useLocation();
  const health = useAsync(api.health, [], 30000);
  const title = titles.find((item) => item.match.test(location.pathname))?.title ?? "IATP";

  useEffect(() => {
    setMenuOpen(false);
    window.scrollTo({ top: 0, behavior: "auto" });
  }, [location.pathname]);

  const online = health.data?.status === "ok" && health.error === null;

  return (
    <div className={`app-shell${menuOpen ? " app-shell--menu-open" : ""}`}>
      <button
        type="button"
        className="mobile-scrim"
        aria-label="关闭导航"
        onClick={() => setMenuOpen(false)}
      />
      <aside className="sidebar">
        <div className="sidebar__brand">
          <NavLink to="/" className="brand">
            <span className="brand__mark" aria-hidden="true">
              <span />
              <span />
              <span />
            </span>
            <span>
              <strong>IATP</strong>
              <small>工业 Agent 测试平台</small>
            </span>
          </NavLink>
          <button
            type="button"
            className="icon-button sidebar__close"
            onClick={() => setMenuOpen(false)}
            aria-label="关闭导航"
          >
            <X size={18} />
          </button>
        </div>

        <nav className="sidebar__nav" aria-label="主导航">
          {navigation.map((group) => (
            <div className="nav-group" key={group.section}>
              <div className="nav-group__label">{group.section}</div>
              {group.items.map((item) => {
                const Icon = item.icon;
                return (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    end={item.end}
                    className={({ isActive }) =>
                      `nav-link${isActive ? " nav-link--active" : ""}`
                    }
                  >
                    <Icon size={17} strokeWidth={1.9} aria-hidden="true" />
                    <span>{item.label}</span>
                  </NavLink>
                );
              })}
            </div>
          ))}
        </nav>

        <div className="sidebar__domain">
          <div className="domain-plate">
            <div className="domain-plate__tag">DEMO DOMAIN</div>
            <strong>R-101 演示反应器</strong>
            <span>预热／压力单元 · 合成机理数据</span>
            <span className="domain-plate__warning">
              非真实装置数据，不得用于安全认证
            </span>
          </div>
        </div>
      </aside>

      <div className="main-shell">
        <header className="topbar">
          <button
            type="button"
            className="icon-button topbar__menu"
            onClick={() => setMenuOpen(true)}
            aria-label="打开导航"
          >
            <Menu size={19} />
          </button>
          <div className="breadcrumbs" aria-label="当前位置">
            <span>IATP</span>
            <span className="breadcrumbs__sep">/</span>
            <strong>{title}</strong>
          </div>
          <div className="topbar__right">
            <span className="environment-pill">DEMO</span>
            <span
              className={`connection ${online ? "connection--online" : "connection--offline"}`}
              title={health.error ?? "后端连接正常"}
            >
              <span className="connection__dot" aria-hidden="true" />
              {online ? "API 在线" : "API 离线"}
            </span>
          </div>
        </header>

        <main className="content">
          <Outlet />
        </main>

        <footer className="page-footer">
          <span>IATP v0.1.0 · 漏报优先 · 权限不可绕过 · 结论可复现</span>
          <span>演示域为合成机理数据，不代表真实装置工程结论。</span>
        </footer>
      </div>
    </div>
  );
}
