import type { ScoreComponent } from '../types';
import { SEGMENT_COLORS, points } from '../score';

/**
 * The score, decomposed: each segment's width is the points that criterion earned,
 * so the filled length equals the score and the colours show where it came from.
 */
export function FitBar({ components, big = false, label }: {
  components: Pick<ScoreComponent, 'key' | 'weight' | 'score'>[];
  big?: boolean;
  label: string;
}) {
  return (
    <div className={`fit-bar${big ? ' big' : ''}`} role="img" aria-label={label}>
      {components.map(c => (
        <i key={c.key} style={{ width: `${points(c)}%`, background: SEGMENT_COLORS[c.key] }} />
      ))}
    </div>
  );
}
