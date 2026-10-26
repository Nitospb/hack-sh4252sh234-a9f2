"use client";

import { useEffect, useState, type ReactNode } from "react";
import { usePathname } from "next/navigation";
import Sidebar from "./Sidebar/Sidebar";
import Topbar from "./Topbar/Topbar";
import Drawer from "@/src/components/UI/Drawer/Drawer";
import { useLive } from "@/src/providers/LiveProvider";
import styles from "@/src/styles/Design.module.css";

const AppShell = ({ children }: { children: ReactNode }) => {
  const {health}=useLive();
  const [menuOpen, setMenuOpen] = useState(false);
  const pathname = usePathname();
  const closeMenu = () => setMenuOpen(false);

  useEffect(() => {
    const desktop = window.matchMedia("(min-width: 761px)");
    const handleResize = () => {
      if (desktop.matches) setMenuOpen(false);
    };

    desktop.addEventListener("change", handleResize);
    return () => desktop.removeEventListener("change", handleResize);
  }, []);

  return (
    <div className={styles.app}>
      <a className={styles.skipLink} href="#main-content">
        К содержимому
      </a>
      <Sidebar />
      <Drawer
        id="mobile-navigation"
        label="Меню Альфа-Бизнес"
        open={menuOpen}
        onClose={closeMenu}
        closeLabel="Закрыть навигацию"
      >
        <Sidebar mobile onNavigate={closeMenu} />
      </Drawer>
      <main className={styles.main} id="main-content">
        <Topbar
          onMenu={() => setMenuOpen((open) => !open)}
          menuOpen={menuOpen}
        />
        <div className={styles.pageContent} key={pathname}>
          {health?.dataset_kind === "synthetic" && <p role="status" style={{padding:16,background:"#fff6dd",borderRadius:12}}>Техническая демонстрация на синтетических данных. Эти новости и компании не описывают реальные события.</p>}
          {children}
        </div>
      </main>
    </div>
  );
};

export default AppShell;
