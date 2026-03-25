import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../AuthContext';
import './Navbar.css';

export default function Navbar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/');
  };

  return (
    <nav className="navbar">
      <div className="navbar-inner">
        <Link to="/" className="navbar-brand">
          ForgeAI
        </Link>

        <div className="navbar-links">
          <Link to="/discover" className="navbar-link">Discover</Link>
          {user ? (
            <>
              <Link to="/projects" className="navbar-link">Projects</Link>
              <Link to="/profile" className="navbar-link">Profile</Link>
              <span className="navbar-user">{user.username}</span>
              <button onClick={handleLogout} className="navbar-btn-ghost">
                Sign Out
              </button>
            </>
          ) : (
            <>
              <Link to="/login" className="navbar-link">Sign In</Link>
              <Link to="/register" className="navbar-btn-primary">
                Get Started
              </Link>
            </>
          )}
        </div>
      </div>
    </nav>
  );
}
