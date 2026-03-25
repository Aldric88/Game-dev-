import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './AuthContext';
import Navbar from './components/Navbar';
import PixelBlast from './components/PixelBlast';
import Landing from './pages/Landing';
import Login from './pages/Login';
import Register from './pages/Register';
import Projects from './pages/Projects';
import ProjectDetail from './pages/ProjectDetail';
import Profile from './pages/Profile';
import PlayPage from './pages/PlayPage';
import Discover from './pages/Discover';

function PrivateRoute({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <PageLoader />;
  return user ? children : <Navigate to="/login" replace />;
}

function GuestRoute({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <PageLoader />;
  return !user ? children : <Navigate to="/projects" replace />;
}

function PageLoader() {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      height: '100vh', background: '#000',
    }}>
      <div style={{
        width: 24, height: 24, border: '2px solid #333',
        borderTopColor: '#f5f5f7', borderRadius: '50%',
        animation: 'spin 0.8s linear infinite',
      }} />
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        {/* Layered background: gradient base + PixelBlast overlay */}
        <div className="app-bg-gradient" />
        <PixelBlast
          variant="circle"
          color="#ffffff"
          pixelSize={2}
          patternScale={3}
          patternDensity={0.5}
          speed={0.2}
          edgeFade={0.4}
          enableRipples
          transparent
          style={{
            position: 'fixed',
            inset: 0,
            zIndex: 1,
            pointerEvents: 'auto',
            opacity: 0.08,
          }}
        />
        <div style={{ position: 'relative', zIndex: 2 }}>
          <Navbar />
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/login" element={<GuestRoute><Login /></GuestRoute>} />
            <Route path="/register" element={<GuestRoute><Register /></GuestRoute>} />
            <Route path="/projects" element={<PrivateRoute><Projects /></PrivateRoute>} />
            <Route path="/projects/:id" element={<PrivateRoute><ProjectDetail /></PrivateRoute>} />
            <Route path="/profile" element={<PrivateRoute><Profile /></PrivateRoute>} />
            <Route path="/play/:id" element={<PlayPage />} />
            <Route path="/discover" element={<Discover />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </div>
      </AuthProvider>
    </BrowserRouter>
  );
}
