import {createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode} from 'react';
import {useQuery, useQueryClient} from '@tanstack/react-query';
import {apiRequest} from '@/api';
import type {FactoryState} from '@/lib/types';

const HEARTBEAT_TIMEOUT = 30000;
const RECONNECT_DELAY = 2000;
export const STATE_KEY = ['factory-state'] as const;

type Modal = {title: string; value: unknown} | null;

type FactoryContextValue = {
  access: string;
  data: FactoryState | undefined;
  connected: boolean;
  busy: boolean;
  error: string;
  networkError: string;
  modal: Modal;
  setModal: (modal: Modal) => void;
  clearError: () => void;
  refresh: () => Promise<FactoryState>;
  /** POST autorizado; atualiza o estado e devolve a resposta (ou undefined com erro exibido). */
  operate: (path: string, body?: unknown) => Promise<Record<string, unknown> | undefined>;
  disconnect: () => void;
};

const FactoryContext = createContext<FactoryContextValue | null>(null);

export function useFactory() {
  const value = useContext(FactoryContext);
  if (!value) throw new Error('useFactory fora do FactoryProvider');
  return value;
}

export function FactoryProvider({access, onDisconnect, children}: {access: string; onDisconnect: () => void; children: ReactNode}) {
  const client = useQueryClient();
  const [connected, setConnected] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [networkError, setNetworkError] = useState('');
  const [modal, setModal] = useState<Modal>(null);

  const fetchState = useCallback(
    async (signal?: AbortSignal) => {
      const result = (await apiRequest(access, 'state', undefined, signal)) as FactoryState;
      if (!signal?.aborted) {
        client.setQueryData(STATE_KEY, result);
        setNetworkError('');
      }
      return result;
    },
    [access, client],
  );

  // O estado só é buscado pelo laço de eventos abaixo (sem polling próprio do Query).
  const {data} = useQuery<FactoryState>({queryKey: STATE_KEY, queryFn: () => fetchState(), enabled: false});

  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    let cursor = 0;

    async function poll() {
      const stream = new AbortController();
      const stop = () => stream.abort();
      controller.signal.addEventListener('abort', stop, {once: true});
      let streamTimer = setTimeout(stop, HEARTBEAT_TIMEOUT);
      try {
        await fetchState(controller.signal);
        const response = await fetch('/api/events?after=' + cursor, {headers: {Authorization: 'Bearer ' + access}, signal: stream.signal});
        if (!response.ok) throw Error(response.status === 403 ? 'Sessão expirada. Reconecte com o endereço atual do servidor.' : 'SSE recusado. Tente reconectar.');
        if (!response.body) throw Error('SSE indisponível neste navegador.');
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let changed = false;
        while (!controller.signal.aborted) {
          const {value, done} = await reader.read();
          if (done) break;
          clearTimeout(streamTimer);
          streamTimer = setTimeout(stop, HEARTBEAT_TIMEOUT);
          buffer += decoder.decode(value, {stream: true});
          const boundary = buffer.lastIndexOf('\n\n');
          if (boundary >= 0) {
            const text = buffer.slice(0, boundary);
            buffer = buffer.slice(boundary + 2);
            for (const match of text.matchAll(/^id: (\d+)/gm)) {
              cursor = Math.max(cursor, Number(match[1]));
              changed = true;
            }
            setConnected(true);
            if (changed) {
              await fetchState(controller.signal);
              changed = false;
            }
          }
        }
        if (changed && !controller.signal.aborted) await fetchState(controller.signal);
        setConnected(false);
      } catch (e) {
        if (!controller.signal.aborted) {
          setConnected(false);
          setNetworkError(
            stream.signal.aborted
              ? 'Eventos desconectados por timeout de heartbeat. Reconexão automática em 2 segundos.'
              : e instanceof TypeError
                ? 'Conexão SSE interrompida. Verifique o backend; reconexão automática em 2 segundos.'
                : (e as Error).message,
          );
        }
      } finally {
        clearTimeout(streamTimer);
        controller.signal.removeEventListener('abort', stop);
        stream.abort();
      }
      if (!controller.signal.aborted) timer = setTimeout(poll, RECONNECT_DELAY);
    }

    poll();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [access, fetchState]);

  const operate = useCallback(
    async (path: string, body: unknown = {}) => {
      setBusy(true);
      setError('');
      try {
        const result = (await apiRequest(access, path, body)) as Record<string, unknown>;
        await fetchState();
        if (path === 'diagnostic') setModal({title: 'Diagnóstico atual do ambiente', value: result});
        return result;
      } catch (e) {
        setError((e as Error).message);
        return undefined;
      } finally {
        setBusy(false);
      }
    },
    [access, fetchState],
  );

  const value = useMemo<FactoryContextValue>(
    () => ({
      access,
      data,
      connected,
      busy,
      error,
      networkError,
      modal,
      setModal,
      clearError: () => setError(''),
      refresh: () => fetchState(),
      operate,
      disconnect: () => {
        client.removeQueries({queryKey: STATE_KEY});
        onDisconnect();
      },
    }),
    [access, data, connected, busy, error, networkError, modal, fetchState, operate, client, onDisconnect],
  );

  return <FactoryContext.Provider value={value}>{children}</FactoryContext.Provider>;
}
