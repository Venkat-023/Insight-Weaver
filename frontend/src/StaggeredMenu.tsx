import React, { useEffect, useMemo, useState } from "react";
import { LogOut, Menu, Moon, RefreshCw, Sun, X } from "lucide-react";
import "./StaggeredMenu.css";

export interface StaggeredMenuItem {
  id?: string;
  label: string;
  ariaLabel?: string;
  link?: string;
  icon?: React.ComponentType<{ size?: number; strokeWidth?: number }>;
  emphasized?: boolean;
}

export interface StaggeredMenuSocialItem {
  label: string;
  link: string;
}

export interface StaggeredMenuProps {
  position?: "left" | "right";
  items?: StaggeredMenuItem[];
  colors?: string[];
  socialItems?: StaggeredMenuSocialItem[];
  displaySocials?: boolean;
  displayItemNumbering?: boolean;
  activeItem?: string;
  onItemSelect?: (id: string) => void;
  className?: string;
  title?: string;
  subtitle?: string;
  logoUrl?: string;
  menuButtonColor?: string;
  openMenuButtonColor?: string;
  accentColor?: string;
  changeMenuColorOnOpen?: boolean;
  closeOnClickAway?: boolean;
  onMenuOpen?: () => void;
  onMenuClose?: () => void;
  isFixed?: boolean;
  user?: { username?: string; display_name?: string; email?: string } | null;
  onLogout?: () => void;
  theme?: "light" | "dark";
  setTheme?: (theme: "light" | "dark") => void;
  modelStatus?: { status?: string; message?: string } | null;
  onRefreshModel?: () => void;
  onResetWorkspace?: () => void;
}

function classNames(...items: Array<string | false | null | undefined>) {
  return items.filter(Boolean).join(" ");
}

export const StaggeredMenu: React.FC<StaggeredMenuProps> = ({
  position = "left",
  items = [],
  accentColor,
  activeItem,
  onItemSelect,
  className,
  title = "Insight Weaver",
  user,
  onLogout,
  theme = "dark",
  setTheme,
  modelStatus,
  onRefreshModel,
  onResetWorkspace,
  onMenuOpen,
  onMenuClose
}) => {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    function handleResize() {
      if (window.innerWidth >= 1024) {
        setOpen(false);
      }
    }

    handleResize();
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  const profileName = user?.display_name || user?.username || "Researcher";
  const profileMeta = user?.email || user?.username || "Scientific workspace";
  const modelState = useMemo(() => {
    const status = (modelStatus?.status || "unknown").toLowerCase();
    if (status === "ready") return "Model ready";
    if (status === "warming") return "Warming models";
    if (status === "failed") return "Model unavailable";
    return "Model status";
  }, [modelStatus]);

  function handleItemClick(id: string) {
    onItemSelect?.(id);
    setOpen(false);
  }

  useEffect(() => {
    if (open) {
      onMenuOpen?.();
    } else {
      onMenuClose?.();
    }
  }, [open, onMenuOpen, onMenuClose]);

  function toggleTheme() {
    if (!setTheme) return;
    setTheme(theme === "dark" ? "light" : "dark");
  }

  return (
    <div
      className={classNames("staggered-menu-shell", className)}
      data-open={open || undefined}
      data-position={position}
      data-theme={theme}
      style={accentColor ? ({ ["--sm-accent" as never]: accentColor } as React.CSSProperties) : undefined}
    >
      <button
        type="button"
        className="sm-mobile-toggle"
        aria-label={open ? "Close navigation" : "Open navigation"}
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
      >
        <span className="sm-mobile-toggle-icon" aria-hidden="true">
          {open ? <X size={18} strokeWidth={2} /> : <Menu size={18} strokeWidth={2} />}
        </span>
        <span className="sm-mobile-toggle-label">Navigation</span>
      </button>

      <div
        className="sm-mobile-backdrop"
        aria-hidden={!open}
        onClick={() => setOpen(false)}
      />

      <aside className="staggered-menu-panel" aria-label="Workspace navigation">
        <div className="sm-panel-top">
          <div className="sm-brand-lockup">
            <div className="sm-brand-copy">
              <span className="sm-brand-title">{title}</span>
            </div>
          </div>

          <div className="sm-utility-row">
            <button
              type="button"
              className="sm-utility-button"
              onClick={toggleTheme}
              aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
              title={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
            >
              {theme === "dark" ? <Sun size={16} strokeWidth={2} /> : <Moon size={16} strokeWidth={2} />}
            </button>
            <button
              type="button"
              className="sm-utility-button"
              onClick={onRefreshModel}
              aria-label="Refresh model status"
              title="Refresh model status"
            >
              <RefreshCw size={16} strokeWidth={2} />
            </button>
          </div>
        </div>

        <div className="sm-status-card">
          <span className={classNames("sm-status-dot", `is-${(modelStatus?.status || "unknown").toLowerCase()}`)} />
          <div>
            <p className="sm-status-label">{modelState}</p>
            <p className="sm-status-meta">{modelStatus?.message || "Evidence-grounded navigation for connected research."}</p>
          </div>
        </div>

        <nav className="sm-nav" aria-label="Primary">
          <ul className="sm-nav-list">
            {items.map((item, index) => {
              const Icon = item.icon;
              const itemId = item.id || item.link || item.label;
              const isActive = itemId === activeItem;
              return (
                <li
                  key={itemId}
                  className="sm-nav-item"
                  style={{ animationDelay: `${index * 45}ms` }}
                >
                  <button
                    type="button"
                    className={classNames(
                      "sm-nav-link",
                      isActive && "is-active",
                      item.emphasized && "is-emphasized"
                    )}
                    aria-label={item.ariaLabel || item.label}
                    aria-current={isActive ? "page" : undefined}
                    onClick={() => handleItemClick(itemId)}
                  >
                    <span className="sm-nav-main">
                      {Icon ? <Icon size={16} strokeWidth={2} /> : null}
                      <span>{item.label}</span>
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </nav>

        <div className="sm-panel-footer">
          <button
            type="button"
            className="sm-workspace-button"
            onClick={onResetWorkspace}
          >
            Reset workspace
          </button>

          <div className="sm-profile-card">
            <div className="sm-profile-avatar" aria-hidden="true">
              {profileName.slice(0, 2).toUpperCase()}
            </div>
            <div className="sm-profile-copy">
              <p className="sm-profile-name">{profileName}</p>
              <p className="sm-profile-meta">{profileMeta}</p>
            </div>
          </div>

          <button type="button" className="sm-logout-button" onClick={onLogout}>
            <LogOut size={16} strokeWidth={2} />
            <span>Logout</span>
          </button>
        </div>
      </aside>
    </div>
  );
};

export default StaggeredMenu;
