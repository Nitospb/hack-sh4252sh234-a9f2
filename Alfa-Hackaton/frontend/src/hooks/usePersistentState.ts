"use client";

import { useCallback, useSyncExternalStore } from "react";

const memory = new Map<string, string>();
const subscribe = (callback: () => void) => {
  window.addEventListener("storage", callback);
  window.addEventListener("alfa-storage", callback);
  return () => {
    window.removeEventListener("storage", callback);
    window.removeEventListener("alfa-storage", callback);
  };
};

const read = (key: string) => {
  try {
    return window.localStorage.getItem(key) ?? memory.get(key) ?? null;
  } catch {
    return memory.get(key) ?? null;
  }
};

export const usePersistentState = <T>(key: string, initialValue: T) => {
  const getSnapshot = useCallback(() => read(key), [key]);
  const serialized = useSyncExternalStore(subscribe, getSnapshot, () => null);
  let value = initialValue;
  if (serialized !== null) {
    try {
      value = JSON.parse(serialized) as T;
    } catch {
      value = initialValue;
    }
  }

  const setValue = (next: T | ((previous: T) => T)) => {
    const result =
      typeof next === "function" ? (next as (previous: T) => T)(value) : next;
    const json = JSON.stringify(result);
    memory.set(key, json);
    try {
      window.localStorage.setItem(key, json);
    } catch {}
    window.dispatchEvent(new Event("alfa-storage"));
  };

  return [value, setValue] as const;
};
