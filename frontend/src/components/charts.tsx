import type { ReactNode } from "react";

/** Deterministic molecule glyph (hexagon + substituents) — visual only. */
export function MolGlyph({ seed, size = 46 }: { seed: number; size?: number }) {
  let s = (seed + 7) * 9301 + 49297;
  const rnd = () => {
    s = (s * 9301 + 49297) % 233280;
    return s / 233280;
  };
  const cx = size / 2;
  const cy = size / 2;
  const r = size * 0.25;
  const pts: [number, number][] = [];
  for (let i = 0; i < 6; i++) {
    const a = Math.PI / 6 + (i * Math.PI) / 3;
    pts.push([cx + r * Math.cos(a), cy + r * Math.sin(a)]);
  }
  const bonds: ReactNode[] = [];
  for (let i = 0; i < 6; i++) {
    const p = pts[i];
    const q = pts[(i + 1) % 6];
    bonds.push(<line key={`b${i}`} className="bond" x1={p[0]} y1={p[1]} x2={q[0]} y2={q[1]} />);
  }
  const atoms: ReactNode[] = [];
  const n = 1 + Math.floor(rnd() * 3);
  for (let i = 0; i < n; i++) {
    const p = pts[Math.floor(rnd() * 6)];
    const a = Math.atan2(p[1] - cy, p[0] - cx);
    const len = size * 0.18 + rnd() * size * 0.07;
    const ex = p[0] + len * Math.cos(a);
    const ey = p[1] + len * Math.sin(a);
    bonds.push(<line key={`s${i}`} className="bond" x1={p[0]} y1={p[1]} x2={ex} y2={ey} />);
    atoms.push(
      <circle key={`a${i}`} className={`atom ${rnd() > 0.5 ? "hetero" : ""}`} cx={ex} cy={ey} r={size * 0.055} />,
    );
  }
  atoms.push(<circle key="c" className="atom" cx={cx} cy={cy} r={size * 0.05} />);
  return (
    <svg className="mol" width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden="true">
      {bonds}
      {atoms}
    </svg>
  );
}

/** Radar chart for drug-likeness endpoints. */
export function RadarChart({ axes, size = 240 }: { axes: { label: string; a: number; b?: number }[]; size?: number }) {
  const c = size / 2;
  const R = size * 0.36;
  const n = axes.length;
  const pt = (i: number, v: number): [number, number] => {
    const a = -Math.PI / 2 + (i * 2 * Math.PI) / n;
    return [c + R * v * Math.cos(a), c + R * v * Math.sin(a)];
  };
  const poly = (key: "a" | "b", color: string) => {
    const points = axes.map((ax, i) => pt(i, (ax[key] as number) ?? 0).join(",")).join(" ");
    return <polygon points={points} fill={color} fillOpacity={0.18} stroke={color} strokeWidth={2} />;
  };
  return (
    <svg className="chart" viewBox={`0 0 ${size} ${size}`} role="img">
      {[0.25, 0.5, 0.75, 1].map((r) => (
        <polygon key={r} className="radar-ring" points={axes.map((_, i) => pt(i, r).join(",")).join(" ")} />
      ))}
      {axes.map((ax, i) => {
        const [x, y] = pt(i, 1);
        return <line key={`sp${i}`} className="radar-spoke" x1={c} y1={c} x2={x} y2={y} />;
      })}
      {axes.map((ax, i) => {
        const [x, y] = pt(i, 1.22);
        return (
          <text key={`lb${i}`} className="tick" x={x} y={y} textAnchor="middle">
            {ax.label}
          </text>
        );
      })}
      {axes.some((a) => a.b != null) && poly("b", "#7f8da6")}
      {poly("a", "#3dd6c4")}
    </svg>
  );
}

/** Retrosynthetic route diagram. */
export function RouteDiagram({ steps }: { steps: string[] }) {
  return (
    <div className="route">
      {steps.map((s, i) => (
        <span key={i} style={{ display: "contents" }}>
          {i > 0 && <span className="route-arrow">→</span>}
          <span className={`route-node${i === steps.length - 1 ? " final" : ""}`}>{s}</span>
        </span>
      ))}
    </div>
  );
}

/** Horizontal meter with label. */
export function Meter({ label, value, max = 1, tone = "accent" }: { label: string; value: number; max?: number; tone?: string }) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <div className="endpoint">
      <div className="ep-head">
        <span>{label}</span>
        <span>{value.toFixed(2)}</span>
      </div>
      <div className="ep-bar">
        <span
          style={{
            width: `${pct}%`,
            background: tone === "pass" ? "#35d39a" : tone === "warn" ? "#f5b544" : tone === "fail" ? "#f2707a" : "linear-gradient(90deg,#3dd6c4,#5b8cff)",
          }}
        />
      </div>
    </div>
  );
}
