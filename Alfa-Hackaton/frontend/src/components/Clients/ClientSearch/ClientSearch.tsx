"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { CLIENTS } from "@/src/data/demo";
import { useClient } from "@/src/providers/ClientProvider";
import Avatar from "@/src/components/UI/Avatar/Avatar";
import styles from "@/src/styles/Design.module.css";

const ClientSearch = () => {
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const { selectClient } = useClient();
  const router = useRouter();
  const handleSearch = (event: FormEvent) => {
    event.preventDefault();
    const client = CLIENTS.find(
      (item) => item.id === query.trim().toUpperCase(),
    );
    if (!client) {
      setError("Клиент не найден. В демо доступны U-10482, U-22917 и U-31055.");
      return;
    }
    selectClient(client.id);
    router.push("/");
  };

  return (
    <>
      <div className={styles["up-file"]}>
        <Avatar text="+" background="var(--violet)" />
        <div style={{ flex: 1 }}>
          <b>Найти по SYNTHETIC_U</b>
          <div className={`${styles.muted} ${styles.small}`}>
            Загружено: df_Uid_data_hack.csv · df_Fid_Uid_link_hack.csv ·
            df_Uid_payment_hack.csv
          </div>
        </div>
        <form className={styles.inp} onSubmit={handleSearch}>
          <input
            aria-label="Идентификатор клиента"
            placeholder="Например, U-10482"
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setError("");
            }}
            required
          />
          <button type="submit">Найти</button>
        </form>
      </div>
      {error && (
        <p role="alert" style={{ color: "var(--red)" }}>
          {error}
        </p>
      )}
    </>
  );
};

export default ClientSearch;
