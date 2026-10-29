/**
 * Sign-in.
 *  - cognito: Cognito hosted sign-in with the OAuth 2.0 authorization code flow + PKCE
 *    (no client secret in the browser, no auth library needed).
 *  - local:   for backend/local_server.py; the "token" is just the email address.
 */

const env = import.meta.env;
export const authMode: 'local' | 'cognito' = env.VITE_AUTH_MODE === 'cognito' ? 'cognito' : 'local';

const DOMAIN = (env.VITE_COGNITO_DOMAIN ?? '').replace(/\/$/, '');
const CLIENT_ID = env.VITE_COGNITO_CLIENT_ID ?? '';
const REDIRECT_URI = env.VITE_REDIRECT_URI ?? `${window.location.origin}/`;

const KEY = 'rs.session';
const PKCE_KEY = 'rs.pkce';

export interface Session {
  email: string;
  accessToken: string;
  refreshToken?: string;
  expiresAt: number; // epoch ms
}

function read(key: string): string | null {
  try { return sessionStorage.getItem(key); } catch { return null; }
}
function write(key: string, value: string | null): void {
  try {
    if (value === null) sessionStorage.removeItem(key);
    else sessionStorage.setItem(key, value);
  } catch { /* private mode: session lasts until reload */ }
}

let memory: Session | null = null;

export function currentSession(): Session | null {
  if (memory) return memory;
  const raw = read(KEY);
  memory = raw ? (JSON.parse(raw) as Session) : null;
  return memory;
}

function save(session: Session | null): void {
  memory = session;
  write(KEY, session ? JSON.stringify(session) : null);
}

// ─── Local mode ──────────────────────────────────────────────────────────────

export function localSignIn(email: string): Session {
  const session = { email: email.trim().toLowerCase(), accessToken: `local:${email.trim().toLowerCase()}`, expiresAt: Infinity };
  save(session);
  return session;
}

// ─── Cognito (authorization code + PKCE) ─────────────────────────────────────

function base64url(bytes: ArrayBuffer | Uint8Array): string {
  const arr = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  let s = '';
  arr.forEach(b => { s += String.fromCharCode(b); });
  return btoa(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function randomString(bytes = 32): string {
  return base64url(crypto.getRandomValues(new Uint8Array(bytes)));
}

export async function cognitoSignIn(signUp = false): Promise<void> {
  const verifier = randomString(48);
  const state = randomString(16);
  const challenge = base64url(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier)));
  write(PKCE_KEY, JSON.stringify({ verifier, state }));
  const params = new URLSearchParams({
    response_type: 'code',
    client_id: CLIENT_ID,
    redirect_uri: REDIRECT_URI,
    scope: 'openid email profile',
    code_challenge_method: 'S256',
    code_challenge: challenge,
    state,
  });
  window.location.assign(`${DOMAIN}/${signUp ? 'signup' : 'oauth2/authorize'}?${params}`);
}

function decodeJwt(token: string): Record<string, unknown> {
  const part = token.split('.')[1] ?? '';
  const bytes = Uint8Array.from(atob(part.replace(/-/g, '+').replace(/_/g, '/')), c => c.charCodeAt(0));
  return JSON.parse(new TextDecoder().decode(bytes));
}

async function tokenRequest(body: Record<string, string>): Promise<Session> {
  const res = await fetch(`${DOMAIN}/oauth2/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ client_id: CLIENT_ID, ...body }),
  });
  if (!res.ok) throw new Error('Sign-in failed. Try again.');
  const data = await res.json() as { access_token: string; id_token: string; refresh_token?: string; expires_in: number };
  const claims = decodeJwt(data.id_token);
  return {
    email: String(claims.email ?? ''),
    accessToken: data.access_token,
    refreshToken: data.refresh_token ?? body.refresh_token,
    expiresAt: Date.now() + data.expires_in * 1000,
  };
}

/** Finish sign-in when Cognito redirects back with ?code=... Returns the session, if any. */
export async function completeSignIn(): Promise<Session | null> {
  if (authMode !== 'cognito') return currentSession();
  const url = new URL(window.location.href);
  const code = url.searchParams.get('code');
  if (!code) return currentSession();

  const pkce = JSON.parse(read(PKCE_KEY) ?? '{}') as { verifier?: string; state?: string };
  write(PKCE_KEY, null);
  window.history.replaceState({}, '', url.pathname);
  if (!pkce.verifier || pkce.state !== url.searchParams.get('state')) {
    throw new Error('Sign-in expired. Please sign in again.');
  }
  const session = await tokenRequest({ grant_type: 'authorization_code', code, redirect_uri: REDIRECT_URI, code_verifier: pkce.verifier });
  save(session);
  return session;
}

/** A valid access token, refreshing it first if it's about to expire. */
export async function accessToken(): Promise<string | null> {
  const s = currentSession();
  if (!s) return null;
  if (s.expiresAt - Date.now() > 60_000) return s.accessToken;
  if (authMode === 'cognito' && s.refreshToken) {
    try {
      const fresh = await tokenRequest({ grant_type: 'refresh_token', refresh_token: s.refreshToken });
      save(fresh);
      return fresh.accessToken;
    } catch { /* fall through to signed out */ }
  }
  save(null);
  return null;
}

export function signOut(): void {
  save(null);
  if (authMode === 'cognito' && DOMAIN) {
    const params = new URLSearchParams({ client_id: CLIENT_ID, logout_uri: REDIRECT_URI });
    window.location.assign(`${DOMAIN}/logout?${params}`);
  }
}
