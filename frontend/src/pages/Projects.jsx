import { useEffect, useState, useRef, useCallback } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { projects as api, ai as aiApi } from '../api';
import Card from '../components/Card';
import Badge from '../components/Badge';
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

  /* Prompt state */
  const [prompt, setPrompt] = useState('');
  const [attachments, setAttachments] = useState([]); // { name, content }
  const [sending, setSending] = useState(false);
  const [status, setStatus] = useState('');
  const [error, setError] = useState('');

  const inputRef = useRef(null);
  const fileRef = useRef(null);

  const SUGGESTIONS = [
    'Retro platformer with pixel art and power-ups',
    'Top-down racing game with drifting mechanics',
    'Physics-based puzzle game with gravity switching',
    'Space shooter with procedural enemy waves',
  ];

  const load = useCallback(() => {
    setLoading(true);
    api.list()
      .then(setList)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

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

  const handleDelete = async (id, e) => {
    e.preventDefault();
    e.stopPropagation();
    if (!confirm('Delete this project?')) return;
    try {
      await api.delete(id);
      setList((prev) => prev.filter((p) => p.project_id !== id));
    } catch {}
  };

  return (
    <div className="projects-page">
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

      {/* ── Main content: projects + sidebar ── */}
      <div className="container-wide">
        <div className="projects-layout">
          {/* Left: project grid */}
          <div className="projects-main">
            <div className="projects-section-header">
              <h2 className="projects-section-title">Your Projects</h2>
              <span className="projects-count">{list.length}</span>
            </div>
            <div className="projects-grid">
              {list.map((p) => (
                <Link key={p.project_id} to={`/projects/${p.project_id}`} className="project-link">
                  <Card hover className="project-card">
                    <div className="project-card-top">
                      <h3 className="project-name">{p.name}</h3>
                      <Badge variant={STATUS_BADGE[p.status] || 'default'}>{p.status}</Badge>
                    </div>
                    {p.description && <p className="project-desc">{p.description}</p>}
                    <div className="project-card-meta">
                      <span className="project-framework">{p.framework}</span>
                      <span className="project-date">{formatDate(p.updated_at)}</span>
                    </div>
                    <button
                      className="project-delete"
                      onClick={(e) => handleDelete(p.project_id, e)}
                      title="Delete"
                    >
                      <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                        <path d="M1 1l12 12M13 1L1 13" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
                      </svg>
                    </button>
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
              </div>
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
}
