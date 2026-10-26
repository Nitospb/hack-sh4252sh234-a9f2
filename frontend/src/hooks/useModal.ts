"use client";

import { useEffect, useRef, type RefObject } from "react";
import { getFocusableElements } from "@/src/utils/focus";

export const useModal = (
  open: boolean,
  ref: RefObject<HTMLDivElement | null>,
) => {
  const opener = useRef<HTMLElement | null>(null);

  useEffect(() => {
    const panel = ref.current;
    if (!open || !panel) return;

    if (
      document.activeElement instanceof HTMLElement &&
      !panel.contains(document.activeElement)
    ) {
      opener.current = document.activeElement;
    }

    const scrollTop = window.scrollY;
    const body = document.body;
    const previous = {
      position: body.style.position,
      top: body.style.top,
      width: body.style.width,
      overflow: body.style.overflow,
    };
    const background = Array.from(body.children)
      .filter(
        (element): element is HTMLElement =>
          element instanceof HTMLElement && !element.contains(panel),
      )
      .map((element) => ({ element, inert: element.inert }));

    background.forEach(({ element }) => {
      element.inert = true;
    });
    body.style.position = "fixed";
    body.style.top = `-${scrollTop}px`;
    body.style.width = "100%";
    body.style.overflow = "hidden";
    (getFocusableElements(panel)[0] ?? panel).focus({ preventScroll: true });

    return () => {
      background.forEach(({ element, inert }) => {
        element.inert = inert;
      });
      Object.assign(body.style, previous);
      window.scrollTo({ top: scrollTop, behavior: "instant" });
      if (opener.current?.isConnected) {
        opener.current.focus({ preventScroll: true });
      }
    };
  }, [open, ref]);
};
