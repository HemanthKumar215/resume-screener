import { useEffect, useState } from 'react';
import { api } from '../api';
import type { CandidateDetail, Stage } from '../types';
import { SEGMENT_COLORS, describeComponents, points, tierClass } from '../score';
import { FitBar } from './FitBar';

const STAGES: { value: Stage; label: string }[] = [
  { value: 'new', label: 'New' },
  { value: 'shortlisted', label: 'Shortlisted' },
  { value: 'interview', label: 'Interview' },
  { value: 'rejected', label: 'Rejected' },
];

export function CandidatePanel({ jobId, candidateId, onClose, onChanged, onDeleted, onError }: {
  jobId: string;
  candidateId: string;
  onClose: () => void;
  onChanged: () => void;
  onDeleted: () => void;
  onError: (msg: string) => void;
}) {
  const [cand, setCand] = useState<CandidateDetail | null>(null);
  const [notes, setNotes] = useState('');
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api.candidate(jobId, candidateId)
      .then(c => { if (!cancelled) { setCand(c); setNotes(c.notes ?? ''); } })
      .catch(e => { if (!cancelled) setLoadError((e as Error).message); });
    return () => { cancelled = true; };
  }, [jobId, candidateId]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const setStage = async (stage: Stage) => {
    if (!cand) return;
    const prev = cand.stage;
    setCand({ ...cand, stage });
    try {
      await api.updateCandidate(jobId, candidateId, { stage });
      onChanged();
    } catch (e) {
      setCand({ ...cand, stage: prev });
      onError((e as Error).message);
    }
  };

  const saveNotes = async () => {
    if (!cand || notes === (cand.notes ?? '')) return;
    try {
      await api.updateCandidate(jobId, candidateId, { notes });
      setCand({ ...cand, notes });
    } catch (e) {
      onError((e as Error).message);
    }
  };

  const remove = async () => {
    if (!cand || !confirm(`Delete ${cand.name || cand.filename}? The resume file is deleted too.`)) return;
    try {
      await api.deleteCandidate(jobId, candidateId);
      onDeleted();
    } catch (e) {
      onError((e as Error).message);
    }
  };

  const r = cand?.result;
  const title = cand ? (cand.name || cand.filename) : 'Loading…';

  return (
    <>
      <div className="scrim" onClick={onClose} />
      <aside className="panel" role="dialog" aria-modal="true" aria-labelledby="cand-title">
        <div className="panel-head">
          <div style={{ flex: 1, minWidth: 0 }}>
            <h2 id="cand-title">{title}</h2>
            {r && (
              <div className="contact">
                {r.contact.email && <a href={`mailto:${r.contact.email}`}>{r.contact.email}</a>}
                {r.contact.phone && <span>{r.contact.phone}</span>}
                {r.contact.linkedin && <a href={withProtocol(r.contact.linkedin)} target="_blank" rel="noreferrer">LinkedIn</a>}
                {r.contact.github && <a href={withProtocol(r.contact.github)} target="_blank" rel="noreferrer">GitHub</a>}
              </div>
            )}
          </div>
          <button className="btn btn-quiet" onClick={onClose} aria-label="Close">✕</button>
        </div>

        <div className="panel-body">
          {loadError && <p className="error-text" role="alert">{loadError}</p>}

          {cand?.status === 'FAILED' && (
            <section>
              <h3>Couldn't read this resume</h3>
              <p>{cand.error}</p>
            </section>
          )}

          {cand && cand.status !== 'SCORED' && cand.status !== 'FAILED' && (
            <p className="pending">Reading and scoring this resume…</p>
          )}

          {r && (
            <>
              <section>
                <div className="big-score">
                  <span className="n num">{r.score}</span>
                  <span className="of">/ 100</span>
                  <span className={`tier ${tierClass(r.tier)}`}>{r.tier}</span>
                </div>
                <FitBar big components={r.components} label={`Score ${r.score}: ${describeComponents(r.components)}`} />
                <div className="breakdown">
                  {r.components.map(c => (
                    <div key={c.key} className="breakdown-row">
                      <i style={{ background: SEGMENT_COLORS[c.key] }} />
                      <div>
                        <div>{c.label}</div>
                        <div className="d">{c.detail}</div>
                      </div>
                      <span className="pts num">{Math.round(points(c))}<span className="hint"> / {c.weight}</span></span>
                    </div>
                  ))}
                </div>
              </section>

              {(r.highlights.length > 0 || r.concerns.length > 0) && (
                <section>
                  <h3>At a glance</h3>
                  <ul className="notes-list">
                    {r.highlights.map(h => <li key={h}><span className="plus" aria-label="Strength">+</span>{h}</li>)}
                    {r.concerns.map(c => <li key={c}><span className="minus" aria-label="Concern">–</span>{c}</li>)}
                  </ul>
                </section>
              )}

              {cand.summary && (
                <section>
                  <h3>AI summary</h3>
                  <div className="summary-box">{cand.summary}</div>
                </section>
              )}

              <section>
                <h3>Skills against the job</h3>
                <div className="chips">
                  {[...r.matched_required, ...r.matched_nice].map(s => <span key={s} className="chip ok">✓ {s}</span>)}
                  {r.missing_required.map(s => <span key={s} className="chip miss">Missing {s}</span>)}
                </div>
                {r.skills_found.length > 0 && (
                  <>
                    <p className="hint" style={{ margin: '12px 0 6px' }}>Everything recognised on the resume</p>
                    <div className="chips">{r.skills_found.map(s => <span key={s} className="chip">{s}</span>)}</div>
                  </>
                )}
              </section>

              <section>
                <h3>Experience and education</h3>
                <p>
                  {r.experience.years > 0
                    ? `${r.experience.years} years of experience${r.experience.source === 'claim' ? ', as stated on the resume' : ', counted from the dates listed'}.`
                    : 'No work dates found.'}
                </p>
                <p>{r.education === 'None' ? 'No degree found.' : `Highest education: ${r.education}.`}</p>
                {r.experience.ranges.length > 0 && (
                  <p className="hint" style={{ marginTop: 4 }}>{r.experience.ranges.join('; ')}</p>
                )}
              </section>
            </>
          )}

          {cand && (
            <>
              <section>
                <h3>Stage</h3>
                <div className="stage-picker" role="group" aria-label="Candidate stage">
                  {STAGES.map(s => (
                    <button key={s.value} aria-pressed={cand.stage === s.value} onClick={() => setStage(s.value)}>{s.label}</button>
                  ))}
                </div>
              </section>

              <section className="field">
                <label htmlFor="cand-notes" style={{ fontSize: 14, fontWeight: 700, color: 'var(--ink)' }}>Notes</label>
                <textarea id="cand-notes" className="input" style={{ minHeight: 90 }} maxLength={2000} value={notes}
                  onChange={e => setNotes(e.target.value)} onBlur={saveNotes} placeholder="Only you can see these. Saved when you click away." />
              </section>

              <section style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                {cand.download_url && (
                  <a className="btn" href={cand.download_url} target="_blank" rel="noreferrer">Open resume</a>
                )}
                <button className="btn btn-quiet btn-danger" onClick={remove}>Delete candidate</button>
              </section>
            </>
          )}
        </div>
      </aside>
    </>
  );
}

function withProtocol(url: string): string {
  return /^https?:\/\//.test(url) ? url : `https://${url}`;
}
