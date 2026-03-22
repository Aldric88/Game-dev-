import { useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import './PlayPage.css';

const BASE = import.meta.env.VITE_API_BASE_URL || '';

export default function PlayPage() {
  const { id: projectId } = useParams();
  const [projectName, setProjectName] = useState('');
  const iframeRef = useRef(null);

  useEffect(() => {
    if (!projectId) return;
    fetch(`${BASE}/api/v1/projects/${projectId}`)
      .then((res) => {
        if (!res.ok) return null;
        return res.json();
      })
      .then((data) => {
        if (data?.name) setProjectName(data.name);
      })
      .catch(() => {});
  }, [projectId]);

  const handleFullscreen = () => {
    const el = iframeRef.current;
    if (!el) return;
    if (el.requestFullscreen) el.requestFullscreen();
    else if (el.webkitRequestFullscreen) el.webkitRequestFullscreen();
    else if (el.mozRequestFullScreen) el.mozRequestFullScreen();
  };

  const iframeSrc = `${BASE}/api/v1/preview/public/${projectId}`;

  return (
    <div className="play-page">
      {/* Top bar */}
      <div className="play-topbar">
        <div className="play-topbar-left">
          <span className="play-title">Play</span>
          {projectName && (
            <>
              <span className="play-topbar-sep">/</span>
              <span className="play-project-name">{projectName}</span>
            </>
          )}
        </div>
        <button
          className="play-fullscreen-btn"
          onClick={handleFullscreen}
          title="Fullscreen"
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path d="M1.5 5.5V2h3.5M10.5 2H14v3.5M14 10.5V14h-3.5M5.5 14H2v-3.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
          Fullscreen
        </button>
      </div>

      {/* Iframe */}
      <iframe
        ref={iframeRef}
        src={iframeSrc}
        className="play-iframe"
        title={projectName || 'Game'}
        allow="fullscreen"
        sandbox="allow-scripts allow-same-origin"
      />
    </div>
  );
}
