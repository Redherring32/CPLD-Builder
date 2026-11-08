import { useEffect, useRef } from "react";

export interface MenuItem {
  label: string;
  onClick: () => void;
  danger?: boolean;
  disabled?: boolean;
}

export function ContextMenu({ x, y, title, items, onClose }: {
  x: number; y: number; title: string; items: MenuItem[]; onClose: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const away = (e: Event) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("mousedown", away);
    window.addEventListener("keydown", esc);
    ref.current?.querySelector<HTMLButtonElement>("button:not([disabled])")?.focus();
    return () => {
      window.removeEventListener("mousedown", away);
      window.removeEventListener("keydown", esc);
    };
  }, [onClose]);

  // Keep the menu on screen.
  const left = Math.min(x, window.innerWidth - 220);
  const top = Math.min(y, window.innerHeight - (items.length * 30 + 40));
  return (
    <div className="ctxmenu" style={{ left, top }} ref={ref} role="menu">
      <div className="ctxtitle">{title}</div>
      {items.map((it) => (
        <button key={it.label} role="menuitem" disabled={it.disabled}
                className={it.danger ? "danger" : ""}
                onClick={() => { it.onClick(); onClose(); }}>
          {it.label}
        </button>
      ))}
    </div>
  );
}
