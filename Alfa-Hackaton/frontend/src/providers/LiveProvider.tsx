"use client";
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, type Company, type Health, type Profile } from "@/src/screens/Feed/recommendation-api";
type Live = { company: Company | null; user: string; role: string; health: Health | null; error: string; select: (c: Company) => void; refresh: () => void };
const Context = createContext<Live | null>(null);
export default function LiveProvider({ children }: { children: ReactNode }) {
  const [company, setCompany] = useState<Company | null>(null); const [user, setUser] = useState(""); const [role, setRole] = useState("general"); const [health, setHealth] = useState<Health | null>(null); const [error, setError] = useState("");
  const refresh = useCallback(() => { window.dispatchEvent(new Event("alfa:reload-live")); }, []);
  const select = useCallback((c: Company) => { localStorage.setItem("alfa-active-company-v2", c.source_record_id); window.dispatchEvent(new CustomEvent("alfa:company", { detail: c })); }, []);
  useEffect(() => {
    const uid=localStorage.getItem("alfa-live-user") || crypto.randomUUID();localStorage.setItem("alfa-live-user",uid);
    let cancelled=false;
    const onCompany=(event: Event) => { setCompany((event as CustomEvent<Company>).detail); };
    async function init() {
      try {
        const h=await api<Health>("health");const saved=localStorage.getItem("alfa-active-company-v2");
        let c: Company;
        if(saved) c=await api<Company>(`company?${new URLSearchParams({company_id:saved.split(":line:")[0],source_record_id:saved})}`);
        else c=(await api<{items:Company[]}>("companies?limit=1")).items[0];
        if(!cancelled){setUser(uid);setHealth(h);setCompany(c);setError("");}
      } catch(e){if(!cancelled)setError(String(e));}
    }
    init();window.addEventListener("alfa:company",onCompany);window.addEventListener("alfa:reload-live",init);
    return()=>{cancelled=true;window.removeEventListener("alfa:company",onCompany);window.removeEventListener("alfa:reload-live",init);};
  },[]);
  useEffect(()=>{
    const abort=new AbortController();
    const refreshHealth=()=>{if(!document.hidden)api<Health>("health",{signal:abort.signal}).then(setHealth).catch(()=>{});};
    const timer=setInterval(refreshHealth,30000);
    window.addEventListener("focus",refreshHealth);window.addEventListener("alfa:refresh-health",refreshHealth);document.addEventListener("visibilitychange",refreshHealth);
    return()=>{clearInterval(timer);abort.abort();window.removeEventListener("focus",refreshHealth);window.removeEventListener("alfa:refresh-health",refreshHealth);document.removeEventListener("visibilitychange",refreshHealth);};
  },[]);
  useEffect(()=>{
    if(!company||!user)return;const abort=new AbortController();
    api<Profile>(`profile?${new URLSearchParams({company_id:company.company_id,user_id:user})}`,{signal:abort.signal}).then(p=>setRole(p.role)).catch(()=>{});
    return()=>abort.abort();
  },[company,user]);
  return <Context.Provider value={{company,user,role,health,error,select,refresh}}>{children}</Context.Provider>;
}
export function useLive(){const c=useContext(Context);if(!c)throw Error("LiveProvider required");return c;}
