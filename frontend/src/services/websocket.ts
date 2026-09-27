export type BackendEvent = { type: string; payload?: unknown };
export function connectEvents(
  onEvent: (event: BackendEvent) => void,
): () => void {
  if (import.meta.env.VITE_USE_MOCK_API !== "false") return () => {};
  const socket = new WebSocket(
    import.meta.env.VITE_WS_URL || "ws://127.0.0.1:8765/ws/events",
  );
  socket.onmessage = (event) => {
    try {
      onEvent(JSON.parse(event.data) as BackendEvent);
    } catch {
      /* malformed event */
    }
  };
  socket.onerror = () => socket.close();
  return () => socket.close();
}
