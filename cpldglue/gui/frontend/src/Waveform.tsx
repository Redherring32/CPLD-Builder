/** Simple digital waveform: one row per signal, one column per sim step. */
export type Sample = Record<string, number | null>;

const ROW = 20, STEP = 14, LABEL = 110, HI = 4, LO = 15;

export function Waveform({ names, samples }: { names: string[]; samples: Sample[] }) {
  if (!samples.length) return <div className="muted small">Change an input to start recording.</div>;
  const w = LABEL + samples.length * STEP + 4;
  const h = names.length * ROW + 4;
  return (
    <div className="wave" data-testid="waveform">
      <svg width={w} height={h} role="img" aria-label="Waveform of the last simulation steps">
        {names.map((name, r) => {
          const y0 = r * ROW + 2;
          // Build the trace: high/low lines with vertical edges; Z/X as a dashed midline.
          const parts: { d: string; z: boolean }[] = [];
          let d = "", prev: number | null | undefined = undefined;
          samples.forEach((s, i) => {
            const v = s[name];
            const x = LABEL + i * STEP;
            const z = v === null || v === undefined;
            const y = z ? y0 + (HI + LO) / 2 : y0 + (v ? HI : LO);
            if (prev === undefined || (prev === null) !== z) {
              if (d) parts.push({ d, z: prev === null || prev === undefined });
              d = `M${x},${y}`;
            } else if (!z && prev !== v) {
              d += ` L${x},${y}`;
            }
            d += ` L${x + STEP},${y}`;
            prev = z ? null : v;
          });
          if (d) parts.push({ d, z: prev === null });
          return (
            <g key={name}>
              <text x={4} y={y0 + 13} className="wname">{name}</text>
              <line x1={LABEL} x2={w} y1={y0 + ROW - 1} y2={y0 + ROW - 1} className="wgrid" />
              {parts.map((p, i) => <path key={i} d={p.d} className={p.z ? "wz" : "wv"} />)}
            </g>
          );
        })}
      </svg>
    </div>
  );
}
