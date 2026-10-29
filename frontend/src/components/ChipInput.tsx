import { useId, useState } from 'react';

/** Type a skill and press Enter or comma to add it. Pasting a comma-separated list works too. */
export function ChipInput({ label, value, onChange, placeholder, tone }: {
  label: string;
  value: string[];
  onChange: (next: string[]) => void;
  placeholder?: string;
  tone?: 'req';
}) {
  const id = useId();
  const [draft, setDraft] = useState('');

  const add = (raw: string) => {
    const items = raw.split(',').map(s => s.trim()).filter(Boolean);
    const next = [...value];
    for (const item of items) {
      if (!next.some(v => v.toLowerCase() === item.toLowerCase()) && next.length < 30) next.push(item);
    }
    onChange(next);
    setDraft('');
  };

  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <div className="chip-input" onClick={() => document.getElementById(id)?.focus()}>
        {value.map(v => (
          <span key={v} className={`chip ${tone ?? ''}`}>
            {v}
            <button type="button" aria-label={`Remove ${v}`} onClick={() => onChange(value.filter(x => x !== v))}>×</button>
          </span>
        ))}
        <input
          id={id}
          value={draft}
          placeholder={value.length ? '' : placeholder}
          onChange={e => {
            if (e.target.value.includes(',')) add(e.target.value);
            else setDraft(e.target.value);
          }}
          onKeyDown={e => {
            if (e.key === 'Enter') { e.preventDefault(); if (draft.trim()) add(draft); }
            if (e.key === 'Backspace' && !draft && value.length) onChange(value.slice(0, -1));
          }}
          onBlur={() => { if (draft.trim()) add(draft); }}
        />
      </div>
    </div>
  );
}
