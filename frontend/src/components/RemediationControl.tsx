/* Remediation control (prototype `buildCtl` controls): renders the resolved action for a
   finding and drives the state machine via the API. Report-only / Open-in-provider /
   Enable / Open fix PR → PR #n open ↗ + Mark merged → fixed. Toast on every action
   (FR-011–FR-018; SC-002 — every failing finding offers ≥1 path, Report always available). */

import { useToast } from "../app/state";
import { useMarkMerged, useRemediate, type RemediationKind } from "../lib/api";

interface Check {
  id?: string;
  label?: string;
  status?: string;
  open_pr_url?: string | null;
  primary_action?: string | null;
  secondary_action?: string | null;
}

function kindFor(primary: string): RemediationKind {
  if (primary.startsWith("Open in")) return "deep_link";
  if (primary === "Enable") return "settings_patch";
  if (primary === "Open fix PR") return "config_pr";
  return "report";
}

function prNumber(url: string | null | undefined): string {
  if (!url) return "";
  const m = url.match(/\/pull\/(\d+)/);
  return m ? `#${m[1]}` : "";
}

export function RemediationControl({
  connectionId,
  repoId,
  check,
}: {
  connectionId: string;
  repoId: string;
  check: Check;
}) {
  const remediate = useRemediate(connectionId, repoId);
  const merge = useMarkMerged(connectionId, repoId);
  const { show } = useToast();
  const status = check.status ?? "fail";

  if (status === "pass") {
    return <Note text="Pass" color="var(--muted)" />;
  }
  if (status === "working") {
    return <Note text="Working…" color="var(--warn)" />;
  }
  if (status === "pending") {
    return (
      <>
        <a
          href={check.open_pr_url ?? "#"}
          target="_blank"
          rel="noreferrer"
          style={{ fontSize: 12, fontWeight: 600, color: "var(--warn)", whiteSpace: "nowrap", textDecoration: "none" }}
        >
          PR {prNumber(check.open_pr_url)} open ↗
        </a>
        <Button
          label="Mark merged"
          variant="secondary"
          onClick={() => {
            merge.mutate(check.id!, {
            onSuccess: () => show(`Merged · ${check.label}`),
            onError: () => show(`Couldn't mark merged · ${check.label}`),
          });
          }}
        />
      </>
    );
  }

  // fail / unknown
  const primary = check.primary_action;
  if (!primary) {
    return <Note text="Report only" color="var(--muted)" />;
  }

  const kind = kindFor(primary);
  return (
    <Button
      label={primary}
      variant="primary"
      onClick={() => {
        remediate.mutate(
          { checkId: check.id!, kind },
          {
            onSuccess: (r) => {
              if (kind === "deep_link") {
                show("Opening provider →");
                if (r.pr_url) window.open(r.pr_url, "_blank");
              } else if (kind === "config_pr") {
                show(`Opened fix PR · ${repoId}`);
              } else if (kind === "settings_patch") {
                show(`Applied · ${check.label}`);
              } else {
                show(`Reported · ${check.label}`);
              }
            },
            onError: () => show(`Remediation failed · ${check.label}`),
          },
        );
      }}
    />
  );
}

function Note({ text, color }: { text: string; color: string }) {
  return <span style={{ fontSize: 12, fontWeight: 600, color, whiteSpace: "nowrap" }}>{text}</span>;
}

function Button({
  label,
  variant,
  onClick,
}: {
  label: string;
  variant: "primary" | "secondary";
  onClick: () => void;
}) {
  const primary = variant === "primary";
  return (
    <div
      onClick={onClick}
      style={{
        fontSize: 12,
        fontWeight: 600,
        color: primary ? "var(--bg)" : "var(--fg-2)",
        background: primary ? "var(--fg)" : "transparent",
        border: `1px solid ${primary ? "var(--fg)" : "var(--border)"}`,
        borderRadius: 6,
        padding: primary ? "6px 13px" : "6px 12px",
        cursor: "pointer",
        whiteSpace: "nowrap",
        display: "flex",
        alignItems: "center",
        gap: 6,
      }}
    >
      {label}
    </div>
  );
}
