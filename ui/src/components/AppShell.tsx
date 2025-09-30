import { NavLink, Outlet } from 'react-router-dom';

const navLinks = [
  { to: '/', label: 'Submit Task' },
  { to: '/tasks', label: 'Tasks' },
  { to: '/projects', label: 'Projects' },
  { to: '/settings', label: 'Settings' },
];

function AppShell() {
  return (
    <div className="app-shell">
      <header className="hero">
        <h1>Containerized Agent Runner</h1>
        <p>Register projects, submit agent tasks, and monitor results locally.</p>
      </header>

      <div className="app-layout">
        <nav className="app-nav" aria-label="Main navigation">
          <ul>
            {navLinks.map((link) => (
              <li key={link.to}>
                <NavLink
                  to={link.to}
                  className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')}
                  end={link.to === '/'}
                >
                  {link.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>

        <main className="app-main">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

export default AppShell;
