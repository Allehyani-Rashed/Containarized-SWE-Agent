import { NavLink } from 'react-router-dom';
import Icon, { IconType } from './Icon';
import './Sidebar.css';

const navLinks: Array<{ to: string; label: string; icon: IconType }> = [
  { to: '/', label: 'Submit Task', icon: 'edit' },
  { to: '/tasks', label: 'Tasks', icon: 'clipboard' },
  { to: '/projects', label: 'Projects', icon: 'folder' },
  { to: '/settings', label: 'Settings', icon: 'settings' },
  { to: '/help', label: 'Help', icon: 'help' },
];

function Sidebar() {
  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <div className="sidebar-brand-icon">
          <svg width="32" height="32" viewBox="0 0 32 32" fill="none">
            <rect width="32" height="32" rx="8" fill="#4F46E5"/>
            <path d="M16 8L20 12L16 16L12 12L16 8Z" fill="white"/>
            <path d="M16 16L20 20L16 24L12 20L16 16Z" fill="#A5B4FC"/>
            <path d="M8 16L12 12L12 20L8 16Z" fill="#818CF8"/>
            <path d="M24 16L20 12L20 20L24 16Z" fill="#818CF8"/>
          </svg>
        </div>
        <div className="sidebar-brand-text">
          <div className="sidebar-brand-title">Codex Agent</div>
          <div className="sidebar-brand-subtitle">Containerized Runner</div>
        </div>
      </div>

      <nav className="sidebar-nav" aria-label="Main navigation">
        <ul className="sidebar-nav-list">
          {navLinks.map((link) => (
            <li key={link.to}>
              <NavLink
                to={link.to}
                className={({ isActive }) =>
                  isActive ? 'sidebar-nav-link active' : 'sidebar-nav-link'
                }
                end={link.to === '/'}
              >
                <span className="sidebar-nav-icon">
                  <Icon type={link.icon} size={20} />
                </span>
                <span className="sidebar-nav-label">{link.label}</span>
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
    </aside>
  );
}

export default Sidebar;
