import { accessToken } from './auth';
import type { CandidateDetail, CandidateSummary, Job, JobInput, Stage, UploadTicket } from './types';

const API_URL = (import.meta.env.VITE_API_URL ?? 'http://localhost:8001').replace(/\/$/, '');

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

let onSignedOut: (() => void) | null = null;
export function setSignedOutHandler(fn: (() => void) | null): void {
  onSignedOut = fn;
}

async function raw(path: string, init: RequestInit = {}): Promise<Response> {
  const token = await accessToken();
  if (!token) {
    onSignedOut?.();
    throw new ApiError(401, 'Your session ended. Sign in again.');
  }
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: { Authorization: `Bearer ${token}`, ...(init.body ? { 'Content-Type': 'application/json' } : {}), ...init.headers },
    });
  } catch {
    throw new ApiError(0, "Can't reach the server. Check your connection and try again.");
  }
  if (res.status === 401) {
    onSignedOut?.();
    throw new ApiError(401, 'Your session ended. Sign in again.');
  }
  if (!res.ok) {
    const body = await res.json().catch(() => null) as { message?: string } | null;
    throw new ApiError(res.status, body?.message ?? `Request failed (${res.status})`);
  }
  return res;
}

async function json<T>(path: string, init: RequestInit = {}): Promise<T> {
  return (await raw(path, init)).json() as Promise<T>;
}

const send = (method: string, body?: unknown): RequestInit => ({ method, body: body === undefined ? undefined : JSON.stringify(body) });

export const api = {
  listJobs: () => json<Job[]>('/jobs'),
  createJob: (input: JobInput) => json<Job>('/jobs', send('POST', input)),
  updateJob: (id: string, input: Partial<JobInput>) => json<Job>(`/jobs/${id}`, send('PUT', input)),
  deleteJob: (id: string) => json<{ deleted: boolean }>(`/jobs/${id}`, send('DELETE')),
  rescore: (id: string) => json<{ rescored: number }>(`/jobs/${id}/rescore`, send('POST', {})),
  suggestSkills: (text: string) => json<{ skills: string[] }>('/skills/suggest', send('POST', { text })),

  candidates: (jobId: string) => json<CandidateSummary[]>(`/jobs/${jobId}/candidates`),
  candidate: (jobId: string, id: string) => json<CandidateDetail>(`/jobs/${jobId}/candidates/${id}`),
  updateCandidate: (jobId: string, id: string, patch: { stage?: Stage; notes?: string }) =>
    json<CandidateSummary>(`/jobs/${jobId}/candidates/${id}`, send('PATCH', patch)),
  deleteCandidate: (jobId: string, id: string) => json<{ deleted: boolean }>(`/jobs/${jobId}/candidates/${id}`, send('DELETE')),

  requestUploads: (jobId: string, files: File[]) =>
    json<{ uploads: UploadTicket[] }>(`/jobs/${jobId}/uploads`, send('POST', { files: files.map(f => ({ filename: f.name, size: f.size })) })),

  async exportCsv(jobId: string): Promise<{ blob: Blob; filename: string }> {
    const res = await raw(`/jobs/${jobId}/export`);
    const disposition = res.headers.get('content-disposition') ?? '';
    const filename = /filename="([^"]+)"/.exec(disposition)?.[1] ?? 'candidates.csv';
    return { blob: await res.blob(), filename };
  },
};

/**
 * Upload a file straight to S3 using a presigned POST form (the API never sees the bytes).
 * Uses XHR rather than fetch so we can report progress.
 */
export function uploadToS3(ticket: UploadTicket, file: File, onProgress: (pct: number) => void): Promise<void> {
  return new Promise((resolve, reject) => {
    const form = new FormData();
    Object.entries(ticket.fields).forEach(([k, v]) => form.append(k, v));
    form.append('file', file); // S3 requires the file to be the last field
    const xhr = new XMLHttpRequest();
    xhr.open('POST', ticket.url);
    xhr.upload.onprogress = e => { if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 100)); };
    xhr.onload = () => (xhr.status >= 200 && xhr.status < 300 ? resolve() : reject(new Error(
      xhr.status === 400 && /EntityTooLarge/.test(xhr.responseText) ? 'File is too large' : `Upload failed (${xhr.status})`,
    )));
    xhr.onerror = () => reject(new Error('Upload failed. Check your connection.'));
    xhr.send(form);
  });
}
