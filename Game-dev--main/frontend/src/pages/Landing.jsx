import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { dashboard } from '../api';
import { useAuth } from '../AuthContext';
import Card from '../components/Card';
import Badge from '../components/Badge';
import Button from '../components/Button';
import './Landing.css';

export default function Landing() {
  const { user } = useAuth();
  const [data, setData] = useState(null);

  useEffect(() => {
    dashboard.summary().then(setData).catch(() => {});
  }, []);

  return (
    <div className="landing">
      {/* Hero */}
      <section className="hero">
        <div className="container">
          <div className="hero-content">
            <div className="hero-text">
              {data?.hero_badge && (
                <Badge variant="blue">{data.hero_badge}</Badge>
              )}
              <h1 className="hero-title">
                {data?.hero_title || 'Build Games with AI'}
              </h1>
              <p className="hero-sub">
                {data?.hero_subtext || 'An intelligent platform that transforms your ideas into playable games using advanced AI agents.'}
              </p>
              <div className="hero-actions">
                {user ? (
                  <Link to="/projects">
                    <Button size="lg">Open Dashboard</Button>
                  </Link>
                ) : (
                  <>
                    <Link to="/register">
                      <Button size="lg">Get Started</Button>
                    </Link>
                    <Link to="/login">
                      <Button size="lg" variant="secondary">Sign In</Button>
                    </Link>
                  </>
                )}
              </div>
            </div>
            <div className="hero-visual">
              <div className="hero-visual-inner">
                <div className="hero-code-line"><span className="hero-code-kw">const</span> game = <span className="hero-code-fn">createGame</span>({'{'})</div>
                <div className="hero-code-line"><span className="hero-code-kw">&nbsp;&nbsp;type:</span> <span className="hero-code-str">'platformer'</span>,</div>
                <div className="hero-code-line"><span className="hero-code-kw">&nbsp;&nbsp;ai:</span> <span className="hero-code-bool">true</span></div>
                <div className="hero-code-line">{'}'})</div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Metrics */}
      {data?.metrics && data.metrics.length > 0 && (
        <section className="section">
          <div className="container">
            <div className="metrics-grid">
              {data.metrics.map((m, i) => (
                <div key={i} className="metric-item">
                  <span className="metric-name">{m.name}</span>
                  <span className="metric-status">{m.status}</span>
                </div>
              ))}
            </div>
            {data.trusted_by && (
              <p className="trusted-text">{data.trusted_by}</p>
            )}
          </div>
        </section>
      )}

      {/* Features */}
      {data?.features && data.features.length > 0 && (
        <section className="section">
          <div className="container">
            <h2 className="section-title">Features</h2>
            <div className="features-grid">
              {data.features.map((f, i) => (
                <Card key={i} hover>
                  <h3 className="feature-title">{f.title}</h3>
                  <p className="feature-desc">{f.description}</p>
                </Card>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* Architecture */}
      {data?.architecture && data.architecture.length > 0 && (
        <section className="section">
          <div className="container">
            <h2 className="section-title">Architecture</h2>
            <div className="arch-grid">
              {data.architecture.map((a, i) => (
                <div key={i} className="arch-item">
                  <div className="arch-number">{String(i + 1).padStart(2, '0')}</div>
                  <div>
                    <h4 className="arch-title">{a.title}</h4>
                    <p className="arch-desc">{a.description}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* Roadmap */}
      {data?.roadmap && data.roadmap.length > 0 && (
        <section className="section section-last">
          <div className="container">
            <h2 className="section-title">Roadmap</h2>
            <div className="roadmap-grid">
              {data.roadmap.map((r, i) => (
                <Card key={i}>
                  <div className="roadmap-header">
                    <Badge variant="default">{r.phase}</Badge>
                    <span className="roadmap-window">{r.window}</span>
                  </div>
                  <p className="roadmap-desc">{r.description}</p>
                </Card>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* Footer */}
      <footer className="footer">
        <div className="container">
          <p className="footer-text">
            {data?.brand_name || 'ForgeAI'}. All rights reserved.
          </p>
        </div>
      </footer>
    </div>
  );
}
