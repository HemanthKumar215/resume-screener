import { useState } from 'react';
import { authMode, cognitoSignIn, localSignIn, type Session } from '../auth';

export function SignIn({ onSignedIn, error }: { onSignedIn: (s: Session) => void; error?: string | null }) {
  const [email, setEmail] = useState('demo@example.com');

  return (
    <div className="signin">
      <div className="signin-card">
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <img src="/favicon.svg" alt="" width={32} height={32} />
          <span className="brand">Resume Screener</span>
        </div>
        <div style={{ display: 'grid', gap: 10 }}>
          <h1>Rank every resume against the job, and see why.</h1>
          <p>
            Upload a stack of resumes. Each one is read, scored on skills, experience, education and relevance,
            and ranked, with the reasons laid out so you can decide quickly.
          </p>
        </div>

        {error && <p className="error-text" role="alert">{error}</p>}

        {authMode === 'cognito' ? (
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <button className="btn btn-primary" onClick={() => cognitoSignIn()}>Sign in</button>
            <button className="btn" onClick={() => cognitoSignIn(true)}>Create an account</button>
          </div>
        ) : (
          <form className="signin-demo" onSubmit={e => { e.preventDefault(); if (email.trim()) onSignedIn(localSignIn(email)); }}>
            <div className="field">
              <label htmlFor="email">Email</label>
              <input id="email" className="input" type="email" required value={email} onChange={e => setEmail(e.target.value)} />
            </div>
            <button className="btn btn-primary" type="submit">Continue</button>
            <p className="hint">
              Local mode: no password needed. Each email gets its own jobs. <code>demo@example.com</code> has a sample job if
              the server was started with <code>--seed</code>.
            </p>
          </form>
        )}
      </div>
    </div>
  );
}
