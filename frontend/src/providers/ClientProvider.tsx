"use client";

import { createContext, useContext, type ReactNode } from "react";
import { CLIENTS } from "@/src/data/demo";
import { usePersistentState } from "@/src/hooks/usePersistentState";
import {
  DEFAULT_SETTINGS,
  getClientEvents,
  getVisibleEvents,
} from "@/src/utils/insights";
import type { Client, FeedSettings, PersonalizedEvent } from "@/src/types";

interface ClientContextValue {
  client: Client;
  selectClient: (id: string) => void;
  settings: FeedSettings;
  updateSettings: (values: Partial<FeedSettings>) => void;
  events: PersonalizedEvent[];
  allEvents: PersonalizedEvent[];
}

const ClientContext = createContext<ClientContextValue | null>(null);

const ClientProvider = ({ children }: { children: ReactNode }) => {
  const [clientId, setClientId] = usePersistentState(
    "alfa-client",
    CLIENTS[0].id,
  );
  const client = CLIENTS.find((item) => item.id === clientId) ?? CLIENTS[0];
  const [storedSettings, setSettings] = usePersistentState<FeedSettings>(
    `alfa-settings-${client.id}`,
    DEFAULT_SETTINGS,
  );
  const settings = { ...DEFAULT_SETTINGS, ...storedSettings };

  return (
    <ClientContext.Provider
      value={{
        client,
        selectClient: setClientId,
        settings,
        updateSettings: (values) =>
          setSettings((previous) => ({ ...previous, ...values })),
        events: getVisibleEvents(client, settings),
        allEvents: getClientEvents(client),
      }}
    >
      {children}
    </ClientContext.Provider>
  );
};

export const useClient = () => {
  const context = useContext(ClientContext);
  if (!context) throw new Error("ClientProvider is required");
  return context;
};

export default ClientProvider;
