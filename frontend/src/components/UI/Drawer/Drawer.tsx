"use client";

import { useEffect, useRef, useState, type CSSProperties, type ReactNode, type TouchEvent } from "react";
import { createPortal } from "react-dom";
import { useModal } from "@/src/hooks/useModal";
import { getFocusableElements } from "@/src/utils/focus";
import Icon from "@/src/components/UI/Icon/Icon";
import styles from "./Drawer.module.css";

interface DrawerProps {
  id: string;
  open: boolean;
  label: string;
  children: ReactNode;
  onClose: () => void;
  closeLabel?: string;
  width?: CSSProperties["width"];
  side?: "left" | "right";
  mobileBottom?: boolean;
}

const Drawer = ({
  id,
  open,
  label,
  children,
  onClose,
  closeLabel = "Закрыть",
  width,
  side = "left",
  mobileBottom = false,
}: DrawerProps) => {
  const ref = useRef<HTMLDivElement>(null);
  const [mounted, setMounted] = useState(open);
  const touch = useRef<{ x: number; y: number; scrollTop: number; dragging: boolean } | null>(null);
  useModal(mounted, ref);

  useEffect(() => {
    if (open) {
      ref.current?.style.removeProperty("--sheet-drag-y");
      ref.current?.style.removeProperty("animation");
      ref.current?.style.removeProperty("transition");
      const frame = requestAnimationFrame(() => setMounted(true));
      return () => cancelAnimationFrame(frame);
    }
    if (!mounted) return;
    const timer = window.setTimeout(() => setMounted(false), window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 280);
    return () => window.clearTimeout(timer);
  }, [open, mounted]);

  function onTouchStart(event: TouchEvent<HTMLDivElement>) {
    if (!mobileBottom || !window.matchMedia("(max-width: 600px)").matches || event.touches.length !== 1) return;
    const target = event.target instanceof Element ? event.target.closest<HTMLElement>("[data-sheet-scroll]") : null;
    touch.current = { x: event.touches[0].clientX, y: event.touches[0].clientY, scrollTop: target?.scrollTop ?? 0, dragging: false };
  }

  function onTouchMove(event: TouchEvent<HTMLDivElement>) {
    const start = touch.current;
    const panel = ref.current;
    if (!start || !panel || start.scrollTop > 0 || event.touches.length !== 1) return;
    const dx = event.touches[0].clientX - start.x;
    const dy = event.touches[0].clientY - start.y;
    if (dy < 8 || dy < Math.abs(dx) * 1.2) return;
    start.dragging = true;
    panel.style.animation = "none";
    panel.style.transition = "none";
    panel.style.setProperty("--sheet-drag-y", `${dy}px`);
  }

  function onTouchEnd(event: TouchEvent<HTMLDivElement>) {
    const start = touch.current;
    touch.current = null;
    const panel = ref.current;
    if (!start?.dragging || !panel) return;
    const dy = event.changedTouches[0]?.clientY - start.y || 0;
    panel.style.transition = "transform var(--motion-normal) var(--ease-out)";
    if (dy > 90) onClose();
    else panel.style.setProperty("--sheet-drag-y", "0px");
  }

  function onTouchCancel() {
    touch.current = null;
    ref.current?.style.setProperty("--sheet-drag-y", "0px");
    if (ref.current) ref.current.style.transition = "transform var(--motion-normal) var(--ease-out)";
  }

  if (!mounted) return null;

  return createPortal(
    <div
      className={`${styles.Drawer} ${side === "right" ? styles.right : ""} ${mobileBottom ? styles.mobileBottom : ""}`}
      data-state={open ? "open" : "closed"}
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
        onTouchStart={onTouchStart}
        onTouchMove={onTouchMove}
        onTouchEnd={onTouchEnd}
        onTouchCancel={onTouchCancel}
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
          <Icon name="close" size={20} />
        </button>
        {children}
      </div>
    </div>,
    document.body,
  );
};

export default Drawer;
