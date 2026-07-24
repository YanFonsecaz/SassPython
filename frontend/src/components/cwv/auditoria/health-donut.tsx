"use client";

// Donut de health score (SPEC_CWV_Auditoria_UI_V2 §3.1): SVG puro, % central.
// Verde = pass, vermelho = fail — mesmas cores dos badges do checklist.
// Determinístico em jsdom (sem ResponsiveContainer).

interface HealthDonutProps {
  pass: number | null;
  fail: number | null;
  label: string;
  hint?: string;
  size?: number;
}

export function HealthDonut({ pass, fail, label, hint, size = 140 }: HealthDonutProps) {
  const total = (pass ?? 0) + (fail ?? 0);
  const vazio = pass === null || fail === null || total === 0;
  const pct = vazio ? 0 : Math.round(((pass ?? 0) / total) * 100);

  const stroke = size * 0.11;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const passLen = (pct / 100) * c;

  return (
    <div className="flex flex-col items-center gap-1" data-testid={`donut-${label.toLowerCase()}`}>
      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        role="img"
        aria-label={`${label}: ${vazio ? "sem dados" : `${pct}% aprovado`}`}
      >
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          className={vazio ? "stroke-muted" : "stroke-destructive/70"}
          strokeWidth={stroke}
        />
        {!vazio && (
          <circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            className="stroke-success"
            strokeWidth={stroke}
            strokeDasharray={`${passLen} ${c - passLen}`}
            strokeDashoffset={c / 4}
            strokeLinecap="round"
          />
        )}
        <text
          x="50%"
          y="50%"
          dominantBaseline="central"
          textAnchor="middle"
          className="fill-foreground font-bold"
          fontSize={size * 0.2}
        >
          {vazio ? "—" : `${pct}%`}
        </text>
      </svg>
      <p className="text-xs font-medium text-muted-foreground">{label}</p>
      {vazio ? (
        hint && <p className="text-[11px] text-muted-foreground">{hint}</p>
      ) : (
        <p className="text-[11px] text-muted-foreground">
          <span className="text-success">✔ {pass}</span> ·{" "}
          <span className="text-destructive">✖ {fail}</span>
        </p>
      )}
    </div>
  );
}
