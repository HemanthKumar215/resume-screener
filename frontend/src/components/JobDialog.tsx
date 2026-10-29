import { useState } from 'react';
import { api } from '../api';
import type { Education, Job, JobInput } from '../types';
import { ChipInput } from './ChipInput';

const EDUCATION: Education[] = ['None', 'Diploma', "Bachelor's", "Master's", 'Doctorate'];

const EMPTY: JobInput = {
  title: '', description: '', required_skills: [], nice_to_have_skills: [],
  min_years: 0, min_education: 'None', alert_threshold: 80,
};

export function JobDialog({ job, onClose, onSaved }: {
  job: Job | null;
  onClose: () => void;
  onSaved: (job: Job, requirementsChanged: boolean) => void;
}) {
  const [form, setForm] = useState<JobInput>(() => (job ? {
    title: job.title, description: job.description, required_skills: job.required_skills,
    nice_to_have_skills: job.nice_to_have_skills, min_years: job.min_years,
    min_education: job.min_education, alert_threshold: job.alert_threshold,
  } : EMPTY));
  const [saving, setSaving] = useState(false);
  const [detecting, setDetecting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const set = <K extends keyof JobInput>(k: K, v: JobInput[K]) => setForm(f => ({ ...f, [k]: v }));

  const detect = async () => {
    setDetecting(true);
    setError(null);
    try {
      const { skills } = await api.suggestSkills(`${form.title}\n${form.description}`);
      const known = new Set([...form.required_skills, ...form.nice_to_have_skills].map(s => s.toLowerCase()));
      const added = skills.filter(s => !known.has(s.toLowerCase()));
      set('required_skills', [...form.required_skills, ...added].slice(0, 30));
      if (!added.length) setError('No new skills found in the description.');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setDetecting(false);
    }
  };

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      const saved = job ? await api.updateJob(job.id, form) : await api.createJob(form);
      const changed = !!job && JSON.stringify([job.title, job.description, job.required_skills, job.nice_to_have_skills, job.min_years, job.min_education])
        !== JSON.stringify([form.title, form.description, form.required_skills, form.nice_to_have_skills, form.min_years, form.min_education]);
      onSaved(saved, changed);
    } catch (e) {
      setError((e as Error).message);
      setSaving(false);
    }
  };

  return (
    <div className="dialog-wrap" onMouseDown={e => { if (e.target === e.currentTarget) onClose(); }}>
      <form className="dialog" role="dialog" aria-modal="true" aria-labelledby="job-dialog-title"
        onSubmit={e => { e.preventDefault(); save(); }}
        onKeyDown={e => { if (e.key === 'Escape') onClose(); }}>
        <div className="dialog-head">
          <h2 id="job-dialog-title">{job ? 'Edit job' : 'New job'}</h2>
        </div>
        <div className="dialog-body">
          <div className="field">
            <label htmlFor="job-title">Job title</label>
            <input id="job-title" className="input" required maxLength={120} autoFocus value={form.title}
              onChange={e => set('title', e.target.value)} placeholder="e.g. Backend Engineer (Python, AWS)" />
          </div>
          <div className="field">
            <label htmlFor="job-desc">Job description</label>
            <textarea id="job-desc" className="input" maxLength={10000} value={form.description}
              onChange={e => set('description', e.target.value)} placeholder="Paste the job description. It's used for keyword relevance." />
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <button type="button" className="btn" onClick={detect} disabled={detecting || !(form.title + form.description).trim()}>
                {detecting ? 'Reading description…' : 'Find skills in description'}
              </button>
              <span className="hint">Adds the skills it finds to Required skills.</span>
            </div>
          </div>
          <ChipInput label="Required skills" tone="req" value={form.required_skills}
            onChange={v => set('required_skills', v)} placeholder="Python, AWS, SQL…" />
          <ChipInput label="Nice-to-have skills" value={form.nice_to_have_skills}
            onChange={v => set('nice_to_have_skills', v)} placeholder="Terraform, Kubernetes…" />
          <div className="grid-3">
            <div className="field">
              <label htmlFor="job-years">Minimum experience (years)</label>
              <input id="job-years" className="input num" type="number" min={0} max={40} step={0.5} value={form.min_years}
                onChange={e => set('min_years', Number(e.target.value))} />
            </div>
            <div className="field">
              <label htmlFor="job-edu">Minimum education</label>
              <select id="job-edu" className="input" value={form.min_education}
                onChange={e => set('min_education', e.target.value as Education)}>
                {EDUCATION.map(o => <option key={o} value={o}>{o === 'None' ? 'Not required' : o}</option>)}
              </select>
            </div>
            <div className="field">
              <label htmlFor="job-alert">Email me at score</label>
              <input id="job-alert" className="input num" type="number" min={0} max={100} value={form.alert_threshold}
                onChange={e => set('alert_threshold', Number(e.target.value))} />
            </div>
          </div>
          <p className="hint">You'll get an email when a candidate scores at or above that number. Set it to 0 to turn alerts off.</p>
          {error && <p className="error-text" role="alert">{error}</p>}
        </div>
        <div className="dialog-foot">
          <button type="button" className="btn btn-quiet" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn btn-primary" disabled={saving}>
            {saving ? 'Saving…' : job ? 'Save changes' : 'Create job'}
          </button>
        </div>
      </form>
    </div>
  );
}
