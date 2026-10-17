import { createContext, useContext, useSyncExternalStore, type ReactNode } from 'react';
import type { ConsoleState, SoundMatClient } from './client';

const Ctx = createContext<SoundMatClient | null>(null);

export function ClientProvider({ client, children }: { client: SoundMatClient; children: ReactNode }) {
  return <Ctx.Provider value={client}>{children}</Ctx.Provider>;
}

export function useClient(): SoundMatClient {
  const c = useContext(Ctx);
  if (!c) throw new Error('ClientProvider missing');
  return c;
}

export function useConsole(): ConsoleState {
  const c = useClient();
  return useSyncExternalStore(c.subscribe, c.getState, c.getState);
}
