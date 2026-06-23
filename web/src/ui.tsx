// Small shared UI primitives + hand-rolled SVG-free viz (keeps the dependency surface tiny).
import { useState, type ReactNode } from "react";

export function Pill({ kind, children }: { kind: string; children: ReactNode }) {
  return (
    <span className={`pill ${kind}`}>
      {(kind === "published" || kind === "draft") && <span className="dot-led" />}
      {children}
    </span>
  );
}

export function StatusPill({ status }: { status: "draft" | "published" }) {
  return <Pill kind={status}>{status}</Pill>;
}

export function PassPill({ passed }: { passed: boolean | null }) {
  if (passed === null) return <span className="faint">—</span>;
  return <Pill kind={passed ? "pass" : "fail"}>{passed ? "passed" : "not yet"}</Pill>;
}

export function Stat({ value, label }: { value: ReactNode; label: string }) {
  return (
    <div className="stat">
      <div className="v">{value}</div>
      <div className="k">{label}</div>
    </div>
  );
}

export function Bar({ value }: { value: number | null }) {
  const pct = value === null ? 0 : Math.round(value * 100);
  return (
    <div className="row" style={{ gap: 10 }}>
      <div className="bar-track" style={{ width: 120 }}>
        <div className="bar-fill" style={{ width: `${pct}%` }} />
      </div>
      <span className="mono faint" style={{ fontSize: "0.8rem" }}>
        {value === null ? "—" : `${pct}%`}
      </span>
    </div>
  );
}

export function CopyField({ value }: { value: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="copy">
      <code>{value}</code>
      <button
        onClick={async () => {
          try {
            await navigator.clipboard.writeText(value);
          } catch {
            /* clipboard blocked; user can still select */
          }
          setCopied(true);
          setTimeout(() => setCopied(false), 1400);
        }}
      >
        {copied ? "copied" : "copy"}
      </button>
    </div>
  );
}

export function fmtDuration(seconds: number | null): string {
  if (seconds === null || seconds === undefined) return "—";
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  if (m < 60) return `${m}m ${seconds % 60}s`;
  return `${Math.floor(m / 60)}h ${m % 60}m`;
}

export function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

export function asLines(v: string | string[] | undefined): string {
  if (!v) return "";
  return Array.isArray(v) ? v.join("; ") : v;
}

export function Spinner() {
  return <div className="empty faint">Loading…</div>;
}

export function ErrorBanner({ message }: { message: string }) {
  return <div className="error-banner">{message}</div>;
}
