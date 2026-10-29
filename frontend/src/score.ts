import type { ScoreComponent } from './types';

export const SEGMENT_COLORS: Record<ScoreComponent['key'], string> = {
  required_skills: 'var(--seg-required)',
  nice_skills: 'var(--seg-nice)',
  experience: 'var(--seg-experience)',
  education: 'var(--seg-education)',
  relevance: 'var(--seg-relevance)',
};

export const SEGMENT_LABELS: Record<ScoreComponent['key'], string> = {
  required_skills: 'Required skills',
  nice_skills: 'Nice-to-have',
  experience: 'Experience',
  education: 'Education',
  relevance: 'Keyword relevance',
};

/** Points a component contributed to the 0-100 score. */
export const points = (c: Pick<ScoreComponent, 'weight' | 'score'>) => c.weight * c.score;

export function tierClass(tier: string | null | undefined): string {
  if (!tier) return '';
  return `tier-${tier.split(' ')[0].toLowerCase()}`;
}

export function describeComponents(components: Pick<ScoreComponent, 'key' | 'weight' | 'score'>[]): string {
  return components.map(c => `${SEGMENT_LABELS[c.key]} ${Math.round(points(c))} of ${c.weight}`).join(', ');
}
