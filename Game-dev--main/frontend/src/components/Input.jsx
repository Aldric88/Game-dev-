import './Input.css';

export default function Input({
  label,
  error,
  id,
  ...props
}) {
  return (
    <div className="input-group">
      {label && <label className="input-label" htmlFor={id}>{label}</label>}
      <input className={`input-field ${error ? 'input-error' : ''}`} id={id} {...props} />
      {error && <span className="input-error-text">{error}</span>}
    </div>
  );
}

export function TextArea({ label, error, id, ...props }) {
  return (
    <div className="input-group">
      {label && <label className="input-label" htmlFor={id}>{label}</label>}
      <textarea className={`input-field input-textarea ${error ? 'input-error' : ''}`} id={id} {...props} />
      {error && <span className="input-error-text">{error}</span>}
    </div>
  );
}

export function Select({ label, error, id, children, ...props }) {
  return (
    <div className="input-group">
      {label && <label className="input-label" htmlFor={id}>{label}</label>}
      <select className={`input-field ${error ? 'input-error' : ''}`} id={id} {...props}>
        {children}
      </select>
      {error && <span className="input-error-text">{error}</span>}
    </div>
  );
}
