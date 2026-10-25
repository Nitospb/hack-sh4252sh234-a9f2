"use client";

import { useRef, type CSSProperties, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { useModal } from "@/src/hooks/useModal";
import { getFocusableElements } from "@/src/utils/focus";
import styles from "./Drawer.module.css";

interface DrawerProps {
  id: string;
  open: boolean;
  label: string;
  children: ReactNode;
  onClose: () => void;
  closeLabel?: string;
  width?: CSSProperties["width"];
}

const Drawer = ({
  id,
  open,
  label,
  children,
  onClose,
  closeLabel = "Закрыть",
  width,
}: DrawerProps) => {
  const ref = useRef<HTMLDivElement>(null);
  useModal(open, ref);

  if (!open) return null;

  return createPortal(
    <div
      className={styles.Drawer}
      role="presentation"
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        ref={ref}
        id={id}
        role="dialog"
        aria-label={label}
        aria-modal="true"
        tabIndex={-1}
        className={styles.panel}
        style={{ width }}
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            event.preventDefault();
            onClose();
            return;
          }

          if (event.key !== "Tab") return;

          const elements = getFocusableElements(event.currentTarget);
          const first = elements[0];
          const last = elements[elements.length - 1];

          if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last?.focus();
          } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first?.focus();
          }
        }}
      >
        <button
          type="button"
          className={styles.close}
          aria-label={closeLabel}
          onClick={onClose}
        >
          <svg
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            aria-hidden="true"
          >
            <path d="m6 6 12 12M18 6 6 18" />
          </svg>
        </button>
        {children}
      </div>
    </div>,
    document.body,
  );
};

export default Drawer;
