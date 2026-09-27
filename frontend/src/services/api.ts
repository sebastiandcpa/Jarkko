import { files, initialActivity, tools } from "../mock/data";
import type {
  Activity,
  FileItem,
  Message,
  SystemStatus,
  ToolItem,
} from "../types";
const base = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8765";
const forceMock = import.meta.env.VITE_USE_MOCK_API !== "false";
export const apiMode = forceMock ? "mock" : "auto";
async function request<T>(
  path: string,
  init?: RequestInit,
  fallback?: () => T,
): Promise<T> {
  if (forceMock && fallback) return fallback();
  try {
    const response = await fetch(base + path, {
      ...init,
      signal: AbortSignal.timeout(3000),
    });
    if (!response.ok) throw new Error("HTTP " + response.status);
    return (await response.json()) as T;
  } catch {
    if (fallback) return fallback();
    throw new Error("No se pudo conectar con el servicio local");
  }
}
const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});
export const api = {
  health: () =>
    request<{ status: string }>("/api/health", undefined, () => ({
      status: "mock",
    })),
  systemStatus: () =>
    request<SystemStatus>("/api/system/status", undefined, () => ({
      cpu: 18,
      memory: 42,
      sync: true,
      online: true,
    })),
  tools: () => request<ToolItem[]>("/api/tools", undefined, () => tools),
  activity: () =>
    request<Activity[]>("/api/activity", undefined, () => initialActivity),
  searchFiles: (query: string) =>
    request<FileItem[]>(
      "/api/files/search?q=" + encodeURIComponent(query),
      undefined,
      () =>
        files.filter((file) =>
          (file.name + file.path).toLowerCase().includes(query.toLowerCase()),
        ),
    ),
  chat: (message: string, assistant: string) =>
    request<Message>("/api/chat", json({ message, assistant }), () => ({
      id: crypto.randomUUID(),
      role: "assistant",
      time: new Date().toLocaleTimeString("es-PE", {
        hour: "2-digit",
        minute: "2-digit",
        hourCycle: "h23",
      }),
      text: message.toLowerCase().includes("plan")
        ? "Preparé una secuencia de pasos para esta solicitud. Revísala antes de ejecutar cambios."
        : message.toLowerCase().includes("archivo")
          ? "Encontré documentos relacionados. Puedes revisarlos en Archivos o indicarme qué necesitas hacer con ellos."
          : "Entendido. Preparé el contexto para ayudarte con esa solicitud. Cuando el servicio local esté conectado podré ejecutar la acción.",
      kind: message.toLowerCase().includes("plan")
        ? "plan"
        : message.toLowerCase().includes("archivo")
          ? "file"
          : "result",
    })),
  executeAction: (action: string, payload: unknown) =>
    request<unknown>("/api/actions/execute", json({ action, payload }), () => ({
      status: "mock",
      action,
    })),
  confirmAction: (id: string, confirmed: boolean) =>
    request<unknown>("/api/actions/confirm", json({ id, confirmed }), () => ({
      status: "mock",
      confirmed,
    })),
};
