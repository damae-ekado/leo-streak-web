import { Link, useLocation } from 'react-router-dom'
import './Navbar.css'

const NAV_LINKS = [
  { to: '/',          label: 'Upload' },
  { to: '/dashboard', label: 'Dashboard' },
]

export default function Navbar() {
  const { pathname } = useLocation()

  return (
    <nav className="navbar">
      <Link to="/" className="navbar-logo">
        <span className="navbar-logo-icon">✦</span>
        <span>LEO<em>streak</em></span>
      </Link>

      <div className="navbar-links">
        {NAV_LINKS.map(({ to, label }) => (
          <Link
            key={to}
            to={to}
            className={`navbar-link ${pathname === to ? 'active' : ''}`}
          >
            {label}
          </Link>
        ))}
      </div>

      <div className="navbar-status" id="api-status" />
    </nav>
  )
}