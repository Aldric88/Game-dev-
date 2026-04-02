import { useEffect, useState, useRef, useCallback, useLayoutEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import Editor from '@monaco-editor/react';
import { projects as projApi, ai as aiApi, getPreviewUrl, getPublicPlayUrl, downloadProjectZip, godot, streamGenerate, streamChat } from '../api';
import { useAuth } from '../AuthContext';
import ErrorBoundary from '../components/ErrorBoundary';
import Modal from '../components/Modal';
import './ProjectDetail.css';

/* ── File-type helpers ── */
const ICON_MAP = {
  html: 'H', css: 'C', js: 'J', gd: 'G', tscn: 'S',
  tres: 'R', godot: 'P', svg: 'I', md: 'M', json: 'J',
};
const FOLDER_ORDER = ['', 'scripts', 'scenes', 'assets'];

function getFileIcon(filename) {
  return ICON_MAP[filename.split('.').pop().toLowerCase()] || 'F';
}
function getFileColor(filename) {
  const colors = { html:'#e44d26',css:'#264de4',js:'#f7df1e',gd:'#478cbf',tscn:'#8eef97',godot:'#478cbf',svg:'#ffb13b',md:'#888' };
  return colors[filename.split('.').pop().toLowerCase()] || '#555';
}
function getLanguage(filename) {
  if (!filename) return 'plaintext';
  const map = { js:'javascript',jsx:'javascript',ts:'typescript',tsx:'typescript',html:'html',css:'css',json:'json',py:'python',md:'markdown',svg:'xml',gd:'gdscript',tscn:'ini',tres:'ini',godot:'ini' };
  return map[filename.split('.').pop().toLowerCase()] || 'plaintext';
}
function groupFilesByFolder(fileNames) {
  const groups = {};
  for (const f of fileNames) {
    const parts = f.split('/');
    const folder = parts.length > 1 ? parts.slice(0, -1).join('/') : '';
    if (!groups[folder]) groups[folder] = [];
    groups[folder].push(f);
  }
  return Object.entries(groups).sort(([a], [b]) => {
    const ai = FOLDER_ORDER.indexOf(a), bi = FOLDER_ORDER.indexOf(b);
    if (ai !== -1 && bi !== -1) return ai - bi;
    if (ai !== -1) return -1; if (bi !== -1) return 1;
    return a.localeCompare(b);
  });
}

const AGENT_LABELS = { design:'Design',scripts:'Scripts',scenes:'Scenes',assets:'Assets',assembler:'Assemble' };

function _extractFiles(proj) {
  const gc = proj?.generated_code;
  if (!gc) return {};
  if (gc.files && typeof gc.files === 'object') return gc.files;
  const keys = Object.keys(gc);
  if (keys.some(k => k.endsWith('.html')||k.endsWith('.js')||k.endsWith('.gd'))) return gc;
  return {};
}
function _getStats(proj) { return proj?.generated_code?.godot_stats || null; }

/* ── Read all files recursively from a FileSystemDirectoryEntry ── */
async function readDirectoryEntries(dirEntry, prefix = '') {
  return new Promise(resolve => {
    const reader = dirEntry.createReader();
    const allEntries = [];
    const readBatch = () => {
      reader.readEntries(entries => {
        if (!entries.length) return resolve(allEntries);
        allEntries.push(...entries);
        readBatch();
      });
    };
    readBatch();
  }).then(async entries => {
    const files = {};
    await Promise.all(entries.map(async entry => {
      const path = prefix ? `${prefix}/${entry.name}` : entry.name;
      if (entry.isFile) {
        const file = await new Promise(r => entry.file(r));
        const text = await file.text().catch(() => null);
        if (text !== null) files[path] = text;
      } else if (entry.isDirectory) {
        const sub = await readDirectoryEntries(entry, path);
        Object.assign(files, sub);
      }
    }));
    return files;
  });
}

export default function ProjectDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [project, setProject] = useState(null);
  const [loading, setLoading] = useState(true);
  const [toggling, setToggling] = useState(false);

  const [rightPanel, setRightPanel] = useState('preview');
  const [selectedFile, setSelectedFile] = useState(null);

  /* Local edits to files (pending save) */
  const [editedFiles, setEditedFiles] = useState({});
  const [isDirty, setIsDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState('');

  /* Import codebase */
  const [importing, setImporting] = useState(false);
  const [importMsg, setImportMsg] = useState('');
  const [isDragging, setIsDragging] = useState(false);
  const dropRef = useRef(null);
  const fileInputRef = useRef(null);
  const folderInputRef = useRef(null);

  /* New file creation */
  const [isCreatingFile, setIsCreatingFile] = useState(false);
  const [newFileName, setNewFileName] = useState('');
  const newFileInputRef = useRef(null);

  /* File tree context menu */
  const [ctxMenu, setCtxMenu] = useState(null); // { file, x, y }
  const [renaming, setRenaming] = useState(null); // filename being renamed
  const [renameVal, setRenameVal] = useState('');
  const renameInputRef = useRef(null);

  /* Console panel */
  const [consoleLogs, setConsoleLogs] = useState([]);

  /* Diff view */
  const [diffFiles, setDiffFiles] = useState(null); // { before, after } file maps

  /* Rate limit / credits toast */
  const [toast, setToast] = useState(null); // { msg, type, countdown }
  const toastTimerRef = useRef(null);

  /* Session expiry modal */
  const [sessionExpired, setSessionExpired] = useState(false);

  /* AI file action (explain/fix) */
  const [fileActionLoading, setFileActionLoading] = useState(false);

  /* Delete file confirm */
  const [confirmDeleteFile, setConfirmDeleteFile] = useState(null);

  /* Multi-tab editor */
  const [openTabs, setOpenTabs] = useState([]);

  /* Version history */
  const [showVersions, setShowVersions] = useState(false);

  /* Ctrl+P file switcher */
  const [showSwitcher, setShowSwitcher] = useState(false);
  const [switcherQuery, setSwitcherQuery] = useState('');
  const switcherRef = useRef(null);

  /* Search across files (Ctrl+Shift+F) */
  const [showSearch, setShowSearch] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const searchRef = useRef(null);

  /* Image/asset upload */
  const imageInputRef = useRef(null);

  /* Resizable panels */
  const [leftWidth, setLeftWidth] = useState(380);
  const isResizing = useRef(false);
  const startX = useRef(0);
  const startWidth = useRef(0);
  const rootRef = useRef(null);

  const onResizeStart = useCallback((e) => {
    isResizing.current = true;
    startX.current = e.clientX ?? e.touches?.[0]?.clientX ?? 0;
    startWidth.current = leftWidth;
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  }, [leftWidth]);

  useLayoutEffect(() => {
    const getX = (e) => e.clientX ?? e.touches?.[0]?.clientX ?? 0;
    const onMove = (e) => {
      if (!isResizing.current) return;
      const rootW = rootRef.current?.offsetWidth || window.innerWidth;
      const next = Math.min(Math.max(startWidth.current + (getX(e) - startX.current), 240), rootW - 360);
      setLeftWidth(next);
    };
    const onUp = () => {
      isResizing.current = false;
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    window.addEventListener('touchmove', onMove, { passive: true });
    window.addEventListener('touchend', onUp);
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
      window.removeEventListener('touchmove', onMove);
      window.removeEventListener('touchend', onUp);
    };
  }, []);

  /* Chat */
  const [chatInput, setChatInput] = useState('');
  const [chatLoading, setChatLoading] = useState(false);
  const [agentStatus, setAgentStatus] = useState({});
  const chatEndRef = useRef(null);
  const previewRef = useRef(null);

  const load = useCallback(() => {
    setLoading(true);
    projApi.get(id)
      .then(p => {
        setProject(p);
        setEditedFiles({});
        setIsDirty(false);
        const names = Object.keys(_extractFiles(p));
        if (names.length > 0) {
          const first = names[0];
          setSelectedFile(first);
          setOpenTabs([first]);
        }
      })
      .catch(() => navigate('/projects'))
      .finally(() => setLoading(false));
  }, [id, navigate]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [project?.ai_conversation?.length]);

  /* Monaco GDScript + theme */
  function registerGDScript(monaco) {
    if (!monaco.languages.getLanguages().some(l => l.id === 'gdscript')) {
      monaco.languages.register({ id: 'gdscript' });
      monaco.languages.setMonarchTokensProvider('gdscript', {
        keywords: ['extends','class_name','func','var','const','signal','enum','export','@export','@onready','if','elif','else','for','while','match','return','pass','break','continue','yield','await','true','false','null','self','super','and','or','not','in','is','as','class','static','void','preload','load'],
        typeKeywords: ['int','float','bool','String','Vector2','Vector3','Array','Dictionary','NodePath','PackedScene','Texture2D','Node','Node2D','Node3D','CharacterBody2D','RigidBody2D','StaticBody2D','Area2D','Sprite2D','CollisionShape2D','AnimatedSprite2D','Camera2D','Timer','AudioStreamPlayer'],
        operators: [':=','==','!=','<=','>=','+=','-=','*=','/=','->','<','>','+','-','*','/'],
        tokenizer: {
          root: [
            [/#.*$/, 'comment'], [/"""[\s\S]*?"""/, 'string'],
            [/"([^"\\]|\\.)*"/, 'string'], [/'([^'\\]|\\.)*'/, 'string'],
            [/\b\d+(\.\d+)?\b/, 'number'],
            [/@?\b[a-zA-Z_]\w*\b/, { cases: { '@keywords':'keyword','@typeKeywords':'type','@default':'identifier' } }],
            [/[{}()[\]]/, '@brackets'], [/[;,.]/, 'delimiter'],
          ],
        },
      });
    }
    monaco.editor.defineTheme('pd-black', {
      base: 'vs-dark', inherit: true,
      rules: [
        { token:'', foreground:'cccccc', background:'000000' },
        { token:'comment', foreground:'555555', fontStyle:'italic' },
        { token:'keyword', foreground:'ff7b72', fontStyle:'bold' },
        { token:'string', foreground:'a5d6ff' },
        { token:'number', foreground:'bbbbbb' },
        { token:'type', foreground:'79c0ff' },
        { token:'identifier', foreground:'cccccc' },
      ],
      colors: {
        'editor.background':'#000000', 'editor.foreground':'#cccccc',
        'editor.lineHighlightBackground':'#0a0a0a', 'editor.selectionBackground':'#1a1a1a',
        'editorCursor.foreground':'#ffffff', 'editorLineNumber.foreground':'#333333',
        'editorLineNumber.activeForeground':'#666666', 'editor.inactiveSelectionBackground':'#111111',
        'editorGutter.background':'#000000', 'editorWidget.background':'#0a0a0a',
        'editorWidget.border':'#1a1a1a', 'scrollbarSlider.background':'#111111',
        'scrollbarSlider.hoverBackground':'#1a1a1a', 'scrollbarSlider.activeBackground':'#222222',
      },
    });
  }

  /* ── Save edited files ── */
  const handleSave = async () => {
    if (!isDirty || saving) return;
    setSaving(true);
    setSaveMsg('');
    try {
      await aiApi.saveCode(project.project_id, editedFiles);
      setSaveMsg('saved');
      setIsDirty(false);
      // Merge edits into project state
      setProject(prev => {
        const gc = _extractFiles(prev);
        const merged = { ...gc, ...editedFiles };
        return { ...prev, generated_code: prev.generated_code?.files ? { ...prev.generated_code, files: merged } : merged };
      });
      // Hot-reload preview
      if (previewRef.current) previewRef.current.src = getPreviewUrl(project.project_id) + '&t=' + Date.now();
      setTimeout(() => setSaveMsg(''), 2000);
    } catch {
      setSaveMsg('error');
      setTimeout(() => setSaveMsg(''), 3000);
    } finally {
      setSaving(false);
    }
  };

  const handleEditorChange = (value) => {
    if (!selectedFile) return;
    setEditedFiles(prev => ({ ...prev, [selectedFile]: value }));
    setIsDirty(true);
  };

  /* ── Import codebase from files/folder ── */
  const processImportedFiles = async (filesMap) => {
    if (!Object.keys(filesMap).length) return;
    setImporting(true);
    setImportMsg(`Importing ${Object.keys(filesMap).length} files…`);
    try {
      const res = await aiApi.importFiles(project.project_id, { files: filesMap, merge: true });
      if (res.project) {
        setProject(res.project);
        setEditedFiles({});
        setIsDirty(false);
        const names = Object.keys(_extractFiles(res.project));
        if (names.length > 0) { setSelectedFile(names[0]); setRightPanel('code'); }
      }
      setImportMsg(`${Object.keys(filesMap).length} files imported`);
      setTimeout(() => setImportMsg(''), 3000);
    } catch (err) {
      setImportMsg(`Import failed: ${err.message}`);
      setTimeout(() => setImportMsg(''), 4000);
    } finally {
      setImporting(false);
    }
  };

  const handleFileInputChange = async (e) => {
    const rawFiles = Array.from(e.target.files || []);
    const filesMap = {};
    await Promise.all(rawFiles.map(async f => {
      const text = await f.text().catch(() => null);
      if (text !== null) filesMap[f.webkitRelativePath || f.name] = text;
    }));
    await processImportedFiles(filesMap);
    e.target.value = '';
  };

  /* ── Drag and drop ── */
  const handleDragOver = (e) => { e.preventDefault(); setIsDragging(true); };
  const handleDragLeave = (e) => { if (!dropRef.current?.contains(e.relatedTarget)) setIsDragging(false); };
  const handleDrop = async (e) => {
    e.preventDefault();
    setIsDragging(false);
    const items = Array.from(e.dataTransfer.items || []);
    const filesMap = {};
    await Promise.all(items.map(async item => {
      const entry = item.webkitGetAsEntry?.();
      if (!entry) return;
      if (entry.isFile) {
        const file = await new Promise(r => entry.file(r));
        const text = await file.text().catch(() => null);
        if (text !== null) filesMap[entry.name] = text;
      } else if (entry.isDirectory) {
        const sub = await readDirectoryEntries(entry, entry.name);
        Object.assign(filesMap, sub);
      }
    }));
    await processImportedFiles(filesMap);
  };

  /* ── Chat / generate ── */
  const handleSend = async (e) => {
    e?.preventDefault();
    const text = chatInput.trim();
    if (!text || chatLoading) return;
    setChatLoading(true);
    setChatInput('');

    // Optimistically add the user message to the conversation
    setProject(prev => ({ ...prev, ai_conversation: [...(prev.ai_conversation||[]), { role:'user', content:text }] }));

    const projectHasFiles = Object.keys(_extractFiles(project)).length > 0;

    if (projectHasFiles) {
      // ── Chat mode: targeted modifications to existing project ──────────
      let aiReply = '';
      try {
        await streamChat(
          { project_id: project.project_id, message: text },
          {
            onChunk: (chunk) => {
              aiReply += chunk;
              setProject(prev => {
                const conv = [...(prev.ai_conversation || [])];
                const last = conv[conv.length - 1];
                if (last?.role === 'assistant' && last._streaming) {
                  conv[conv.length - 1] = { ...last, content: aiReply };
                } else {
                  conv.push({ role: 'assistant', content: aiReply, _streaming: true });
                }
                return { ...prev, ai_conversation: conv };
              });
            },
            onDone: (updatedProject, filesChanged) => {
              if (updatedProject) {
                setProject(updatedProject);
                if (filesChanged?.length > 0 && previewRef.current) {
                  previewRef.current.src = getPreviewUrl(updatedProject.project_id) + '&t=' + Date.now();
                }
              }
              setChatLoading(false);
            },
            onError: (err) => {
              showToast(err.message || 'Chat failed');
              setChatLoading(false);
            },
          }
        );
      } catch (err) {
        if (err.status === 429) showToast(err.message, 'rate', err.retryAfter);
        else if (err.status === 402) showToast(err.message, 'credits');
        else if (err.message?.includes('Session expired')) setSessionExpired(true);
        else {
          // Last resort: non-streaming chat fallback
          try {
            const chatRes = await aiApi.chat({ project_id: project.project_id, message: text });
            if (chatRes.project) setProject(chatRes.project);
          } catch {
            setProject(prev => ({ ...prev, ai_conversation: [...(prev.ai_conversation||[]), { role:'system', content:`Error: ${err.message}` }] }));
          }
        }
        setChatLoading(false);
      }
    } else {
      // ── Generate mode: create new game from prompt ──────────────────────
      setAgentStatus({ design:{status:'pending'}, scripts:{status:'pending'}, scenes:{status:'pending'}, assets:{status:'pending'}, assembler:{status:'pending'} });

      const timer = setInterval(() => {
        setAgentStatus(prev => {
          const next = { ...prev };
          const order = ['design','scripts','scenes','assets','assembler'];
          for (const a of order) {
            if (next[a]?.status === 'pending') { next[a] = { status:'running' }; break; }
            if (next[a]?.status === 'running')  { next[a] = { status:'complete' }; }
          }
          return next;
        });
      }, 2800);

      const beforeFiles = { ..._extractFiles(project) };
      try {
        await streamGenerate(
          { project_id: project.project_id, prompt: text, framework: project.framework || 'phaser' },
          {
            onAgent: ({ agent, status }) => {
              clearInterval(timer);
              setAgentStatus(prev => ({ ...prev, [agent]: { status } }));
            },
            onDone: (updatedProject) => {
              if (!updatedProject) return;
              const afterFiles = _extractFiles(updatedProject);
              const changed = Object.keys(afterFiles).filter(f => afterFiles[f] !== beforeFiles[f]);
              if (changed.length > 0) setDiffFiles({ before: beforeFiles, after: afterFiles, changed });
              setProject(updatedProject);
              setEditedFiles({});
              setIsDirty(false);
              const names = Object.keys(afterFiles);
              if (names.length > 0) { openTab(names[0]); }
              if (previewRef.current) previewRef.current.src = getPreviewUrl(updatedProject.project_id) + '&t=' + Date.now();
              setTimeout(() => setAgentStatus({}), 2000);
              setChatLoading(false);
            },
            onError: (err) => {
              clearInterval(timer);
              setAgentStatus({});
              if (err.status === 429) showToast(err.message, 'rate', err.retryAfter);
              else if (err.status === 402) showToast(err.message, 'credits');
              else showToast(err.message);
              setChatLoading(false);
            },
          }
        );
      } catch (err) {
        clearInterval(timer);
        setAgentStatus({});
        if (err.status === 429) { showToast(err.message, 'rate', err.retryAfter); setChatLoading(false); return; }
        if (err.status === 402) { showToast(err.message, 'credits'); setChatLoading(false); return; }
        if (err.message?.includes('Session expired')) { setSessionExpired(true); setChatLoading(false); return; }
        // Fall back to regular generate
        try {
          const res = await aiApi.generate({ project_id: project.project_id, prompt: text, framework: project.framework || 'phaser' });
          if (res.project) {
            setProject(res.project);
            const names = Object.keys(_extractFiles(res.project));
            if (names.length > 0) openTab(names[0]);
            if (previewRef.current) previewRef.current.src = getPreviewUrl(res.project.project_id) + '&t=' + Date.now();
          }
        } catch {
          setProject(prev => ({ ...prev, ai_conversation: [...(prev.ai_conversation||[]), { role:'system', content:`Error: ${err.message}` }] }));
        } finally {
          setChatLoading(false);
        }
      }
    }
  };

  /* ── Toast helper ── */
  const showToast = useCallback((msg, type = 'error', countdown = 0) => {
    if (toastTimerRef.current) clearInterval(toastTimerRef.current);
    setToast({ msg, type, countdown });
    if (countdown > 0) {
      let c = countdown;
      toastTimerRef.current = setInterval(() => {
        c -= 1;
        if (c <= 0) { clearInterval(toastTimerRef.current); setToast(null); }
        else setToast(t => t ? { ...t, countdown: c } : null);
      }, 1000);
    } else {
      toastTimerRef.current = setTimeout(() => setToast(null), 4000);
    }
  }, []);

  /* ── Session expiry listener ── */
  useEffect(() => {
    const onLogout = () => setSessionExpired(true);
    window.addEventListener('auth:logout', onLogout);
    return () => window.removeEventListener('auth:logout', onLogout);
  }, []);

  /* ── Multi-tab: open / close tabs ── */
  const openTab = useCallback((filename) => {
    setOpenTabs(prev => prev.includes(filename) ? prev : [...prev, filename]);
    setSelectedFile(filename);
    setRightPanel('code');
  }, []);

  const closeTab = useCallback((filename, e) => {
    e?.preventDefault();
    e?.stopPropagation();
    setOpenTabs(prev => {
      const next = prev.filter(t => t !== filename);
      if (selectedFile === filename) setSelectedFile(next[next.length - 1] || null);
      return next;
    });
  }, [selectedFile]);

  /* ── Ctrl+P switcher + Ctrl+Shift+F search keyboard shortcuts ── */
  useEffect(() => {
    const onKey = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'p') {
        e.preventDefault();
        setSwitcherQuery('');
        setShowSwitcher(true);
        setTimeout(() => switcherRef.current?.focus(), 30);
      }
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'F') {
        e.preventDefault();
        setSearchQuery('');
        setShowSearch(true);
        setTimeout(() => searchRef.current?.focus(), 30);
      }
      if (e.key === 'Escape') {
        setShowSwitcher(false);
        setShowSearch(false);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  /* ── Image/asset upload ── */
  const handleImageUpload = async (e) => {
    const rawFiles = Array.from(e.target.files || []);
    const added = {};
    await Promise.all(rawFiles.map(f => new Promise(resolve => {
      const reader = new FileReader();
      reader.onload = () => { added[f.name] = reader.result; resolve(); };
      reader.readAsDataURL(f);
    })));
    if (Object.keys(added).length) {
      setEditedFiles(prev => ({ ...prev, ...added }));
      setIsDirty(true);
      const firstName = Object.keys(added)[0];
      openTab(firstName);
    }
    e.target.value = '';
  };

  /* ── Ctrl+S to save ── */
  useEffect(() => {
    const onKey = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        e.preventDefault();
        if (isDirty && !saving) handleSave();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [isDirty, saving]);

  /* ── Console: capture messages from preview iframe ── */
  useEffect(() => {
    const onMsg = (e) => {
      if (e.data?.type === 'console') {
        setConsoleLogs(prev => [...prev.slice(-199), { level: e.data.level || 'log', text: String(e.data.args?.join(' ') ?? e.data.msg ?? ''), ts: Date.now() }]);
      }
      if (e.data?.type === 'error') {
        setConsoleLogs(prev => [...prev.slice(-199), { level: 'error', text: e.data.message || 'Runtime error', ts: Date.now() }]);
      }
    };
    window.addEventListener('message', onMsg);
    return () => window.removeEventListener('message', onMsg);
  }, []);

  /* ── Close context menu on outside click ── */
  useEffect(() => {
    if (!ctxMenu) return;
    const close = () => setCtxMenu(null);
    window.addEventListener('click', close);
    return () => window.removeEventListener('click', close);
  }, [ctxMenu]);

  /* ── File context menu ── */
  const handleFileContextMenu = (e, filename) => {
    e.preventDefault();
    e.stopPropagation();
    setCtxMenu({ file: filename, x: e.clientX, y: e.clientY });
  };

  /* ── Rename file ── */
  const handleStartRename = (filename) => {
    setCtxMenu(null);
    setRenaming(filename);
    setRenameVal(filename);
    setTimeout(() => renameInputRef.current?.focus(), 40);
  };

  const handleRenameSubmit = () => {
    const newName = renameVal.trim();
    if (!newName || newName === renaming) { setRenaming(null); return; }
    setEditedFiles(prev => {
      const next = { ...prev };
      const content = next[renaming] ?? files[renaming] ?? '';
      next[newName] = content;
      delete next[renaming];
      return next;
    });
    // Mark original as deleted (empty sentinel to be overwritten) and new as dirty
    setProject(prev => {
      const gc = _extractFiles(prev);
      const updated = { ...gc };
      delete updated[renaming];
      updated[newName] = gc[renaming] || '';
      if (prev.generated_code?.files) return { ...prev, generated_code: { ...prev.generated_code, files: updated } };
      return { ...prev, generated_code: updated };
    });
    if (selectedFile === renaming) setSelectedFile(newName);
    setIsDirty(true);
    setRenaming(null);
  };

  /* ── Delete file ── */
  const handleDeleteFile = (filename) => {
    setCtxMenu(null);
    setConfirmDeleteFile(filename);
  };

  const handleDeleteFileConfirm = () => {
    const filename = confirmDeleteFile;
    setConfirmDeleteFile(null);
    setEditedFiles(prev => { const n = { ...prev }; delete n[filename]; return n; });
    setProject(prev => {
      const gc = _extractFiles(prev);
      const updated = { ...gc };
      delete updated[filename];
      if (prev.generated_code?.files) return { ...prev, generated_code: { ...prev.generated_code, files: updated } };
      return { ...prev, generated_code: updated };
    });
    if (selectedFile === filename) setSelectedFile(Object.keys(files).find(f => f !== filename) || null);
    setIsDirty(true);
  };

  /* ── AI file action (explain / fix / improve) ── */
  const handleFileAction = async (action) => {
    setCtxMenu(null);
    if (!selectedFile && !ctxMenu?.file) return;
    const filename = ctxMenu?.file || selectedFile;
    const content = files[filename] || '';
    setFileActionLoading(true);
    setRightPanel('code');
    try {
      const res = await aiApi.fileAction({ project_id: project.project_id, filename, content, action });
      const reply = res.reply || '';
      if (action === 'fix' && res.updated_content) {
        setEditedFiles(prev => ({ ...prev, [filename]: res.updated_content }));
        setIsDirty(true);
      }
      setProject(prev => ({ ...prev, ai_conversation: [...(prev.ai_conversation || []), { role: 'system', content: `[${action} → ${filename}] ${reply}` }] }));
    } catch (err) {
      if (err.status === 429) showToast(err.message, 'rate', err.retryAfter);
      else if (err.status === 402) showToast(err.message, 'credits');
      else showToast(err.message);
    } finally {
      setFileActionLoading(false);
    }
  };

  /* ── New file creation ── */
  const handleCreateFile = () => {
    setIsCreatingFile(true);
    setNewFileName('');
    setRightPanel('code');
    setTimeout(() => newFileInputRef.current?.focus(), 50);
  };

  const handleNewFileSubmit = (e) => {
    e?.preventDefault();
    const name = newFileName.trim().replace(/^\/+/, '');
    if (!name) { setIsCreatingFile(false); return; }
    setEditedFiles(prev => ({ ...prev, [name]: '' }));
    setIsDirty(true);
    setSelectedFile(name);
    setIsCreatingFile(false);
    setNewFileName('');
  };

  const handleNewFileKeyDown = (e) => {
    if (e.key === 'Enter') { e.preventDefault(); handleNewFileSubmit(); }
    if (e.key === 'Escape') { setIsCreatingFile(false); setNewFileName(''); }
  };

  const handleKeyDown = (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); } };
  const [shareCopied, setShareCopied] = useState(false);
  const handleShare = () => {
    const url = window.location.origin + `/play/${project.project_id}`;
    navigator.clipboard.writeText(url).then(() => { setShareCopied(true); setTimeout(() => setShareCopied(false), 2000); });
  };
  const [confirmDeleteProject, setConfirmDeleteProject] = useState(false);
  const handleToggleVisibility = async () => {
    if (toggling) return;
    setToggling(true);
    try {
      const updated = await projApi.toggleVisibility(project.project_id);
      setProject(updated);
    } catch (err) {
      alert(err.message);
    } finally {
      setToggling(false);
    }
  };
  const handleDelete = () => setConfirmDeleteProject(true);
  const handleDeleteProjectConfirm = async () => {
    setConfirmDeleteProject(false);
    try { await projApi.delete(project.project_id); navigate('/projects'); } catch {}
  };
  const handleDownload = async () => { try { const blob = await downloadProjectZip(project.project_id); const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href=url; a.download=`${project.name||'project'}.zip`; document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url); } catch (err) { alert(err.message); } };
  const handleOpenFolder = async () => { try { const r = await godot.openFolder(project.project_id); if (!r.success) alert(r.error); } catch (err) { alert(err.message); } };
  const handleRunGodot = async () => { try { const r = await godot.runGodot(project.project_id); if (!r.success) alert(r.error); } catch (err) { alert(err.message); } };
  const handleReloadPreview = () => { if (previewRef.current) previewRef.current.src = getPreviewUrl(project.project_id) + '&t=' + Date.now(); };

  if (loading || !project) return <div className="pd-loading"><div className="pd-spinner" /></div>;

  const conversation = project.ai_conversation || [];
  const baseFiles = _extractFiles(project);
  const files = { ...baseFiles, ...editedFiles };
  const fileNames = Object.keys(files);
  const hasFiles = fileNames.length > 0;
  const stats = _getStats(project);
  const fileGroups = groupFilesByFolder(fileNames);
  const hasAgentActivity = Object.keys(agentStatus).length > 0;
  const currentValue = selectedFile ? (files[selectedFile] ?? '') : '';

  return (
    <div className="pd-root" ref={(el) => { dropRef.current = el; rootRef.current = el; }} onDragOver={handleDragOver} onDragLeave={handleDragLeave} onDrop={handleDrop}>

      {/* Drop overlay */}
      {isDragging && (
        <div className="pd-drop-overlay">
          <div className="pd-drop-box">
            <svg width="32" height="32" viewBox="0 0 32 32" fill="none">
              <path d="M16 4v16M8 12l8-8 8 8M6 24h20" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
            <span>Drop files or folder to import</span>
          </div>
        </div>
      )}

      {/* Hidden file inputs */}
      <input ref={fileInputRef} type="file" multiple accept="*" style={{ display:'none' }} onChange={handleFileInputChange} />
      <input ref={folderInputRef} type="file" webkitdirectory="true" multiple style={{ display:'none' }} onChange={handleFileInputChange} />
      <input ref={imageInputRef} type="file" multiple accept="image/*" style={{ display:'none' }} onChange={handleImageUpload} />

      {/* ── Left Panel ── */}
      <div className="pd-left" style={{ width: leftWidth, minWidth: leftWidth, flexShrink: 0 }}>
        <div className="pd-left-header">
          <div className="pd-project-info">
            <button className="pd-back" onClick={() => navigate('/projects')}>
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <path d="M10 12L6 8l4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </button>
            <span className="pd-project-name">{project.name}</span>
            <span className={`pd-project-status pd-status-${project.status}`}>{project.status}</span>
          </div>
          <div className="pd-header-actions">
            {hasFiles && <button className="pd-icon-btn" onClick={handleShare} title={shareCopied ? 'Link copied!' : 'Copy share link'} style={shareCopied?{color:'#4ade80'}:{}}>
              {shareCopied
                ? <svg width="13" height="13" viewBox="0 0 14 14" fill="none"><path d="M2 7l3 3 7-7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
                : <svg width="13" height="13" viewBox="0 0 14 14" fill="none"><circle cx="10.5" cy="3.5" r="1.5" stroke="currentColor" strokeWidth="1.2"/><circle cx="10.5" cy="10.5" r="1.5" stroke="currentColor" strokeWidth="1.2"/><circle cx="3.5" cy="7" r="1.5" stroke="currentColor" strokeWidth="1.2"/><path d="M5 7.8l4 2M5 6.2l4-2" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/></svg>
              }
            </button>}
            {hasFiles && <button className="pd-icon-btn" onClick={handleDownload} title="Download ZIP"><svg width="13" height="13" viewBox="0 0 14 14" fill="none"><path d="M7 1.75v7m0 0l-2.5-2.5M7 8.75l2.5-2.5M2.333 11.083h9.334" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/></svg></button>}
            {hasFiles && <button className="pd-icon-btn" onClick={handleOpenFolder} title="Open folder"><svg width="13" height="13" viewBox="0 0 14 14" fill="none"><path d="M1.75 4.083h4.667L7.583 5.25H12.25v6.417H1.75V4.083z" stroke="currentColor" strokeWidth="1.2" fill="none" strokeLinecap="round" strokeLinejoin="round"/></svg></button>}
            {hasFiles && <button className="pd-icon-btn pd-godot-icon" onClick={handleRunGodot} title="Run in Godot"><svg width="13" height="13" viewBox="0 0 14 14" fill="none"><circle cx="7" cy="7" r="5.25" stroke="currentColor" strokeWidth="1.2"/><path d="M5.5 5.5L9 7l-3.5 1.5V5.5z" fill="currentColor"/></svg></button>}
            {user?.user_id === project.user_id && (
              <button
                className="pd-icon-btn"
                onClick={handleToggleVisibility}
                disabled={toggling}
                title={project.is_public ? 'Set to private' : 'Set to public'}
                style={project.is_public ? { color: '#4ade80' } : {}}
              >
                {project.is_public ? (
                  <svg width="13" height="13" viewBox="0 0 14 14" fill="none"><circle cx="7" cy="7" r="5.25" stroke="currentColor" strokeWidth="1.2"/><path d="M7 4v3l2 1.5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/></svg>
                ) : (
                  <svg width="13" height="13" viewBox="0 0 14 14" fill="none"><rect x="2.5" y="6" width="9" height="6.5" rx="1" stroke="currentColor" strokeWidth="1.2"/><path d="M4.5 6V4.5a2.5 2.5 0 015 0V6" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/></svg>
                )}
              </button>
            )}
            <button className="pd-icon-btn pd-danger-icon" onClick={handleDelete} title="Delete project"><svg width="13" height="13" viewBox="0 0 14 14" fill="none"><path d="M1.75 3.5h10.5M5.25 3.5V2.333c0-.322.261-.583.583-.583h2.334c.322 0 .583.261.583.583V3.5m1.75 0v8.167c0 .322-.261.583-.583.583H4.083a.583.583 0 01-.583-.583V3.5h7" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/></svg></button>
          </div>
        </div>

        {/* Import toolbar */}
        <div className="pd-import-bar">
          <span className="pd-import-label">Import codebase</span>
          <button className="pd-import-btn" onClick={() => fileInputRef.current?.click()} disabled={importing}>
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M6 1v7M3 4l3-3 3 3M1 10h10" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/></svg>
            Files
          </button>
          <button className="pd-import-btn" onClick={() => folderInputRef.current?.click()} disabled={importing}>
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M1 3h4l1 1.5H11v6H1V3z" stroke="currentColor" strokeWidth="1.1" fill="none" strokeLinecap="round" strokeLinejoin="round"/></svg>
            Folder
          </button>
          <button className="pd-import-btn" onClick={() => imageInputRef.current?.click()} disabled={importing}>
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><rect x="1" y="2" width="10" height="8" rx="1" stroke="currentColor" strokeWidth="1.1"/><circle cx="4" cy="5" r="1" fill="currentColor"/><path d="M1 8l3-3 2 2 2-2 3 3" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round"/></svg>
            Images
          </button>
          {importMsg && <span className={`pd-import-msg ${importMsg.startsWith('Import failed') ? 'error' : ''}`}>{importMsg}</span>}
          {importing && <div className="pd-mini-spinner" />}
        </div>

        {/* Agent progress */}
        {hasAgentActivity && (
          <div className="pd-agent-panel">
            {Object.entries(agentStatus).map(([key, val]) => (
              <div key={key} className={`pd-agent-row pd-agent-${val.status}`}>
                <div className="pd-agent-indicator">
                  {val.status === 'running' && <div className="pd-agent-spinner" />}
                  {val.status === 'complete' && <svg width="10" height="10" viewBox="0 0 12 12" fill="none"><path d="M2 6l3 3 5-5" stroke="#4ade80" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>}
                  {val.status === 'pending' && <div className="pd-agent-dot" />}
                </div>
                <span className="pd-agent-label">{AGENT_LABELS[key]}</span>
              </div>
            ))}
          </div>
        )}

        {/* Stats */}
        {stats && !hasAgentActivity && (
          <div className="pd-stats-bar">
            {[['entities',stats.entities||0],['scripts',stats.scripts||0],['scenes',stats.scenes||0],['assets',stats.assets||0]].map(([k,v]) => (
              <span key={k} className="pd-stat"><span className="pd-stat-val">{v}</span> {k}</span>
            ))}
          </div>
        )}

        {/* Messages */}
        <div className="pd-messages">
          {conversation.length === 0 && !hasAgentActivity && (
            <div className="pd-empty-chat">
              <div className="pd-empty-icon">
                <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
                  <rect x="3" y="3" width="22" height="22" rx="3" stroke="#333" strokeWidth="1.5"/>
                  <path d="M8 10h12M8 14h8M8 18h5" stroke="#444" strokeWidth="1.3" strokeLinecap="round"/>
                </svg>
              </div>
              <p className="pd-empty-title">Describe your game</p>
              <p className="pd-empty-sub">Or import an existing codebase above — the AI will read your files and continue from where you left off.</p>
            </div>
          )}
          {conversation.map((msg, i) => (
            <div key={i} className={`pd-msg pd-msg-${msg.role}`}>
              <span className="pd-msg-role">{msg.role === 'user' ? 'you' : msg.role === 'system' ? 'sys' : 'ai'}</span>
              <div className="pd-msg-content">{msg.content}</div>
            </div>
          ))}
          {chatLoading && (
            <div className="pd-msg pd-msg-assistant">
              <span className="pd-msg-role">ai</span>
              <div className="pd-msg-content pd-typing"><span /><span /><span /></div>
            </div>
          )}
          <div ref={chatEndRef} />
        </div>

        <form className="pd-input-area" onSubmit={handleSend}>
          <textarea
            className="pd-input"
            value={chatInput}
            onChange={e => setChatInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={hasFiles ? "Describe changes, reference files, ask questions…" : "Describe your game idea…"}
            rows={2}
            disabled={chatLoading}
          />
          <button type="submit" className="pd-send-btn" disabled={chatLoading || !chatInput.trim()}>
            {chatLoading ? <div className="pd-send-spinner" /> : (
              <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
                <path d="M2.5 8h11M8.5 3l5 5-5 5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            )}
          </button>
        </form>
      </div>

      {/* ── Resize Handle ── */}
      <div className="pd-resize-handle" onMouseDown={onResizeStart}>
        <div className="pd-resize-grip" />
      </div>

      {/* ── Right Panel ── */}
      <div className="pd-right">
        <div className="pd-right-header">
          <div className="pd-right-tabs">
            {['preview','code','console'].map(tab => (
              <button key={tab} className={`pd-right-tab ${rightPanel===tab?'active':''} ${tab==='console'&&consoleLogs.some(l=>l.level==='error')?'pd-tab-error':''}`} onClick={() => setRightPanel(tab)}>
                {tab.charAt(0).toUpperCase()+tab.slice(1)}
                {tab==='console'&&consoleLogs.length>0&&<span className="pd-tab-badge">{consoleLogs.length}</span>}
              </button>
            ))}
          </div>

          <div className="pd-right-actions">
            {project?.versions?.length > 0 && (
              <button className="pd-icon-btn" onClick={() => setShowVersions(true)} title="Version history">
                <svg width="13" height="13" viewBox="0 0 14 14" fill="none"><circle cx="7" cy="7" r="5.5" stroke="currentColor" strokeWidth="1.2"/><path d="M7 4.5V7l2 1.5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/></svg>
              </button>
            )}
            <button className="pd-icon-btn pd-newfile-btn" onClick={handleCreateFile} title="New file">
              <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
                <path d="M7 2v10M2 7h10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
              </svg>
            </button>
            {rightPanel === 'preview' && hasFiles && (
              <button className="pd-icon-btn" onClick={handleReloadPreview} title="Reload">
                <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M10 6a4 4 0 11-1.17-2.83" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/><path d="M10 1.5v2.5H7.5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/></svg>
              </button>
            )}
            {rightPanel === 'code' && (
              <>
                {isDirty && (
                  <button className="pd-save-btn" onClick={handleSave} disabled={saving}>
                    {saving ? <div className="pd-mini-spinner" /> : (
                      <svg width="12" height="12" viewBox="0 0 14 14" fill="none"><path d="M11.5 11.5H2.5V2.5h7l2 2v7z" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/><path d="M9 11.5V8H5v3.5M5 2.5v3h3.5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/></svg>
                    )}
                    {saving ? 'Saving…' : 'Save'}
                  </button>
                )}
                {saveMsg === 'saved' && <span className="pd-save-feedback saved">Saved</span>}
                {saveMsg === 'error' && <span className="pd-save-feedback error">Save failed</span>}
              </>
            )}
            {diffFiles && (
              <button className="pd-diff-btn" onClick={() => setDiffFiles(null)} title="Dismiss diff">
                <span className="pd-diff-badge">{diffFiles.changed.length} changed</span>
                <svg width="10" height="10" viewBox="0 0 10 10" fill="none"><path d="M1 1l8 8M9 1L1 9" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/></svg>
              </button>
            )}
            {hasFiles && <span className="pd-file-count">{fileNames.length} files</span>}
          </div>
        </div>

        {/* Tab bar */}
        {rightPanel === 'code' && openTabs.length > 0 && (
          <div className="pd-tab-bar">
            {openTabs.map(tab => (
              <div key={tab} className={`pd-editor-tab ${selectedFile===tab?'active':''} ${editedFiles[tab]!==undefined?'dirty':''}`}
                onClick={() => setSelectedFile(tab)}>
                <span className="pd-editor-tab-icon" style={{color:getFileColor(tab)}}>{getFileIcon(tab)}</span>
                <span className="pd-editor-tab-name">{tab.split('/').pop()}</span>
                {editedFiles[tab]!==undefined && <span className="pd-editor-tab-dot"/>}
                <button className="pd-editor-tab-close" onClick={(e)=>closeTab(tab,e)}>×</button>
              </div>
            ))}
          </div>
        )}

        <div className="pd-right-body">
          {rightPanel === 'console' && (
            <div className="pd-console">
              <div className="pd-console-toolbar">
                <span className="pd-console-label">Console</span>
                <button className="pd-icon-btn" onClick={() => setConsoleLogs([])} title="Clear">
                  <svg width="11" height="11" viewBox="0 0 12 12" fill="none"><path d="M1 1l10 10M11 1L1 11" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/></svg>
                </button>
              </div>
              <div className="pd-console-body">
                {consoleLogs.length === 0 && (
                  <span className="pd-console-empty">No output yet — run your game to see console messages.</span>
                )}
                {consoleLogs.map((log, i) => (
                  <div key={i} className={`pd-console-line pd-console-${log.level}`}>
                    <span className="pd-console-level">{log.level}</span>
                    <span className="pd-console-text">{log.text}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
          {rightPanel === 'code' && (hasFiles || isCreatingFile) && (
            <div className="pd-file-tree">
              {isCreatingFile && (
                <form className="pd-new-file-row" onSubmit={handleNewFileSubmit}>
                  <svg width="11" height="11" viewBox="0 0 12 12" fill="none" style={{flexShrink:0,color:'#555'}}>
                    <path d="M2 1h5.5L10 3.5V11H2V1z" stroke="currentColor" strokeWidth="1" fill="none"/>
                    <path d="M7.5 1v3H10" stroke="currentColor" strokeWidth="1" fill="none"/>
                  </svg>
                  <input
                    ref={newFileInputRef}
                    className="pd-new-file-input"
                    value={newFileName}
                    onChange={e => setNewFileName(e.target.value)}
                    onKeyDown={handleNewFileKeyDown}
                    onBlur={() => { if (!newFileName.trim()) { setIsCreatingFile(false); } }}
                    placeholder="filename.js"
                    spellCheck={false}
                  />
                  <button type="submit" className="pd-new-file-confirm" tabIndex={-1}>↵</button>
                </form>
              )}
              {fileGroups.map(([folder, groupFiles]) => (
                <div key={folder} className="pd-file-group">
                  {folder && (
                    <div className="pd-folder-name">
                      <svg width="11" height="11" viewBox="0 0 12 12" fill="none"><path d="M1 3h4l1.5 1.5H11v6H1V3z" stroke="#444" strokeWidth="1" fill="none"/></svg>
                      {folder}/
                    </div>
                  )}
                  {groupFiles.map(f => (
                    renaming === f ? (
                      <div key={f} className="pd-file-item active" style={{ paddingLeft: folder?24:8 }}>
                        <span className="pd-file-icon" style={{ color:getFileColor(f) }}>{getFileIcon(f)}</span>
                        <input
                          ref={renameInputRef}
                          className="pd-rename-input"
                          value={renameVal}
                          onChange={e => setRenameVal(e.target.value)}
                          onKeyDown={e => { if (e.key==='Enter') handleRenameSubmit(); if (e.key==='Escape') setRenaming(null); }}
                          onBlur={handleRenameSubmit}
                        />
                      </div>
                    ) : (
                      <button key={f} className={`pd-file-item ${selectedFile===f?'active':''} ${editedFiles[f]!==undefined?'dirty':''}`}
                        onClick={() => openTab(f)}
                        onContextMenu={(e) => handleFileContextMenu(e, f)}
                        style={{ paddingLeft: folder?24:8 }}>
                        <span className="pd-file-icon" style={{ color:getFileColor(f) }}>{getFileIcon(f)}</span>
                        <span className="pd-file-name">{folder ? f.split('/').pop() : f}</span>
                        {editedFiles[f] !== undefined && <span className="pd-dirty-dot" />}
                        {diffFiles?.changed?.includes(f) && <span className="pd-diff-dot" title="Changed by AI" />}
                      </button>
                    )
                  ))}
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
                  onLoad={(e) => {
                    try {
                      const doc = e.target.contentDocument;
                      if (!doc) return;
                      const s = doc.createElement('script');
                      s.textContent = `(function(){['log','warn','error'].forEach(function(l){var o=console[l];console[l]=function(){window.parent.postMessage({type:'console',level:l,args:Array.from(arguments).map(String)}, '*');o.apply(console,arguments);};});window.addEventListener('error',function(e){window.parent.postMessage({type:'error',message:e.message},'*');});})();`;
                      doc.head?.prepend(s);
                    } catch {}
                  }}
                />
              ) : (
                <div className="pd-right-empty">
                  <p className="pd-empty-title">No preview yet</p>
                  <p className="pd-empty-sub">Send a message or import a codebase to get started.</p>
                </div>
              )
            ) : (
              (hasFiles || editedFiles[selectedFile] !== undefined) && selectedFile ? (
                <ErrorBoundary>
                <Editor
                  height="100%"
                  language={getLanguage(selectedFile)}
                  value={currentValue}
                  theme="pd-black"
                  beforeMount={registerGDScript}
                  onChange={handleEditorChange}
                  options={{
                    readOnly: false,
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
                    tabSize: 2,
                    formatOnPaste: true,
                    suggestOnTriggerCharacters: true,
                    quickSuggestions: true,
                  }}
                />
                </ErrorBoundary>
              ) : (
                <div className="pd-right-empty">
                  <p className="pd-empty-title">No files yet</p>
                  <p className="pd-empty-sub">Generate a game or import your codebase to start editing.</p>
                </div>
              )
            )}
          </div>
        </div>
      </div>
      {/* ── Context menu ── */}
      {ctxMenu && (
        <div className="pd-ctx-menu" style={{ top: ctxMenu.y, left: ctxMenu.x }} onClick={e => e.stopPropagation()}>
          <button className="pd-ctx-item" onClick={() => handleFileAction('explain')}>
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><circle cx="6" cy="6" r="5" stroke="currentColor" strokeWidth="1"/><path d="M6 5.5v3M6 4v.5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/></svg>
            Explain file
          </button>
          <button className="pd-ctx-item" onClick={() => handleFileAction('fix')}>
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M2 6l2.5 2.5L10 3" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/></svg>
            Fix bugs
          </button>
          <button className="pd-ctx-item" onClick={() => handleFileAction('improve')}>
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M6 1l1.5 3 3.5.5-2.5 2.5.5 3.5L6 9 2.5 10.5l.5-3.5L.5 4.5 4 4z" stroke="currentColor" strokeWidth="1" fill="none"/></svg>
            Improve
          </button>
          <div className="pd-ctx-sep" />
          <button className="pd-ctx-item" onClick={() => handleStartRename(ctxMenu.file)}>
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M8 2l2 2-6 6H2V8l6-6z" stroke="currentColor" strokeWidth="1" fill="none"/></svg>
            Rename
          </button>
          <button className="pd-ctx-item pd-ctx-danger" onClick={() => handleDeleteFile(ctxMenu.file)}>
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M1.5 3h9M4 3V2h4v1M4.5 3v6M7.5 3v6M2 3l.5 7h7L10 3" stroke="currentColor" strokeWidth="1" strokeLinecap="round"/></svg>
            Delete
          </button>
        </div>
      )}

      {/* ── Toast notification ── */}
      {toast && (
        <div className={`pd-toast pd-toast-${toast.type}`}>
          {toast.type === 'rate' && <svg width="13" height="13" viewBox="0 0 14 14" fill="none"><circle cx="7" cy="7" r="5.5" stroke="currentColor" strokeWidth="1.2"/><path d="M7 4.5v3M7 9.5v.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/></svg>}
          <span>{toast.msg}{toast.countdown > 0 ? ` (${toast.countdown}s)` : ''}</span>
          <button onClick={() => setToast(null)} className="pd-toast-close">×</button>
        </div>
      )}

      {/* ── Session expired modal ── */}
      <Modal open={sessionExpired} onClose={() => {}} title="Session expired">
        <p style={{ fontSize: 13, color: '#888', marginBottom: 20 }}>Your session has expired. Please log in again to continue.</p>
        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <button onClick={() => { setSessionExpired(false); navigate('/login'); }}
            style={{ padding: '6px 16px', fontSize: 12, fontWeight: 600, background: '#fff', color: '#000', border: 'none', borderRadius: 6, cursor: 'pointer' }}>
            Log in
          </button>
        </div>
      </Modal>

      {/* ── Delete project confirm modal ── */}
      <Modal open={confirmDeleteProject} onClose={() => setConfirmDeleteProject(false)} title="Delete project">
        <p style={{ fontSize: 13, color: '#888', marginBottom: 20 }}>
          This will permanently delete <strong style={{color:'#ccc'}}>{project?.name}</strong> and all its files.
        </p>
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <button onClick={() => setConfirmDeleteProject(false)} style={{ padding: '6px 14px', fontSize: 12, background: '#111', color: '#888', border: '1px solid #222', borderRadius: 6, cursor: 'pointer' }}>Cancel</button>
          <button onClick={handleDeleteProjectConfirm} style={{ padding: '6px 14px', fontSize: 12, fontWeight: 600, background: '#1a0000', color: '#f87171', border: '1px solid #3a0000', borderRadius: 6, cursor: 'pointer' }}>Delete</button>
        </div>
      </Modal>

      {/* ── Delete file confirm modal ── */}
      <Modal open={!!confirmDeleteFile} onClose={() => setConfirmDeleteFile(null)} title="Delete file">
        <p style={{ fontSize: 13, color: '#888', marginBottom: 20 }}>
          Delete <strong style={{color:'#ccc'}}>{confirmDeleteFile}</strong>? This removes it from the project.
        </p>
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <button onClick={() => setConfirmDeleteFile(null)} style={{ padding: '6px 14px', fontSize: 12, background: '#111', color: '#888', border: '1px solid #222', borderRadius: 6, cursor: 'pointer' }}>Cancel</button>
          <button onClick={handleDeleteFileConfirm} style={{ padding: '6px 14px', fontSize: 12, fontWeight: 600, background: '#1a0000', color: '#f87171', border: '1px solid #3a0000', borderRadius: 6, cursor: 'pointer' }}>Delete</button>
        </div>
      </Modal>

      {/* ── Version history modal ── */}
      <Modal open={showVersions} onClose={() => setShowVersions(false)} title="Version history">
        <div className="pd-versions">
          {(project?.versions || []).length === 0 && (
            <p style={{fontSize:12,color:'#555',padding:'8px 0'}}>No versions saved yet.</p>
          )}
          {[...(project?.versions || [])].reverse().map((v, i) => (
            <div key={i} className="pd-version-row">
              <div className="pd-version-meta">
                <span className="pd-version-ts">{new Date(v.timestamp).toLocaleString()}</span>
                <span className="pd-version-src">{v.source}</span>
              </div>
              <div className="pd-version-files">
                {(v.files || []).slice(0, 8).map(f => (
                  <span key={f} className="pd-version-file">{f}</span>
                ))}
                {(v.files || []).length > 8 && <span className="pd-version-file">+{v.files.length - 8} more</span>}
              </div>
            </div>
          ))}
        </div>
      </Modal>

      {/* ── Ctrl+P file switcher ── */}
      {showSwitcher && (
        <div className="pd-overlay" onClick={() => setShowSwitcher(false)}>
          <div className="pd-switcher" onClick={e => e.stopPropagation()}>
            <input
              ref={switcherRef}
              className="pd-switcher-input"
              placeholder="Go to file…"
              value={switcherQuery}
              onChange={e => setSwitcherQuery(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Escape') setShowSwitcher(false);
                if (e.key === 'Enter') {
                  const match = fileNames.filter(f => f.toLowerCase().includes(switcherQuery.toLowerCase()))[0];
                  if (match) { openTab(match); setShowSwitcher(false); }
                }
              }}
            />
            <div className="pd-switcher-list">
              {fileNames.filter(f => !switcherQuery || f.toLowerCase().includes(switcherQuery.toLowerCase())).slice(0, 12).map(f => (
                <button key={f} className={`pd-switcher-item ${selectedFile===f?'active':''}`}
                  onClick={() => { openTab(f); setShowSwitcher(false); }}>
                  <span className="pd-file-icon" style={{color:getFileColor(f)}}>{getFileIcon(f)}</span>
                  {f}
                </button>
              ))}
              {fileNames.length === 0 && <p className="pd-switcher-empty">No files in project</p>}
            </div>
          </div>
        </div>
      )}

      {/* ── Ctrl+Shift+F search across files ── */}
      {showSearch && (
        <div className="pd-overlay" onClick={() => setShowSearch(false)}>
          <div className="pd-search-panel" onClick={e => e.stopPropagation()}>
            <input
              ref={searchRef}
              className="pd-switcher-input"
              placeholder="Search in files…"
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              onKeyDown={e => { if (e.key === 'Escape') setShowSearch(false); }}
            />
            <div className="pd-switcher-list">
              {searchQuery.trim() && (() => {
                const q = searchQuery.toLowerCase();
                const results = [];
                for (const [filename, content] of Object.entries(files)) {
                  const lines = (content || '').split('\n');
                  lines.forEach((line, idx) => {
                    if (line.toLowerCase().includes(q)) {
                      results.push({ filename, line: line.trim(), lineNum: idx + 1 });
                    }
                  });
                  if (results.length >= 50) return results;
                }
                return results;
              })().map((r, i) => (
                <button key={i} className="pd-search-result"
                  onClick={() => { openTab(r.filename); setShowSearch(false); }}>
                  <div className="pd-search-file">
                    <span style={{color:getFileColor(r.filename)}}>{getFileIcon(r.filename)}</span>
                    {r.filename}
                    <span className="pd-search-linenum">:{r.lineNum}</span>
                  </div>
                  <div className="pd-search-line">{r.line.slice(0, 80)}</div>
                </button>
              ))}
              {searchQuery.trim() && Object.entries(files).every(([,c]) => !(c||'').toLowerCase().includes(searchQuery.toLowerCase())) && (
                <p className="pd-switcher-empty">No matches found</p>
              )}
              {!searchQuery.trim() && <p className="pd-switcher-empty">Type to search across all files</p>}
            </div>
          </div>
        </div>
      )}

      {/* AI file action loading overlay */}
      {fileActionLoading && (
        <div style={{ position:'fixed', bottom:24, right:24, background:'#111', border:'1px solid #222', borderRadius:8, padding:'10px 16px', display:'flex', alignItems:'center', gap:8, fontSize:12, color:'#888', zIndex:200 }}>
          <div className="pd-mini-spinner" /> Analyzing file…
        </div>
      )}
    </div>
  );
}
