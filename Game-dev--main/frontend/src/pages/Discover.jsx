import { useEffect, useState, useRef, useCallback } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { projects as api, getPublicPlayUrl } from '../api';
import { useAuth } from '../AuthContext';
import './Discover.css';

function HeartIcon({ filled }) {
  return filled ? (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="currentColor">
      <path d="M7 12.5S1 8.5 1 4.5a3 3 0 015-2.24A3 3 0 0113 4.5c0 4-6 8-6 8z" />
    </svg>
  ) : (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.3">
      <path d="M7 12.5S1 8.5 1 4.5a3 3 0 015-2.24A3 3 0 0113 4.5c0 4-6 8-6 8z" />
    </svg>
  );
}

function Spinner() {
  return <div className="dc-spinner" />;
}

function ProjectCard({ project, onLike, liking, user, onSimilar }) {
  const p = project;
  return (
    <div className="dc-card">
      <div className="dc-card-top">
        <span className="dc-card-type">{p.design_doc?.game_type || p.framework}</span>
        <button
          className={`dc-like-btn${p.user_liked ? ' liked' : ''}`}
          onClick={() => onLike(p)}
          disabled={liking[p.project_id]}
          title={user ? (p.user_liked ? 'Unlike' : 'Like') : 'Sign in to like'}
        >
          <HeartIcon filled={p.user_liked} />
          <span>{p.likes}</span>
        </button>
      </div>
      <h3 className="dc-card-name">{p.name}</h3>
      {p.description && <p className="dc-card-desc">{p.description}</p>}
      <div className="dc-card-stats">
        <span className="dc-card-plays" title="Total plays">
          <svg width="11" height="11" viewBox="0 0 11 11" fill="currentColor">
            <path d="M2 1.5l7 4-7 4V1.5z" />
          </svg>
          {p.plays ?? 0}
        </span>
      </div>
      <div className="dc-card-footer">
        <button
          className="dc-play-btn"
          onClick={() => {
            if (user) api.recordPlay(p.project_id).catch(() => {});
            window.open(getPublicPlayUrl(p.project_id), '_blank', 'noopener,noreferrer');
          }}
        >
          <svg width="10" height="12" viewBox="0 0 10 12" fill="currentColor">
            <path d="M1 1l8 5-8 5V1z" />
          </svg>
          Play
        </button>
        <button className="dc-similar-btn" onClick={() => onSimilar(p)} title="Find similar games">
          Similar
        </button>
      </div>
    </div>
  );
}

export default function Discover() {
  const { user } = useAuth();
  const navigate = useNavigate();

  const [search, setSearch]           = useState('');
  const [searching, setSearching]     = useState(false);
  const [searchResults, setSearchResults] = useState([]);

  const [popular, setPopular]         = useState([]);
  const [popularLoading, setPopularLoading] = useState(true);

  const [recs, setRecs]               = useState([]);
  const [recsLoading, setRecsLoading] = useState(true);
  const [recsError, setRecsError]     = useState(false);

  const [liking, setLiking]           = useState({});
  const [suggestions, setSuggestions] = useState([]);
  const [similarFor, setSimilarFor]   = useState(null);   // { project_id, name }
  const [similarList, setSimilarList] = useState([]);
  const [similarLoading, setSimilarLoading] = useState(false);
  const timerRef                      = useRef(null);

  // Load popular (top 6) once
  useEffect(() => {
    api.discover('', 6)
      .then(setPopular)
      .catch(() => {})
      .finally(() => setPopularLoading(false));
  }, []);

  // Load "For You" once (auth-gated)
  useEffect(() => {
    if (!user) { setRecsLoading(false); return; }
    api.recommendations()
      .then(setRecs)
      .catch(() => setRecsError(true))
      .finally(() => setRecsLoading(false));
  }, [user]);

  // Load search suggestions (auth-gated)
  useEffect(() => {
    if (!user) return;
    api.searchSuggestions()
      .then(setSuggestions)
      .catch(() => {});
  }, [user]);

  // Debounced search
  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    if (!search.trim()) { setSearchResults([]); setSearching(false); return; }
    setSearching(true);
    timerRef.current = setTimeout(() => {
      api.discover(search.trim(), 50)
        .then(setSearchResults)
        .catch(() => setSearchResults([]))
        .finally(() => setSearching(false));
    }, 300);
    return () => clearTimeout(timerRef.current);
  }, [search]);

  // Shared like handler — updates whichever list contains the project
  const updateLikes = useCallback((pid, res) => {
    const upd = p => p.project_id === pid ? { ...p, likes: res.likes, user_liked: res.liked } : p;
    setPopular(prev => prev.map(upd));
    setRecs(prev => prev.map(upd));
    setSearchResults(prev => prev.map(upd));
  }, []);

  const handleLike = useCallback(async (project) => {
    if (!user) { navigate('/login'); return; }
    if (liking[project.project_id]) return;
    setLiking(prev => ({ ...prev, [project.project_id]: true }));
    try {
      const res = await api.toggleLike(project.project_id);
      updateLikes(project.project_id, res);
    } catch { /* ignore */ }
    finally { setLiking(prev => ({ ...prev, [project.project_id]: false })); }
  }, [user, liking, navigate, updateLikes]);

  const handleSimilar = useCallback(async (project) => {
    if (similarFor?.project_id === project.project_id) {
      setSimilarFor(null); setSimilarList([]); return;
    }
    setSimilarFor({ project_id: project.project_id, name: project.name });
    setSimilarList([]);
    setSimilarLoading(true);
    try {
      const results = await api.similarGames(project.project_id);
      setSimilarList(results || []);
    } catch { setSimilarList([]); }
    finally { setSimilarLoading(false); }
  }, [similarFor]);

  const isSearching = search.trim().length > 0;

  return (
    <div className="dc-page">

      {/* ── Header ── */}
      <div className="dc-header">
        <h1 className="dc-title">Discover</h1>
        <p className="dc-sub">Explore games built by the community</p>
        <div className="dc-search-wrap">
          <svg className="dc-search-icon" width="15" height="15" viewBox="0 0 15 15" fill="none">
            <circle cx="6.5" cy="6.5" r="4.5" stroke="currentColor" strokeWidth="1.3" />
            <path d="M10 10l3 3" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
          </svg>
          <input
            className="dc-search"
            placeholder="Search games..."
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
          {searching && <span className="dc-search-spin" />}
          {search && (
            <button className="dc-search-clear" onClick={() => setSearch('')}>
              <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                <path d="M1 1l8 8M9 1L1 9" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
              </svg>
            </button>
          )}
        </div>
        {!search && suggestions.length > 0 && (
          <div className="dc-suggestions">
            <span className="dc-suggestions-label">Try:</span>
            {suggestions.map(s => (
              <button
                key={s}
                className="dc-suggestion-chip"
                onClick={() => setSearch(s)}
              >
                {s}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* ── Search results (replaces sections when active) ── */}
      {isSearching ? (
        <div className="dc-section">
          {searching ? (
            <div className="dc-center"><Spinner /></div>
          ) : searchResults.length === 0 ? (
            <div className="dc-empty">No games match "{search}"</div>
          ) : (
            <div className="dc-grid">
              {searchResults.map(p => (
                <ProjectCard key={p.project_id} project={p} onLike={handleLike} liking={liking} user={user} onSimilar={handleSimilar} />
              ))}
            </div>
          )}
        </div>
      ) : (
        <>
          {/* ── Popular Creations ── */}
          <div className="dc-section">
            <div className="dc-section-header">
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <path d="M7 1l1.5 3.5L12 5l-2.5 2.5.5 3.5L7 9.5 4 11l.5-3.5L2 5l3.5-.5L7 1z"
                  fill="#f59e0b" stroke="#f59e0b" strokeWidth="0.5" strokeLinejoin="round" />
              </svg>
              <h2 className="dc-section-title">Popular Creations</h2>
            </div>
            {popularLoading ? (
              <div className="dc-center"><Spinner /></div>
            ) : popular.length === 0 ? (
              <div className="dc-empty">No public games yet. Be the first to publish!</div>
            ) : (
              <div className="dc-grid dc-grid-popular">
                {popular.map((p, i) => (
                  <div key={p.project_id} className="dc-card-wrap">
                    {i < 3 && (
                      <span className={`dc-rank dc-rank-${i + 1}`}>#{i + 1}</span>
                    )}
                    <ProjectCard project={p} onLike={handleLike} liking={liking} user={user} onSimilar={handleSimilar} />
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* ── Similar Games ── */}
          {similarFor && (
            <div className="dc-section dc-similar-section">
              <div className="dc-section-header">
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                  <circle cx="5" cy="5" r="3" stroke="#34d399" strokeWidth="1.2" />
                  <circle cx="10" cy="9" r="2.5" stroke="#34d399" strokeWidth="1.2" />
                  <path d="M7.5 6.5l1.5 1.5" stroke="#34d399" strokeWidth="1.2" strokeLinecap="round" />
                </svg>
                <h2 className="dc-section-title">Similar to "{similarFor.name}"</h2>
                <button className="dc-similar-close" onClick={() => { setSimilarFor(null); setSimilarList([]); }}>
                  <svg width="10" height="10" viewBox="0 0 10 10" fill="none"><path d="M1 1l8 8M9 1L1 9" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/></svg>
                </button>
              </div>
              {similarLoading ? (
                <div className="dc-center"><Spinner /></div>
              ) : similarList.length === 0 ? (
                <div className="dc-empty">No similar games found yet — more games needed to cluster.</div>
              ) : (
                <div className="dc-grid">
                  {similarList.map(p => (
                    <ProjectCard key={p.project_id} project={p} onLike={handleLike} liking={liking} user={user} onSimilar={handleSimilar} />
                  ))}
                </div>
              )}
            </div>
          )}

          {/* ── For You ── */}
          <div className="dc-section">
            <div className="dc-section-header">
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <circle cx="7" cy="5" r="2.5" stroke="#818cf8" strokeWidth="1.2" />
                <path d="M2 12c0-2.76 2.24-5 5-5s5 2.24 5 5" stroke="#818cf8" strokeWidth="1.2" strokeLinecap="round" />
              </svg>
              <h2 className="dc-section-title">For You</h2>
              {user && <span className="dc-section-badge">ML-powered</span>}
            </div>

            {!user ? (
              <div className="dc-foryou-gate">
                <p>Sign in to get game recommendations based on what you build and play</p>
                <Link to="/login" className="dc-foryou-btn">Sign In</Link>
              </div>
            ) : recsLoading ? (
              <div className="dc-center"><Spinner /></div>
            ) : recsError ? (
              <div className="dc-empty">Could not load recommendations.</div>
            ) : recs.length === 0 ? (
              <div className="dc-empty">
                Build or like some games to get personalised picks!
              </div>
            ) : (
              <div className="dc-grid">
                {recs.map(p => (
                  <ProjectCard key={p.project_id} project={p} onLike={handleLike} liking={liking} user={user} onSimilar={handleSimilar} />
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
