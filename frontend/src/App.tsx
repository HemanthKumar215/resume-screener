import { useCallback, useEffect, useState } from 'react';
import { api, setSignedOutHandler } from './api';
import { completeSignIn, currentSession, signOut, type Session } from './auth';
import { JobDialog } from './components/JobDialog';
import { JobView } from './components/JobView';
import { SignIn } from './components/SignIn';
import type { Job } from './types';

export default function App() {
  const [session, setSession] = useState<Session | null>(() => currentSession());
  const [signInError, setSignInError] = useState<string | null>(null);
  const [checking, setChecking] = useState(() => new URL(window.location.href).searchParams.has('code'));

  useEffect(() => {
    if (!checking) return;
    completeSignIn()
      .then(setSession)
      .catch(e => setSignInError((e as Error).message))
      .finally(() => setChecking(false));
  }, [checking]);

  useEffect(() => {
    setSignedOutHandler(() => setSession(null));
    return () => setSignedOutHandler(null);
  }, []);

  if (checking) return <div className="signin"><p className="pending">Signing you in…</p></div>;
  if (!session) return <SignIn onSignedIn={setSession} error={signInError} />;
  return <Workspace session={session} onSignOut={() => { signOut(); setSession(null); }} />;
}

function Workspace({ session, onSignOut }: { session: Session; onSignOut: () => void }) {
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [dialog, setDialog] = useState<'new' | 'edit' | null>(null);
  const [toast, setToast] = useState<{ msg: string; kind: 'ok' | 'err' } | null>(null);

  const notify = useCallback((msg: string, kind: 'ok' | 'err' = 'ok') => setToast({ msg, kind }), []);

  const loadJobs = useCallback(async () => {
    try {
      const list = await api.listJobs();
      setJobs(list);
      setSelectedId(cur => (cur && list.some(j => j.id === cur) ? cur : list[0]?.id ?? null));
    } catch (e) {
      notify((e as Error).message, 'err');
      setJobs(j => j ?? []);
    }
  }, [notify]);

  useEffect(() => {
    let cancelled = false;
    api.listJobs()
      .then(list => { if (!cancelled) { setJobs(list); setSelectedId(list[0]?.id ?? null); } })
      .catch(e => { if (!cancelled) { notify((e as Error).message, 'err'); setJobs([]); } });
    return () => { cancelled = true; };
  }, [notify]);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), toast.kind === 'err' ? 6000 : 3000);
    return () => clearTimeout(t);
  }, [toast]);

  const job = jobs?.find(j => j.id === selectedId) ?? null;

  const onSaved = async (saved: Job, requirementsChanged: boolean) => {
    setDialog(null);
    setSelectedId(saved.id);
    if (requirementsChanged && saved.candidate_count > 0) {
      try {
        const { rescored } = await api.rescore(saved.id);
        notify(`Requirements saved. Re-scored ${rescored} candidate${rescored === 1 ? '' : 's'}.`);
      } catch (e) {
        notify((e as Error).message, 'err');
      }
    } else {
      notify(dialog === 'new' ? 'Job created. Now add some resumes.' : 'Requirements saved.');
    }
    await loadJobs();
  };

  return (
    <div className="app">
      <nav className="rail" aria-label="Jobs">
        <div className="rail-head">
          <img src="/favicon.svg" alt="" width={26} height={26} />
          <span className="brand">Resume Screener</span>
          <button className="btn btn-primary" onClick={() => setDialog('new')}>New job</button>
        </div>
        <div className="rail-list">
          {jobs?.map(j => (
            <button key={j.id} className="rail-item" aria-current={j.id === selectedId ? 'page' : undefined} onClick={() => setSelectedId(j.id)}>
              <span className="t">{j.title}</span>
              <span className="m num">{j.candidate_count} {j.candidate_count === 1 ? 'resume' : 'resumes'}</span>
            </button>
          ))}
        </div>
        <div className="rail-foot">
          <span className="who" title={session.email}>{session.email}</span>
          <button className="btn btn-quiet" style={{ justifySelf: 'start', padding: '4px 0' }} onClick={onSignOut}>Sign out</button>
        </div>
      </nav>

      <main className="main">
        {jobs === null && <div className="page"><p className="pending">Loading your jobs…</p></div>}
        {jobs !== null && !job && (
          <div className="page">
            <div className="empty" style={{ paddingTop: 96 }}>
              <h2>Start with a job</h2>
              <p style={{ maxWidth: 460 }}>
                Paste the job description and pick the skills that matter. Then drop in resumes and they'll be ranked against it.
              </p>
              <button className="btn btn-primary" onClick={() => setDialog('new')}>Create a job</button>
            </div>
          </div>
        )}
        {job && (
          <JobView
            key={job.id}
            job={job}
            onEdit={() => setDialog('edit')}
            onDeleted={() => { notify('Job deleted.'); setSelectedId(null); loadJobs(); }}
            onJobChanged={loadJobs}
            notify={notify}
          />
        )}
      </main>

      {dialog && (
        <JobDialog job={dialog === 'edit' ? job : null} onClose={() => setDialog(null)} onSaved={onSaved} />
      )}
      {toast && <div className={`toast${toast.kind === 'err' ? ' err' : ''}`} role="status">{toast.msg}</div>}
    </div>
  );
}
