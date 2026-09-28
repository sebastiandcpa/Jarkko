export type BackendEvent = { type: string; payload?: unknown };

type WireEvent = { type?: unknown; data?: unknown; payload?: unknown };

export function connectEvents(
  onEvent: (event: BackendEvent) => void,
): () => void {
  if (import.meta.env.VITE_USE_MOCK_API !== "false") return () => {};

  const url = import.meta.env.VITE_WS_URL || "ws://127.0.0.1:8765/ws/events";
  let socket: WebSocket | null = null;
  let retryTimer = 0;
  let retries = 0;
  let stopped = false;

  const reconnect = () => {
    if (stopped) return;
    const delay = Math.min(5000, 600 * 2 ** Math.min(retries++, 3));
    retryTimer = window.setTimeout(open, delay);
  };

  const open = () => {
    if (stopped) return;
    try {
      socket = new WebSocket(url);
    } catch {
      reconnect();
      return;
    }
    const current = socket;
    current.onopen = () => {
      if (stopped) return;
      retries = 0;
      onEvent({ type: "connection.status", payload: true });
    };
    current.onmessage = (message) => {
      try {
        const event = JSON.parse(message.data) as WireEvent;
        if (typeof event.type !== "string") return;
        onEvent({ type: event.type, payload: event.data ?? event.payload });
      } catch {
        // Un mensaje incompleto no interrumpe el resto de la conversación.
      }
    };
    current.onclose = () => {
      if (stopped) return;
      onEvent({ type: "connection.status", payload: false });
      reconnect();
    };
    current.onerror = () => current.close();
  };

  open();
  return () => {
    stopped = true;
    window.clearTimeout(retryTimer);
    socket?.close();
  };
}
