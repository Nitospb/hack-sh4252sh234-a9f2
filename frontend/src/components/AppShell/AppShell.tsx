"use client";

import { useEffect, useState, type ReactNode } from "react";
import { usePathname } from "next/navigation";
import Sidebar from "./Sidebar/Sidebar";
import Topbar from "./Topbar/Topbar";
import Drawer from "@/src/components/UI/Drawer/Drawer";
import Icon from "@/src/components/UI/Icon/Icon";
import { useLive } from "@/src/providers/LiveProvider";
import styles from "@/src/styles/Design.module.css";
import Onboarding from "@/src/screens/Workspace/Onboarding";
import SitePreloader from "./SitePreloader/SitePreloader";

const AppShell = ({ children }: { children: ReactNode }) => {
  const {health}=useLive();
  const [menuOpen, setMenuOpen] = useState(false);
  const [demoNoticeOpen, setDemoNoticeOpen] = useState(false);
  const pathname = usePathname();
  const closeMenu = () => setMenuOpen(false);
  const showDemoNotice = pathname !== "/kit" && health?.dataset_kind === "synthetic";
  const demoNoticeText = "Техническая демонстрация на синтетических данных. Эти новости и компании не описывают реальные события.";

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
      <SitePreloader />
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
      <main className={`${styles.main} ${showDemoNotice ? styles.mainWithDemoNotice : ""}`} id="main-content">
        <Topbar onMenu={() => setMenuOpen(true)} menuOpen={menuOpen} />
        <div className={styles.pageContent} key={pathname}>
          {children}
        </div>
        {pathname !== "/kit" && <Onboarding />}
      </main>
      <button
        type="button"
        className={styles.mobileNavigationButton}
        onClick={() => setMenuOpen(true)}
        aria-label="Открыть разделы"
        aria-expanded={menuOpen}
        aria-controls="mobile-navigation"
      >
        <Icon name="menu" size={22} />
      </button>
      {showDemoNotice && (
        <button
          type="button"
          className={`${styles.demoNotice} ${demoNoticeOpen ? styles.demoNoticeOpen : ""}`}
          onClick={() => setDemoNoticeOpen((open) => !open)}
          aria-expanded={demoNoticeOpen}
          aria-controls="demo-notice-text"
          aria-label={demoNoticeOpen ? `${demoNoticeText} Свернуть уведомление.` : "Показать уведомление о синтетических данных"}
        >
          <span className={styles.demoNoticeIcon} aria-hidden="true">!</span>
          <span id="demo-notice-text" className={styles.demoNoticeText} aria-hidden={!demoNoticeOpen}>
            {demoNoticeText}
          </span>
        </button>
      )}
    </div>
  );
};

export default AppShell;
