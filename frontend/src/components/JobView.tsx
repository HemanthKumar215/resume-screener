import { useCallback, useEffect, useRef, useState } from 'react';
import { api, uploadToS3 } from '../api';
import type { CandidateSummary, Job, Stage } from '../types';
import { CandidatePanel } from './CandidatePanel';
import { SEGMENT_COLORS, SEGMENT_LABELS, describeComponents, tierClass } from '../score';
import { FitBar } from './FitBar';

const ACCEPT = '.pdf,.docx,.txt,.png,.jpg,.jpeg';
const UPLOAD_CONCURRENCY = 4;
type Filter = 'all' | Stage;

interface TrayItem {
  name: string;
  progress: number;
  state: 'uploading' | 'done' | 'error';
  error?: string;
}

export function JobView({ job, onEdit, onDeleted, onJobChanged, notify }: {
  job: Job;
  onEdit: () => void;
  onDeleted: () => void;
  onJobChanged: () => void;
  notify: (msg: string, kind?: 'ok' | 'err') => void;
}) {
  const [cands, setCands] = useState<CandidateSummary[] | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>('all');
  const [tray, setTray] = useState<TrayItem[]>([]);
  const [over, setOver] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  const fileInput = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    try {
      setCands(await api.candidates(job.id));
      setNow(Date.now());
    } catch (e) {
      notify((e as Error).message, 'err');
    }
  }, [job.id, notify]);

  useEffect(() => {
    let cancelled = false;
    api.candidates(job.id)
      .then(c => { if (!cancelled) setCands(c); })
      .catch(e => { if (!cancelled) notify((e as Error).message, 'err'); });
    return () => { cancelled = true; };
  }, [job.id, job.updated_at, notify]);

  // Poll while anything is still being read and scored.
  const busy = cands?.some(c => c.status === 'PROCESSING' || (c.status === 'UPLOADING' && !isStale(c, now))) ?? false;
  useEffect(() => {
    if (!busy) return;
    const t = setInterval(load, 2500);
    return () => clearInterval(t);
  }, [busy, load]);

  const uploadFiles = async (files: File[]) => {
    if (!files.length) return;
    let tickets;
    try {
      tickets = (await api.requestUploads(job.id, files)).uploads;
    } catch (e) {
      notify((e as Error).message, 'err');
      return;
    }
    setTray(files.map(f => ({ name: f.name, progress: 0, state: 'uploading' })));
    await load();

    const update = (i: number, patch: Partial<TrayItem>) =>
      setTray(t => t.map((item, j) => (j === i ? { ...item, ...patch } : item)));
    let next = 0;
    const worker = async () => {
      while (next < files.length) {
        const i = next++;
        try {
          await uploadToS3(tickets[i], files[i], pct => update(i, { progress: pct }));
          update(i, { progress: 100, state: 'done' });
        } catch (e) {
          update(i, { state: 'error', error: (e as Error).message });
        }
      }
    };
    await Promise.all(Array.from({ length: Math.min(UPLOAD_CONCURRENCY, files.length) }, worker));
    onJobChanged();
    await load();
    setTimeout(() => setTray(t => t.filter(x => x.state === 'error')), 2500);
  };

  const exportCsv = async () => {
    try {
      const { blob, filename } = await api.exportCsv(job.id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      notify((e as Error).message, 'err');
    }
  };

  const deleteJob = async () => {
    if (!confirm(`Delete "${job.title}" and all ${job.candidate_count} of its candidates? Resume files are deleted too.`)) return;
    try {
      await api.deleteJob(job.id);
      onDeleted();
    } catch (e) {
      notify((e as Error).message, 'err');
    }
  };

  const shown = (cands ?? []).filter(c => filter === 'all' || c.stage === filter);
  const scored = (cands ?? []).filter(c => c.status === 'SCORED');
  const legendKeys = scored[0]?.components.map(c => c.key) ?? [];
  const ranks = new Map(scored.map((c, i) => [c.id, i + 1]));

  return (
    <div className="page">
      <header style={{ display: 'grid', gap: 10 }}>
        <div className="job-head">
          <h1>{job.title}</h1>
          <div className="job-actions">
            <button className="btn" onClick={onEdit}>Edit requirements</button>
            <button className="btn" onClick={exportCsv} disabled={!scored.length}>Export CSV</button>
            <button className="btn btn-quiet btn-danger" onClick={deleteJob}>Delete job</button>
          </div>
        </div>
        <div className="reqs">
          {job.required_skills.length > 0 && (
            <span className="chips" aria-label="Required skills">
              {job.required_skills.map(s => <span key={s} className="chip req">{s}</span>)}
            </span>
          )}
          {job.nice_to_have_skills.length > 0 && (
            <span className="chips" aria-label="Nice-to-have skills">
              {job.nice_to_have_skills.map(s => <span key={s} className="chip">{s}</span>)}
            </span>
          )}
          {job.min_years > 0 && <span>{job.min_years}+ years</span>}
          {job.min_education !== 'None' && <span>{job.min_education} or higher</span>}
          {job.required_skills.length === 0 && (
            <span>No required skills yet. <button className="btn btn-quiet" style={{ padding: '2px 6px' }} onClick={onEdit}>Add some</button> so ranking means something.</span>
          )}
        </div>
      </header>

      <section
        className={`drop${over ? ' over' : ''}`}
        onDragOver={e => { e.preventDefault(); setOver(true); }}
        onDragLeave={() => setOver(false)}
        onDrop={e => { e.preventDefault(); setOver(false); uploadFiles(Array.from(e.dataTransfer.files)); }}
        aria-label="Upload resumes"
      >
        <div className="copy">
          <strong>Drop resumes here</strong>
          <span className="hint">PDF, DOCX, TXT or a photo of a resume, up to 25 at a time. Each is scored within a few seconds.</span>
        </div>
        <button className="btn btn-primary" onClick={() => fileInput.current?.click()}>Choose files</button>
        <input ref={fileInput} type="file" multiple accept={ACCEPT} className="sr-only" tabIndex={-1}
          onChange={e => { uploadFiles(Array.from(e.target.files ?? [])); e.target.value = ''; }} />
        {tray.length > 0 && (
          <div className="tray" style={{ flexBasis: '100%' }} aria-live="polite">
            {tray.map((t, i) => (
              <div key={`${t.name}-${i}`} className="tray-row">
                <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{t.name}</span>
                <span className="bar"><i style={{ width: `${t.progress}%`, background: t.state === 'error' ? 'var(--weak)' : undefined }} /></span>
                <span className={t.state === 'error' ? 'error-text' : 'hint'}>
                  {t.state === 'error' ? t.error : t.state === 'done' ? 'Uploaded' : `${t.progress}%`}
                </span>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="board" aria-labelledby="board-title">
        <div className="board-head">
          <h2 id="board-title">
            {cands === null ? 'Candidates' : `${cands.length} candidate${cands.length === 1 ? '' : 's'}, best match first`}
          </h2>
          <div className="seg-tabs" role="group" aria-label="Filter by stage">
            {(['all', 'shortlisted', 'interview', 'rejected'] as Filter[]).map(f => (
              <button key={f} aria-pressed={filter === f} onClick={() => setFilter(f)}>
                {f === 'all' ? 'All' : f[0].toUpperCase() + f.slice(1)}
              </button>
            ))}
          </div>
        </div>

        {cands === null && <div className="empty"><p className="pending">Loading candidates…</p></div>}

        {cands !== null && cands.length === 0 && (
          <div className="empty">
            <h2>No resumes yet</h2>
            <p>Drop resumes above. They'll appear here ranked against this job's requirements.</p>
          </div>
        )}

        {cands !== null && cands.length > 0 && shown.length === 0 && (
          <div className="empty"><p>No candidates are at this stage yet.</p></div>
        )}

        {shown.length > 0 && (
          <>
            <div className="row row-head" aria-hidden="true">
              <span>#</span><span>Candidate</span><span>Fit</span><span className="facts">Required skills</span><span className="stage-h">Stage</span>
            </div>
            {shown.map(c => {
              const isScored = c.status === 'SCORED';
              return (
                <button key={c.id} className="row" aria-current={selected === c.id} onClick={() => setSelected(c.id)}>
                  <span className="rank num">{ranks.get(c.id) ?? ''}</span>
                  <span className="who">
                    <span className="n" style={{ display: 'block' }}>{c.name || c.filename}</span>
                    <span className="f" style={{ display: 'block' }}>
                      {isScored ? experienceLine(c) : c.filename}
                    </span>
                  </span>
                  {isScored ? (
                    <span className="fit">
                      <span className="score num">{c.score}</span>
                      <FitBar components={c.components} label={`Score ${c.score}: ${describeComponents(c.components)}`} />
                      <span className={`tier ${tierClass(c.tier)}`}>{c.tier}</span>
                    </span>
                  ) : c.status === 'FAILED' ? (
                    <span className="error-text">{c.error || "Couldn't read this file"}</span>
                  ) : (
                    <span className="pending">{isStale(c, now) ? 'Upload not received' : c.status === 'UPLOADING' ? 'Uploading…' : 'Reading and scoring…'}</span>
                  )}
                  <span className="facts">
                    {isScored && job.required_skills.length > 0 && (
                      <>
                        <span>{c.matched_required.length} of {c.matched_required.length + c.missing_required.length}</span>
                        {c.missing_required.length > 0 && (
                          <span className="chips">{c.missing_required.slice(0, 3).map(s => <span key={s} className="chip miss">{s}</span>)}</span>
                        )}
                      </>
                    )}
                  </span>
                  <span className={`stage stage-${c.stage}`}>{c.stage}</span>
                </button>
              );
            })}
            {legendKeys.length > 0 && (
              <div className="legend" aria-label="What the bar shows">
                <span>Bar length is the score. Colours show where the points came from:</span>
                {legendKeys.map(k => <span key={k}><i style={{ background: SEGMENT_COLORS[k] }} />{SEGMENT_LABELS[k]}</span>)}
              </div>
            )}
          </>
        )}
      </section>

      {selected && (
        <CandidatePanel
          key={selected}
          jobId={job.id}
          candidateId={selected}
          onClose={() => setSelected(null)}
          onChanged={load}
          onDeleted={() => { setSelected(null); onJobChanged(); load(); }}
          onError={msg => notify(msg, 'err')}
        />
      )}
    </div>
  );
}

function experienceLine(c: CandidateSummary): string {
  const parts = [];
  if (c.experience_years) parts.push(`${c.experience_years} yrs`);
  if (c.education && c.education !== 'None') parts.push(c.education);
  return parts.join(', ') || c.filename;
}

/** An upload that never reached S3 (e.g. the tab was closed mid-upload). */
function isStale(c: CandidateSummary, now: number): boolean {
  return c.status === 'UPLOADING' && now - new Date(c.created_at).getTime() > 10 * 60_000;
}
