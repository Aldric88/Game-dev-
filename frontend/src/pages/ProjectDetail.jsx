import { useEffect, useState, useRef, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import Editor from '@monaco-editor/react';
import { projects as projApi, ai as aiApi, getPreviewUrl, downloadProjectZip, godot } from '../api';
import './ProjectDetail.css';

/* ── File-type helpers ── */
const ICON_MAP = {
  html: 'H', css: 'C', js: 'J', gd: 'G', tscn: 'S',
  tres: 'R', godot: 'P', svg: 'I', md: 'M', json: 'J',
};

const FOLDER_ORDER = ['', 'scripts', 'scenes', 'assets'];

function getFileIcon(filename) {
  const ext = filename.split('.').pop().toLowerCase();
  return ICON_MAP[ext] || 'F';
}

function getFileColor(filename) {
  const ext = filename.split('.').pop().toLowerCase();
  const colors = {
    html: '#e44d26', css: '#264de4', js: '#f7df1e', gd: '#478cbf',
    tscn: '#8eef97', godot: '#478cbf', svg: '#ffb13b', md: '#888',
  };
  return colors[ext] || '#666';
}

function getLanguage(filename) {
  if (!filename) return 'plaintext';
  const ext = filename.split('.').pop().toLowerCase();
  const map = {
    js: 'javascript', jsx: 'javascript', ts: 'typescript', tsx: 'typescript',
    html: 'html', css: 'css', json: 'json', py: 'python', md: 'markdown',
    svg: 'xml', gd: 'gdscript', tscn: 'ini', tres: 'ini', godot: 'ini',
  };
  return map[ext] || 'plaintext';
}

function groupFilesByFolder(fileNames) {
  const groups = {};
  for (const f of fileNames) {
    const parts = f.split('/');
    const folder = parts.length > 1 ? parts.slice(0, -1).join('/') : '';
    if (!groups[folder]) groups[folder] = [];
    groups[folder].push(f);
  }
  const sorted = Object.entries(groups).sort(([a], [b]) => {
    const ai = FOLDER_ORDER.indexOf(a);
    const bi = FOLDER_ORDER.indexOf(b);
    if (ai !== -1 && bi !== -1) return ai - bi;
    if (ai !== -1) return -1;
    if (bi !== -1) return 1;
    return a.localeCompare(b);
  });
  return sorted;
}

/* Agent progress labels */
const AGENT_LABELS = {
  design: 'Design Agent',
  scripts: 'Script Agent',
  scenes: 'Scene Agent',
  assets: 'Asset Agent',
  assembler: 'Assembler',
};

export default function ProjectDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [project, setProject] = useState(null);
  const [loading, setLoading] = useState(true);

  // Right panel: 'preview' | 'code'
  const [rightPanel, setRightPanel] = useState('preview');
  const [selectedFile, setSelectedFile] = useState(null);

  // Chat
  const [chatInput, setChatInput] = useState('');
  const [chatLoading, setChatLoading] = useState(false);
  const [agentStatus, setAgentStatus] = useState({});
  const chatEndRef = useRef(null);
  const previewRef = useRef(null);

  const load = useCallback(() => {
    setLoading(true);
    projApi.get(id)
      .then((p) => {
        setProject(p);
        const codeFiles = _extractFiles(p);
        const names = Object.keys(codeFiles);
        if (names.length > 0 && !selectedFile) setSelectedFile(names[0]);
      })
      .catch(() => navigate('/projects'))
      .finally(() => setLoading(false));
  }, [id, navigate]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [project?.ai_conversation?.length]);

  /* Register GDScript language in Monaco */
  function registerGDScript(monaco) {
    if (!monaco.languages.getLanguages().some((l) => l.id === 'gdscript')) {
      monaco.languages.register({ id: 'gdscript' });
      monaco.languages.setMonarchTokensProvider('gdscript', {
        keywords: [
          'extends', 'class_name', 'func', 'var', 'const', 'signal', 'enum',
          'export', '@export', '@onready', 'if', 'elif', 'else', 'for', 'while',
          'match', 'return', 'pass', 'break', 'continue', 'yield', 'await',
          'true', 'false', 'null', 'self', 'super', 'and', 'or', 'not', 'in',
          'is', 'as', 'class', 'static', 'void', 'preload', 'load',
        ],
        typeKeywords: [
          'int', 'float', 'bool', 'String', 'Vector2', 'Vector3', 'Array',
          'Dictionary', 'NodePath', 'PackedScene', 'Texture2D', 'Node',
          'Node2D', 'Node3D', 'CharacterBody2D', 'RigidBody2D', 'StaticBody2D',
          'Area2D', 'Sprite2D', 'CollisionShape2D', 'AnimatedSprite2D',
          'Camera2D', 'Timer', 'AudioStreamPlayer',
        ],
        operators: [':=', '==', '!=', '<=', '>=', '+=', '-=', '*=', '/=', '->', '<', '>', '+', '-', '*', '/'],
        tokenizer: {
          root: [
            [/#.*$/, 'comment'],
            [/"""[\s\S]*?"""/, 'string'],
            [/"([^"\\]|\\.)*"/, 'string'],
            [/'([^'\\]|\\.)*'/, 'string'],
            [/\b\d+(\.\d+)?\b/, 'number'],
            [/@?\b[a-zA-Z_]\w*\b/, {
              cases: {
                '@keywords': 'keyword',
                '@typeKeywords': 'type',
                '@default': 'identifier',
              },
            }],
            [/[{}()[\]]/, '@brackets'],
            [/[;,.]/, 'delimiter'],
          ],
        },
      });
    }

    monaco.editor.defineTheme('pd-black', {
      base: 'vs-dark',
      inherit: true,
      rules: [
        { token: '', foreground: 'cccccc', background: '000000' },
        { token: 'comment', foreground: '555555', fontStyle: 'italic' },
        { token: 'keyword', foreground: 'ff7b72', fontStyle: 'bold' },
        { token: 'string', foreground: 'a5d6ff' },
        { token: 'number', foreground: 'bbbbbb' },
        { token: 'type', foreground: '79c0ff' },
        { token: 'identifier', foreground: 'cccccc' },
      ],
      colors: {
        'editor.background': '#000000',
        'editor.foreground': '#cccccc',
        'editor.lineHighlightBackground': '#0a0a0a',
        'editor.selectionBackground': '#1a1a1a',
        'editorCursor.foreground': '#ffffff',
        'editorLineNumber.foreground': '#333333',
        'editorLineNumber.activeForeground': '#666666',
        'editor.inactiveSelectionBackground': '#111111',
        'editorGutter.background': '#000000',
        'editorWidget.background': '#0a0a0a',
        'editorWidget.border': '#1a1a1a',
        'scrollbar.shadow': '#000000',
        'scrollbarSlider.background': '#111111',
        'scrollbarSlider.hoverBackground': '#1a1a1a',
        'scrollbarSlider.activeBackground': '#222222',
      },
    });
  }

  /* Extract the files dict from generated_code */
  function _extractFiles(proj) {
    const gc = proj?.generated_code;
    if (!gc) return {};
    if (gc.files && typeof gc.files === 'object') return gc.files;
    const keys = Object.keys(gc);
    if (keys.some((k) => k.endsWith('.html') || k.endsWith('.js') || k.endsWith('.css') || k.endsWith('.gd'))) return gc;
    return {};
  }

  /* Get Godot stats from generated_code */
  function _getStats(proj) {
    return proj?.generated_code?.godot_stats || null;
  }

  /* ── Send handler: multi-agent generation via Gemini ── */
  const handleSend = async (e) => {
    e?.preventDefault();
    const text = chatInput.trim();
    if (!text || chatLoading) return;
    setChatLoading(true);
    setChatInput('');
    setAgentStatus({
      design: { status: 'pending', message: 'Waiting...' },
      scripts: { status: 'pending', message: 'Waiting...' },
      scenes: { status: 'pending', message: 'Waiting...' },
      assets: { status: 'pending', message: 'Waiting...' },
      assembler: { status: 'pending', message: 'Waiting...' },
    });

    setProject((prev) => ({
      ...prev,
      ai_conversation: [
        ...(prev.ai_conversation || []),
        { role: 'user', content: text },
      ],
    }));

    // Animate agent progress while waiting
    const progressTimer = setInterval(() => {
      setAgentStatus((prev) => {
        const next = { ...prev };
        const order = ['design', 'scripts', 'scenes', 'assets', 'assembler'];
        for (const agent of order) {
          if (next[agent]?.status === 'pending') {
            next[agent] = { status: 'running', message: `${AGENT_LABELS[agent]} processing...` };
            break;
          }
          if (next[agent]?.status === 'running') {
            next[agent] = { status: 'complete', message: `${AGENT_LABELS[agent]} done` };
          }
        }
        return next;
      });
    }, 3000);

    try {
      const res = await aiApi.generate({
        project_id: project.project_id,
        prompt: text,
        framework: project.framework || 'phaser',
      });

      clearInterval(progressTimer);
      setAgentStatus({
        design: { status: 'complete', message: 'Design complete' },
        scripts: { status: 'complete', message: 'Scripts generated' },
        scenes: { status: 'complete', message: 'Scenes built' },
        assets: { status: 'complete', message: 'Assets created' },
        assembler: { status: 'complete', message: 'Game assembled' },
      });

      if (res.project) {
        setProject(res.project);
        const codeFiles = _extractFiles(res.project);
        const names = Object.keys(codeFiles);
        if (names.length > 0) setSelectedFile(names[0]);
        if (previewRef.current) {
          previewRef.current.src = getPreviewUrl(res.project.project_id) + '&t=' + Date.now();
        }
      }

      setTimeout(() => setAgentStatus({}), 4000);
    } catch (err) {
      clearInterval(progressTimer);
      setAgentStatus({});
      try {
        const chatRes = await aiApi.chat({ project_id: project.project_id, message: text });
        if (chatRes.project) setProject(chatRes.project);
      } catch {
        setProject((prev) => ({
          ...prev,
          ai_conversation: [
            ...(prev.ai_conversation || []),
            { role: 'system', content: `Error: ${err.message}` },
          ],
        }));
      }
    } finally {
      setChatLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleDelete = async () => {
    if (!confirm('Permanently delete this project?')) return;
    try {
      await projApi.delete(project.project_id);
      navigate('/projects');
    } catch {}
  };

  const handleDownload = async () => {
    try {
      const blob = await downloadProjectZip(project.project_id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${project.name || 'project'}.zip`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      alert(err.message);
    }
  };

  const handleOpenFolder = async () => {
    try {
      const res = await godot.openFolder(project.project_id);
      if (!res.success) alert(res.error);
    } catch (err) {
      alert(err.message);
    }
  };

  const handleRunGodot = async () => {
    try {
      const res = await godot.runGodot(project.project_id);
      if (!res.success) alert(res.error);
    } catch (err) {
      alert(err.message);
    }
  };

  const handleReloadPreview = () => {
    if (previewRef.current) {
      previewRef.current.src = getPreviewUrl(project.project_id) + '&t=' + Date.now();
    }
  };

  if (loading || !project) {
    return (
      <div className="pd-loading">
        <div className="pd-spinner" />
      </div>
    );
  }

  const conversation = project.ai_conversation || [];
  const files = _extractFiles(project);
  const fileNames = Object.keys(files);
  const hasFiles = fileNames.length > 0;
  const stats = _getStats(project);
  const fileGroups = groupFilesByFolder(fileNames);
  const hasAgentActivity = Object.keys(agentStatus).length > 0;

  return (
    <div className="pd-root">
      {/* Left Panel: Chat */}
      <div className="pd-left">
        <div className="pd-left-header">
          <div className="pd-project-info">
            <button className="pd-back" onClick={() => navigate('/projects')}>
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <path d="M10 12L6 8l4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </button>
            <span className="pd-project-name">{project.name}</span>
            <span className="pd-project-status">{project.status}</span>
          </div>
          <button className="pd-delete-btn" onClick={handleDelete} title="Delete project">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <path d="M1.75 3.5h10.5M5.25 3.5V2.333c0-.322.261-.583.583-.583h2.334c.322 0 .583.261.583.583V3.5m1.75 0v8.167c0 .322-.261.583-.583.583H4.083a.583.583 0 01-.583-.583V3.5h7" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </button>
          {hasFiles && (
            <button className="pd-download-btn" onClick={handleDownload} title="Download project as ZIP">
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <path d="M7 1.75v7m0 0l-2.5-2.5M7 8.75l2.5-2.5M2.333 11.083h9.334" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </button>
          )}
          {hasFiles && (
            <button className="pd-folder-btn" onClick={handleOpenFolder} title="Open project folder">
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <path d="M1.75 4.083h4.667L7.583 5.25H12.25v6.417H1.75V4.083z" stroke="currentColor" strokeWidth="1.2" fill="none" strokeLinecap="round" strokeLinejoin="round"/>
                <path d="M1.75 4.083V2.333h3.5l1.167 1.75" stroke="currentColor" strokeWidth="1.2" fill="none" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </button>
          )}
          {hasFiles && (
            <button className="pd-godot-btn" onClick={handleRunGodot} title="Open in Godot Editor">
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <circle cx="7" cy="7" r="5.25" stroke="currentColor" strokeWidth="1.2"/>
                <path d="M5.5 5.5L9 7l-3.5 1.5V5.5z" fill="currentColor"/>
              </svg>
            </button>
          )}
        </div>

        {/* Agent Progress Panel */}
        {hasAgentActivity && (
          <div className="pd-agent-panel">
            {Object.entries(agentStatus).map(([key, val]) => (
              <div key={key} className={`pd-agent-row pd-agent-${val.status}`}>
                <div className="pd-agent-indicator">
                  {val.status === 'running' && <div className="pd-agent-spinner" />}
                  {val.status === 'complete' && (
                    <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                      <path d="M2 6l3 3 5-5" stroke="#4ade80" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                    </svg>
                  )}
                  {val.status === 'pending' && <div className="pd-agent-dot" />}
                </div>
                <span className="pd-agent-label">{AGENT_LABELS[key]}</span>
                <span className="pd-agent-msg">{val.message}</span>
              </div>
            ))}
          </div>
        )}

        {/* Stats bar */}
        {stats && !hasAgentActivity && (
          <div className="pd-stats-bar">
            <span className="pd-stat">{stats.entities || 0} entities</span>
            <span className="pd-stat-sep" />
            <span className="pd-stat">{stats.scripts || 0} scripts</span>
            <span className="pd-stat-sep" />
            <span className="pd-stat">{stats.scenes || 0} scenes</span>
            <span className="pd-stat-sep" />
            <span className="pd-stat">{stats.assets || 0} assets</span>
          </div>
        )}

        <div className="pd-messages">
          {conversation.length === 0 && !hasAgentActivity && (
            <div className="pd-empty-chat">
              <p className="pd-empty-title">Describe your game</p>
              <p className="pd-empty-sub">
                Every message triggers a multi-agent pipeline:
                Design, Script, Scene, and Asset agents all run via Gemini
                to generate a complete game with Godot project files.
              </p>
            </div>
          )}
          {conversation.map((msg, i) => (
            <div key={i} className={`pd-msg pd-msg-${msg.role}`}>
              <div className="pd-msg-role">
                {msg.role === 'user' ? 'You' : msg.role === 'system' ? 'System' : 'AI'}
              </div>
              <div className="pd-msg-content">{msg.content}</div>
            </div>
          ))}
          {chatLoading && (
            <div className="pd-msg pd-msg-assistant">
              <div className="pd-msg-role">AI</div>
              <div className="pd-msg-content pd-typing">
                <span /><span /><span />
              </div>
            </div>
          )}
          <div ref={chatEndRef} />
        </div>

        <form className="pd-input-area" onSubmit={handleSend}>
          <textarea
            className="pd-input"
            value={chatInput}
            onChange={(e) => setChatInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Describe your game or changes..."
            rows={2}
            disabled={chatLoading}
          />
          <button
            type="submit"
            className="pd-send-btn"
            disabled={chatLoading || !chatInput.trim()}
          >
            {chatLoading ? (
              <div className="pd-send-spinner" />
            ) : (
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <path d="M2.5 8h11M8.5 3l5 5-5 5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            )}
          </button>
        </form>
      </div>

      {/* Right Panel: Preview / Code */}
      <div className="pd-right">
        <div className="pd-right-header">
          <div className="pd-right-tabs">
            <button
              className={`pd-right-tab ${rightPanel === 'preview' ? 'active' : ''}`}
              onClick={() => setRightPanel('preview')}
            >
              Preview
            </button>
            <button
              className={`pd-right-tab ${rightPanel === 'code' ? 'active' : ''}`}
              onClick={() => setRightPanel('code')}
            >
              Code
            </button>
          </div>

          {hasFiles && (
            <div className="pd-right-actions">
              {rightPanel === 'preview' && (
                <button className="pd-reload-btn" onClick={handleReloadPreview} title="Reload preview">
                  <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                    <path d="M10 6a4 4 0 11-1.17-2.83" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/>
                    <path d="M10 1.5v2.5H7.5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                </button>
              )}
              <span className="pd-file-count">{fileNames.length} files</span>
            </div>
          )}
        </div>

        <div className="pd-right-body">
          {rightPanel === 'code' && hasFiles && (
            <div className="pd-file-tree">
              {fileGroups.map(([folder, groupFiles]) => (
                <div key={folder} className="pd-file-group">
                  {folder && (
                    <div className="pd-folder-name">
                      <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                        <path d="M1 3h4l1.5 1.5H11v6H1V3z" stroke="#666" strokeWidth="1" fill="none"/>
                      </svg>
                      {folder}/
                    </div>
                  )}
                  {groupFiles.map((f) => {
                    const displayName = folder ? f.split('/').pop() : f;
                    return (
                      <button
                        key={f}
                        className={`pd-file-item ${selectedFile === f ? 'active' : ''}`}
                        onClick={() => setSelectedFile(f)}
                        style={{ paddingLeft: folder ? 24 : 8 }}
                      >
                        <span className="pd-file-icon" style={{ color: getFileColor(f) }}>
                          {getFileIcon(f)}
                        </span>
                        {displayName}
                      </button>
                    );
                  })}
                </div>
              ))}
            </div>
          )}

          <div className="pd-right-content">
            {rightPanel === 'preview' ? (
              hasFiles ? (
                <iframe
                  ref={previewRef}
                  className="pd-preview-frame"
                  src={getPreviewUrl(project.project_id)}
                  title="Game Preview"
                  sandbox="allow-scripts allow-same-origin allow-forms allow-popups"
                />
              ) : (
                <div className="pd-right-empty">
                  <p className="pd-empty-title">No preview available</p>
                  <p className="pd-empty-sub">Send a message to generate your game.</p>
                </div>
              )
            ) : (
              hasFiles && selectedFile ? (
                <Editor
                  height="100%"
                  language={getLanguage(selectedFile)}
                  value={files[selectedFile] || ''}
                  theme="pd-black"
                  beforeMount={registerGDScript}
                  options={{
                    readOnly: true,
                    minimap: { enabled: false },
                    fontSize: 13,
                    fontFamily: "'SF Mono', SFMono-Regular, ui-monospace, 'Cascadia Code', Menlo, Consolas, monospace",
                    lineHeight: 20,
                    padding: { top: 16, bottom: 16 },
                    scrollBeyondLastLine: false,
                    renderLineHighlight: 'line',
                    wordWrap: 'on',
                    smoothScrolling: true,
                    cursorBlinking: 'smooth',
                  }}
                />
              ) : (
                <div className="pd-right-empty">
                  <p className="pd-empty-title">No code yet</p>
                  <p className="pd-empty-sub">Send a message to generate Godot project files and a playable game.</p>
                </div>
              )
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
