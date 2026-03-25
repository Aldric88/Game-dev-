import { Component } from 'react';

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    console.error('[ErrorBoundary]', error, info);
  }

  render() {
    if (this.state.error) {
      return (
        <div style={{
          display: 'flex', flexDirection: 'column', alignItems: 'center',
          justifyContent: 'center', height: '100%', gap: 12, padding: 32,
          background: '#000', color: '#555', textAlign: 'center',
        }}>
          <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
            <circle cx="14" cy="14" r="12" stroke="#333" strokeWidth="1.5"/>
            <path d="M14 9v6M14 18v1" stroke="#555" strokeWidth="1.5" strokeLinecap="round"/>
          </svg>
          <p style={{ fontSize: 13, fontWeight: 600, color: '#888' }}>Something went wrong</p>
          <p style={{ fontSize: 11, color: '#444', maxWidth: 260, lineHeight: 1.6 }}>
            {this.state.error.message}
          </p>
          <button
            onClick={() => this.setState({ error: null })}
            style={{
              marginTop: 8, padding: '5px 14px', fontSize: 12, fontWeight: 500,
              background: '#111', color: '#ccc', border: '1px solid #2a2a2a',
              borderRadius: 6, cursor: 'pointer',
            }}
          >
            Try again
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
