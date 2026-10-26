"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import Icon, { type IconName } from "@/src/components/UI/Icon/Icon";
import s from "./ToastProvider.module.css";

type Toast = { id: number; text: string; icon: IconName; leaving: boolean; action?: { label: string; onClick: () => void | Promise<void> } };
type ToastInput = Omit<Toast, "id" | "leaving">;
const ToastContext = createContext<((toast: ToastInput) => void) | null>(null);

export function useToast() {
  const show = useContext(ToastContext);
  if (!show) throw new Error("ToastProvider is missing");
  return show;
}

export default function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(0);
  const timers = useRef(new Map<number, ReturnType<typeof setTimeout>[]>());
  const dismiss = useCallback((id: number) => {
    timers.current.get(id)?.forEach(clearTimeout);
    setToasts(current => current.map(toast => toast.id === id ? { ...toast, leaving: true } : toast));
    const remove = setTimeout(() => {
      setToasts(current => current.filter(toast => toast.id !== id));
      timers.current.delete(id);
    }, 360);
    timers.current.set(id, [remove]);
  }, []);
  const show = useCallback((input: ToastInput) => {
    const id = ++nextId.current;
    setToasts(current => [...current, { ...input, id, leaving: false }]);
    timers.current.set(id, [setTimeout(() => dismiss(id), 4700)]);
  }, [dismiss]);

  useEffect(() => {
    const active = timers.current;
    return () => { active.forEach(handles => handles.forEach(clearTimeout)); active.clear(); };
  }, []);

  return <ToastContext.Provider value={show}>
    {children}
    <div className={s.stack} aria-live="polite" aria-relevant="additions text">
      {toasts.map(toast => <div key={toast.id} className={`${s.toast} ${toast.leaving ? s.leaving : ""}`} role="status">
        <span className={s.icon} aria-hidden="true"><Icon name={toast.icon} size={20} filled={toast.icon === "like"} /></span>
        <span className={s.text}>{toast.text}</span>
        {toast.action && <button type="button" className={s.action} onClick={async () => { try { await toast.action?.onClick(); dismiss(toast.id); } catch { show({ text: "Не удалось отменить действие.", icon: toast.icon }); } }}>{toast.action.label}</button>}
      </div>)}
    </div>
  </ToastContext.Provider>;
}
