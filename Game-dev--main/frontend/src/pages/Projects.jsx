import { useEffect, useState, useRef, useCallback } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { projects as api, ai as aiApi } from '../api';
import Card from '../components/Card';
import Badge from '../components/Badge';
import Modal from '../components/Modal';
import './Projects.css';

const STATUS_BADGE = {
  draft: 'default',
  building: 'orange',
  ready: 'green',
  error: 'red',
};

function formatDate(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

function nameFromPrompt(prompt) {
  const cleaned = prompt.replace(/[^a-zA-Z0-9 ]/g, '').trim();
  const words = cleaned.split(/\s+/).slice(0, 4);
  return words.map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase()).join(' ') || 'New Game';
}

export default function Projects() {
  const navigate = useNavigate();
  const [list, setList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [confirmDelete, setConfirmDelete] = useState(null); // project_id
  const [duplicating, setDuplicating] = useState(null); // project_id

  /* Prompt state */
  const [prompt, setPrompt] = useState('');
  const [attachments, setAttachments] = useState([]); // { name, content }
  const [sending, setSending] = useState(false);
  const [status, setStatus] = useState('');
  const [error, setError] = useState('');

  const [searching, setSearching]     = useState(false);
  const [searchResults, setSearchResults] = useState(null); // null = show full list
  const [searchMeta, setSearchMeta]   = useState({});       // project_id -> match_type
  const [searchInfo, setSearchInfo]   = useState(null);     // {keyword_hits, ml_hits, ...}
  const [suggestions, setSuggestions] = useState([]);

  const inputRef      = useRef(null);
  const fileRef       = useRef(null);
  const searchTimerRef = useRef(null);

  const SUGGESTIONS = [
    'Retro platformer with pixel art and power-ups',
    'Top-down racing game with drifting mechanics',
    'Physics-based puzzle game with gravity switching',
    'Space shooter with procedural enemy waves',
  ];

  const TEMPLATES = [
    { id: 'flappy', name: 'Flappy Bird', desc: 'Classic tap-to-fly obstacle game', emoji: '🐦', prompt: 'Create a flappy bird clone with a bird that flies through pipes. Tap to flap. Score increases each pipe passed. Game over on collision.' },
    { id: 'platformer', name: 'Platformer', desc: 'Side-scrolling jump adventure', emoji: '🏃', prompt: 'Create a side-scrolling platformer with a character that can run and jump. Include platforms, coins to collect, and enemies to avoid.' },
    { id: 'snake', name: 'Snake', desc: 'Classic grid movement game', emoji: '🐍', prompt: 'Create a classic snake game on a grid. The snake grows when eating food. Game over if it hits walls or itself. Track high score.' },
    { id: 'shooter', name: 'Space Shooter', desc: 'Top-down bullet hell', emoji: '🚀', prompt: 'Create a top-down space shooter. Player ship moves and shoots bullets. Waves of alien enemies descend. Collect power-ups. Boss every 3 waves.' },
    { id: 'racing', name: 'Racing', desc: 'Top-down car racing game', emoji: '🏎️', prompt: 'Create a top-down racing game. Player controls a car around a track. Compete against AI opponents. Collect boost power-ups. 3 laps to win.' },
    { id: 'puzzle', name: 'Puzzle', desc: 'Block matching puzzle', emoji: '🧩', prompt: 'Create a block puzzle game like Tetris. Blocks fall from the top. Player rotates and positions them. Clear complete rows to score points. Speed increases over time.' },
  ];

  const load = useCallback(() => {
    setLoading(true);
    api.list()
      .then(setList)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    api.searchSuggestions()
      .then(setSuggestions)
      .catch(() => {});
  }, []);

  /* ── Debounced hybrid search ── */
  useEffect(() => {
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current);

    if (!search.trim()) {
      setSearchResults(null);
      setSearchMeta({});
      setSearchInfo(null);
      setSearching(false);
      return;
    }

    setSearching(true);
    searchTimerRef.current = setTimeout(async () => {
      try {
        const data = await api.search(search.trim());
        setSearchResults(data.results.map(r => r.project));
        const meta = {};
        data.results.forEach(r => { meta[r.project.project_id] = r.match_type; });
        setSearchMeta(meta);
        setSearchInfo({
          keyword_hits: data.keyword_hits,
          ml_hits: data.ml_hits,
          predicted_game_type: data.predicted_game_type,
        });
      } catch {
        // Backend unavailable — fall back to client-side per-token OR filter
        const tokens = search.toLowerCase().split(/\s+/).filter(t => t.length >= 2);
        setSearchResults(
          list.filter(p => {
            const haystack = [
              p.name,
              p.description || '',
              p.framework || '',
            ].join(' ').toLowerCase();
            return tokens.some(t => haystack.includes(t));
          })
        );
        setSearchMeta({});
        setSearchInfo(null);
      } finally {
        setSearching(false);
      }
    }, 300);

    return () => { if (searchTimerRef.current) clearTimeout(searchTimerRef.current); };
  }, [search, list]);

  /* ── Attach files ── */
  const handleAttach = () => fileRef.current?.click();

  const onFilesSelected = (e) => {
    const files = Array.from(e.target.files || []);
    files.forEach((file) => {
      const reader = new FileReader();
      reader.onload = () => {
        const isImage = file.type.startsWith('image/');
        setAttachments((prev) => [
          ...prev,
          {
            name: file.name,
            type: file.type,
            content: isImage
              ? `[Image: ${file.name}]`
              : reader.result,
          },
        ]);
      };
      if (file.type.startsWith('image/')) {
        reader.readAsDataURL(file);
      } else {
        reader.readAsText(file);
      }
    });
    // reset so same file can be re-selected
    e.target.value = '';
  };

  const removeAttachment = (idx) => {
    setAttachments((prev) => prev.filter((_, i) => i !== idx));
  };

  /* ── Send: create + generate + show preview ── */
  const handleSend = async (e) => {
    e?.preventDefault();
    const text = prompt.trim();
    if (!text || sending) return;

    setSending(true);
    setError('');
    setStatus('Initializing multi-agent pipeline...');

    // Build full prompt with attachment context
    let fullPrompt = text;
    if (attachments.length > 0) {
      const attachText = attachments.map((a) =>
        `--- Attached: ${a.name} ---\n${a.content}`
      ).join('\n\n');
      fullPrompt = `${text}\n\n${attachText}`;
    }

    try {
      const proj = await api.create({
        name: nameFromPrompt(text),
        description: text,
        framework: 'phaser',
      });

      setStatus('Running Design, Script, Scene, and Asset agents via Gemini...');
      await aiApi.generate({
        project_id: proj.project_id,
        prompt: fullPrompt,
        framework: 'phaser',
      });

      setStatus('');
      setPrompt('');
      setAttachments([]);
      navigate(`/projects/${proj.project_id}`);
    } catch (err) {
      setError(err.message);
      setStatus('');
    } finally {
      setSending(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleDeleteConfirm = async () => {
    const id = confirmDelete;
    setConfirmDelete(null);
    try {
      await api.delete(id);
      setList((prev) => prev.filter((p) => p.project_id !== id));
    } catch {}
  };

  const handleDelete = (id, e) => {
    e.preventDefault();
    e.stopPropagation();
    setConfirmDelete(id);
  };

  const handleDuplicate = async (id, e) => {
    e.preventDefault();
    e.stopPropagation();
    setDuplicating(id);
    try {
      const copy = await api.duplicate(id);
      setList((prev) => [copy, ...prev]);
    } catch (err) {
      alert(err.message);
    } finally {
      setDuplicating(null);
    }
  };

  const filteredList = (search.trim() && searchResults !== null) ? searchResults : list;

  return (
    <div className="projects-page">
      {/* Delete confirm modal */}
      <Modal open={!!confirmDelete} onClose={() => setConfirmDelete(null)} title="Delete project">
        <p style={{ fontSize: 13, color: '#888', marginBottom: 20 }}>
          This will permanently delete the project and all its files. This cannot be undone.
        </p>
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <button onClick={() => setConfirmDelete(null)} style={{ padding: '6px 14px', fontSize: 12, background: '#111', color: '#888', border: '1px solid #222', borderRadius: 6, cursor: 'pointer' }}>
            Cancel
          </button>
          <button onClick={handleDeleteConfirm} style={{ padding: '6px 14px', fontSize: 12, background: '#1a0000', color: '#f87171', border: '1px solid #3a0000', borderRadius: 6, cursor: 'pointer', fontWeight: 600 }}>
            Delete
          </button>
        </div>
      </Modal>
      {/* ── Centered Prompt Area ── */}
      <div className="prompt-hero">
        <div className="prompt-container">
          <h1 className="prompt-heading">What do you want to build?</h1>
          <p className="prompt-subheading">Describe your game idea and our AI agents will generate it for you</p>

          {error && <div className="prompt-error">{error}</div>}

          {status && (
            <div className="prompt-status">
              <div className="prompt-status-spinner" />
              <span>{status}</span>
            </div>
          )}

          <form className="prompt-form" onSubmit={handleSend}>
            <div className="prompt-box">
              <textarea
                ref={inputRef}
                className="prompt-input"
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Describe your game idea..."
                rows={4}
                disabled={sending}
              />

              {/* Attachment chips */}
              {attachments.length > 0 && (
                <div className="prompt-attachments">
                  {attachments.map((a, i) => (
                    <span key={i} className="prompt-chip">
                      <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                        <path d="M6.5 1.5v5a2 2 0 01-4 0v-4a1 1 0 012 0v3.5" stroke="currentColor" strokeWidth="1" strokeLinecap="round"/>
                      </svg>
                      {a.name}
                      <button type="button" className="prompt-chip-x" onClick={() => removeAttachment(i)}>
                        <svg width="8" height="8" viewBox="0 0 8 8" fill="none">
                          <path d="M1 1l6 6M7 1l-6 6" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/>
                        </svg>
                      </button>
                    </span>
                  ))}
                </div>
              )}

              <div className="prompt-actions">
                {/* Attach button */}
                <button type="button" className="prompt-attach" onClick={handleAttach} title="Attach files or images">
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                    <path d="M8 1.5v9M3.5 6.5l4.5-4.5 4.5 4.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
                    <path d="M2 11v2.5h12V11" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                </button>
                <input
                  ref={fileRef}
                  type="file"
                  multiple
                  accept="image/*,.txt,.md,.json,.html,.css,.js,.pdf,.doc,.docx"
                  style={{ display: 'none' }}
                  onChange={onFilesSelected}
                />

                {/* Send button */}
                <button
                  type="submit"
                  className="prompt-send"
                  disabled={sending || !prompt.trim()}
                >
                  {sending ? (
                    <div className="prompt-send-spinner" />
                  ) : (
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                      <path d="M2.5 8h11M8.5 3l5 5-5 5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                    </svg>
                  )}
                </button>
              </div>
            </div>
          </form>

          {/* ── Suggestion chips ── */}
          <div className="prompt-suggestions">
            <span className="prompt-suggestions-label">Try these</span>
            <div className="prompt-suggestions-list">
              {SUGGESTIONS.map((s, i) => (
                <button
                  key={i}
                  type="button"
                  className="prompt-suggestion"
                  onClick={() => { setPrompt(s); inputRef.current?.focus(); }}
                  disabled={sending}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* ── Templates section ── */}
      <div className="templates-section">
        <div className="templates-inner">
          <p className="templates-heading">Start from a template</p>
          <div className="templates-row">
            {TEMPLATES.map((t) => (
              <button
                key={t.id}
                className="template-card"
                disabled={sending}
                onClick={() => {
                  setPrompt(t.prompt);
                  inputRef.current?.focus();
                  window.scrollTo({ top: 0, behavior: 'smooth' });
                }}
              >
                <span className="template-emoji">{t.emoji}</span>
                <span className="template-name">{t.name}</span>
                <span className="template-desc">{t.desc}</span>
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* ── Main content: projects + sidebar ── */}
      <div className="container-wide">
        <div className="projects-layout">
          {/* Left: project grid */}
          <div className="projects-main">
            <div className="projects-section-header">
              <h2 className="projects-section-title">Your Projects</h2>
              <span className="projects-count">{list.length}</span>
              <div style={{ position: 'relative', display: 'inline-flex', alignItems: 'center' }}>
                <input
                  className="projects-search"
                  placeholder={searching ? 'Searching...' : 'Search...'}
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                />
                {searching && (
                  <span style={{ position: 'absolute', right: 8, width: 10, height: 10, border: '2px solid #444', borderTopColor: '#888', borderRadius: '50%', animation: 'spin 0.7s linear infinite' }} />
                )}
              </div>
              {searchInfo && searchInfo.ml_hits > 0 && (
                <span style={{ fontSize: 11, color: '#666', marginLeft: 8 }}>
                  +{searchInfo.ml_hits} similar {searchInfo.predicted_game_type} game{searchInfo.ml_hits !== 1 ? 's' : ''}
                </span>
              )}
            </div>
            <div className="projects-grid">
              {filteredList.map((p) => (
                <Link key={p.project_id} to={`/projects/${p.project_id}`} className="project-link">
                  <Card hover className="project-card">
                    <div className="project-card-top">
                      <h3 className="project-name">{p.name}</h3>
                      <Badge variant={STATUS_BADGE[p.status] || 'default'}>{p.status}</Badge>
                      {searchMeta[p.project_id] === 'game_type' && (
                        <Badge variant="blue">Similar type</Badge>
                      )}
                    </div>
                    {p.description && <p className="project-desc">{p.description}</p>}
                    <div className="project-card-meta">
                      <span className="project-framework">{p.framework}</span>
                      <span className="project-date">{formatDate(p.updated_at)}</span>
                    </div>
                    <div className="project-card-actions">
                      <button
                        className="project-action-btn"
                        onClick={(e) => handleDuplicate(p.project_id, e)}
                        title="Duplicate"
                        disabled={duplicating === p.project_id}
                      >
                        {duplicating === p.project_id ? (
                          <div className="project-action-spinner" />
                        ) : (
                          <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
                            <rect x="4" y="4" width="8" height="8" rx="1.5" stroke="currentColor" strokeWidth="1.2"/>
                            <path d="M2 10V2h8" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/>
                          </svg>
                        )}
                      </button>
                      <button
                        className="project-action-btn project-delete"
                        onClick={(e) => handleDelete(p.project_id, e)}
                        title="Delete"
                      >
                        <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
                          <path d="M1.75 3.5h10.5M5.25 3.5V2.333c0-.322.261-.583.583-.583h2.334c.322 0 .583.261.583.583V3.5m1.75 0v8.167c0 .322-.261.583-.583.583H4.083a.583.583 0 01-.583-.583V3.5h7" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/>
                        </svg>
                      </button>
                    </div>
                  </Card>
                </Link>
              ))}

              {/* Ghost "New Project" card */}
              <button
                className="project-ghost"
                onClick={() => { inputRef.current?.focus(); window.scrollTo({ top: 0, behavior: 'smooth' }); }}
              >
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                  <path d="M12 5v14M5 12h14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
                </svg>
                <span>New Project</span>
              </button>
            </div>
          </div>

          {/* Right: sidebar */}
          <aside className="projects-sidebar">
            <div className="sidebar-section">
              <h3 className="sidebar-title">Recent Updates</h3>
              <div className="sidebar-list">
                <div className="sidebar-item">
                  <span className="sidebar-item-dot" />
                  <div>
                    <p className="sidebar-item-text">Multi-agent pipeline with Gemini</p>
                    <span className="sidebar-item-meta">v2.0</span>
                  </div>
                </div>
                <div className="sidebar-item">
                  <span className="sidebar-item-dot" />
                  <div>
                    <p className="sidebar-item-text">Phaser 3 framework support</p>
                    <span className="sidebar-item-meta">v1.8</span>
                  </div>
                </div>
                <div className="sidebar-item">
                  <span className="sidebar-item-dot" />
                  <div>
                    <p className="sidebar-item-text">Real-time preview in browser</p>
                    <span className="sidebar-item-meta">v1.5</span>
                  </div>
                </div>
                <div className="sidebar-item">
                  <span className="sidebar-item-dot" />
                  <div>
                    <p className="sidebar-item-text">File attachment support</p>
                    <span className="sidebar-item-meta">v1.3</span>
                  </div>
                </div>
              </div>
            </div>

            <div className="sidebar-section">
              <h3 className="sidebar-title">Quick Stats</h3>
              <div className="sidebar-stats">
                <div className="sidebar-stat">
                  <span className="sidebar-stat-value">{list.length}</span>
                  <span className="sidebar-stat-label">Projects</span>
                </div>
                <div className="sidebar-stat">
                  <span className="sidebar-stat-value">{list.filter(p => p.status === 'ready').length}</span>
                  <span className="sidebar-stat-label">Ready</span>
                </div>
                <div className="sidebar-stat">
                  <span className="sidebar-stat-value">{list.filter(p => p.status === 'building').length}</span>
                  <span className="sidebar-stat-label">Building</span>
                </div>
              </div>
            </div>

            <div className="sidebar-section">
              <h3 className="sidebar-title">Keyboard Shortcuts</h3>
              <div className="sidebar-shortcuts">
                <div className="sidebar-shortcut">
                  <kbd>Enter</kbd>
                  <span>Send prompt</span>
                </div>
                <div className="sidebar-shortcut">
                  <kbd>Shift + Enter</kbd>
                  <span>New line</span>
                </div>
                <div className="sidebar-shortcut">
                  <kbd>⌘S / Ctrl+S</kbd>
                  <span>Save in editor</span>
                </div>
                <div className="sidebar-shortcut">
                  <kbd>Right-click</kbd>
                  <span>File actions (AI)</span>
                </div>
              </div>
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
}
