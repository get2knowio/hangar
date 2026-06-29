/* Shared modal dialog: a click-dismissable backdrop + panel that is keyboard-complete —
   Escape closes, focus moves into the panel on open and is restored on close, and Tab is
   trapped inside so it can't wander to the page behind. Used by every modal so dialog
   accessibility lives in one place. */

import { useEffect, useRef, type ReactNode } from "react";

export function Modal({
  onClose,
  label,
  width = 460,
  children,
}: {
  onClose: () => void;
  label: string;
  width?: number;
  children: ReactNode;
}) {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const restoreTo = document.activeElement as HTMLElement | null;
    const focusables = () =>
      Array.from(
        panelRef.current?.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ) ?? [],
      );
    (focusables()[0] ?? panelRef.current)?.focus();

    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
        return;
      }
      if (e.key === "Tab") {
        const items = focusables();
        if (items.length === 0) {
          e.preventDefault();
          return;
        }
        const first = items[0];
        const last = items[items.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    }
    document.addEventListener("keydown", onKey, true);
    return () => {
      document.removeEventListener("keydown", onKey, true);
      restoreTo?.focus?.();
    };
  }, [onClose]);

  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed", inset: 0, background: "rgba(0,0,0,.35)", zIndex: 90,
        display: "flex", alignItems: "center", justifyContent: "center",
      }}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={label}
        tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 10,
          padding: "20px 22px", width, maxHeight: "85vh", overflowY: "auto",
          boxShadow: "0 12px 40px rgba(0,0,0,.3)", outline: "none",
        }}
      >
        {children}
      </div>
    </div>
  );
}
