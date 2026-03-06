import { useEffect, useState, useRef, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import Editor from '@monaco-editor/react';
import { projects as projApi, ai as aiApi, getPreviewUrl } from '../api';
import './ProjectDetail.css';

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

  /* Extract the files dict from generated_code (which wraps them in .files) */
  function _extractFiles(proj) {
    const gc = proj?.generated_code;
    if (!gc) return {};
    if (gc.files && typeof gc.files === 'object') return gc.files;
    // fallback: if generated_code is already a flat file map
    const keys = Object.keys(gc);
    if (keys.some((k) => k.endsWith('.html') || k.endsWith('.js') || k.endsWith('.css'))) return gc;
    return {};
  }

  /* ── Send handler: always generates code via Gemini ── */
  const handleSend = async (e) => {
    e?.preventDefault();
    const text = chatInput.trim();
    if (!text || chatLoading) return;
    setChatLoading(true);
    setChatInput('');

    // Optimistically add user message
    setProject((prev) => ({
      ...prev,
      ai_conversation: [
        ...(prev.ai_conversation || []),
        { role: 'user', content: text },
      ],
    }));

    try {
      // Call generate — this hits Gemini, creates/updates code, AND appends to conversation
      const res = await aiApi.generate({
        project_id: project.project_id,
        prompt: text,
        framework: project.framework || 'phaser',
      });

      if (res.project) {
        setProject(res.project);
        const codeFiles = _extractFiles(res.project);
        const names = Object.keys(codeFiles);
        if (names.length > 0) setSelectedFile(names[0]);
        // Refresh preview iframe
        if (previewRef.current) {
          previewRef.current.src = getPreviewUrl(res.project.project_id) + '&t=' + Date.now();
        }
      }
    } catch (err) {
      // Fallback: try chat endpoint for a conversational reply
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

  const getLanguage = (filename) => {
    if (!filename) return 'plaintext';
    const ext = filename.split('.').pop().toLowerCase();
    const map = {
      js: 'javascript', jsx: 'javascript', ts: 'typescript', tsx: 'typescript',
      html: 'html', css: 'css', json: 'json', py: 'python', gd: 'plaintext',
      tscn: 'plaintext', tres: 'plaintext', md: 'markdown', svg: 'xml',
    };
    return map[ext] || 'plaintext';
  };

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
        </div>

        <div className="pd-messages">
          {conversation.length === 0 && (
            <div className="pd-empty-chat">
              <p className="pd-empty-title">Describe changes or ideas</p>
              <p className="pd-empty-sub">
                Every message you send generates real code via Gemini.
                The preview updates automatically.
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
            placeholder="Tell AI what to build or change..."
            rows={2}
            disabled={chatLoading}
          />
          <button
            type="submit"
            className="pd-send-btn"
            disabled={chatLoading || !chatInput.trim()}
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path d="M2.5 8h11M8.5 3l5 5-5 5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
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

          {rightPanel === 'code' && hasFiles && (
            <select
              className="pd-file-select"
              value={selectedFile || ''}
              onChange={(e) => setSelectedFile(e.target.value)}
            >
              {fileNames.map((f) => (
                <option key={f} value={f}>{f}</option>
              ))}
            </select>
          )}
        </div>

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
                beforeMount={(monaco) => {
                  monaco.editor.defineTheme('pd-black', {
                    base: 'vs-dark',
                    inherit: true,
                    rules: [
                      { token: '', foreground: 'cccccc', background: '000000' },
                      { token: 'comment', foreground: '555555' },
                      { token: 'keyword', foreground: 'ffffff', fontStyle: 'bold' },
                      { token: 'string', foreground: '999999' },
                      { token: 'number', foreground: 'bbbbbb' },
                      { token: 'type', foreground: 'dddddd' },
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
                }}
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
                <p className="pd-empty-sub">Send a message to generate code for your project.</p>
              </div>
            )
          )}
        </div>
      </div>
    </div>
  );
}
