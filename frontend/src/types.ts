export type Education = 'None' | 'Diploma' | "Bachelor's" | "Master's" | 'Doctorate';
export type Stage = 'new' | 'shortlisted' | 'interview' | 'rejected';
export type CandidateStatus = 'UPLOADING' | 'PROCESSING' | 'SCORED' | 'FAILED';

export interface Job {
  id: string;
  title: string;
  description: string;
  required_skills: string[];
  nice_to_have_skills: string[];
  min_years: number;
  min_education: Education;
  alert_threshold: number;
  candidate_count: number;
  created_at: string;
  updated_at: string;
}

export type JobInput = Omit<Job, 'id' | 'candidate_count' | 'created_at' | 'updated_at'>;

export interface CandidateSummary {
  id: string;
  job_id: string;
  filename: string;
  status: CandidateStatus;
  error: string;
  score: number | null;
  tier: string | null;
  name: string;
  email: string;
  stage: Stage;
  created_at: string;
  scored_at: string | null;
  matched_required: string[];
  missing_required: string[];
  experience_years: number | null;
  education: Education | null;
  components: Pick<ScoreComponent, 'key' | 'weight' | 'score'>[];
}

export interface ScoreComponent {
  key: 'required_skills' | 'nice_skills' | 'experience' | 'education' | 'relevance';
  label: string;
  weight: number;
  score: number;
  detail: string;
}

export interface ScoreResult {
  score: number;
  tier: string;
  components: ScoreComponent[];
  matched_required: string[];
  missing_required: string[];
  matched_nice: string[];
  missing_nice: string[];
  skills_found: string[];
  experience: { years: number; source: 'dates' | 'claim' | 'none'; ranges: string[] };
  education: Education;
  contact: { name: string; email: string; phone: string; linkedin: string; github: string };
  highlights: string[];
  concerns: string[];
}

export interface CandidateDetail extends Omit<CandidateSummary, 'matched_required' | 'missing_required' | 'experience_years' | 'education' | 'components'> {
  result?: ScoreResult;
  notes: string;
  summary?: string;
  method?: string;
  download_url?: string;
}

export interface UploadTicket {
  candidate_id: string;
  filename: string;
  url: string;
  fields: Record<string, string>;
}
