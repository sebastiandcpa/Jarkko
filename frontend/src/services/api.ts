import { files, initialActivity, tools } from "../mock/data";
import type {
  Activity,
  FileItem,
  Message,
  SystemStatus,
  ToolItem,
} from "../types";

const base = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8765";
const forceMock = import.meta.env.VITE_USE_MOCK_API === "true";
export const apiMode = forceMock ? "mock" : "auto";

/* El backend responde con su propio contrato (ver backend/API_CONTRACT.md).
   Aquí se traduce a los tipos de la interfaz; si el backend no está disponible,
   se cae al contenido de muestra para que la app siga siendo usable. */

async function request<T>(
  path: string,
  init?: RequestInit,
  fallback?: () => T,
): Promise<T> {
  if (forceMock && fallback) return fallback();
  try {
    const response = await fetch(base + path, {
      ...init,
      signal: AbortSignal.timeout(20000),
    });
    if (!response.ok) throw new Error("HTTP " + response.status);
    return (await response.json()) as T;
  } catch (error) {
    if (fallback) return fallback();
    throw error instanceof Error
      ? error
      : new Error("No se pudo conectar con el servicio local");
  }
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

const now = () =>
  new Date().toLocaleTimeString("es-PE", {
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  });

const id = () =>
  typeof crypto !== "undefined" && crypto.randomUUID
    ? crypto.randomUUID()
    : String(Math.random()).slice(2);

/* ----------------------------------------------------------------------
   Tipos del backend (solo lo que se usa aquí)
   ---------------------------------------------------------------------- */
type BackendAction = {
  tool: string;
  status: string;
  message: string;
  risk_level: string;
  data?: Record<string, unknown>;
};

type BackendChat = {
  conversation_id: string;
  message: string;
  status: "success" | "error" | "awaiting_confirmation" | "no_action";
  actions?: BackendAction[];
  requires_confirmation?: boolean;
};

const RISK_LABELS: Record<string, ToolItem["risk"]> = {
  low: "Bajo",
  medium: "Medio",
  high: "Alto",
  critical: "Alto",
};

function messageKind(payload: BackendChat): Message["kind"] {
  if (payload.status === "awaiting_confirmation") return "confirmation";
  if (payload.status === "error") return "error";
  const tool = payload.actions?.[0]?.tool ?? "";
  if (tool.includes("file") || tool.includes("folder")) return "file";
  if ((payload.actions?.length ?? 0) > 1) return "plan";
  return "result";
}

function humanSize(bytes: unknown): string {
  const value = typeof bytes === "number" ? bytes : 0;
  if (!value) return "—";
  const units = ["B", "KB", "MB", "GB"];
  let size = value;
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  return `${size < 10 ? size.toFixed(1) : Math.round(size)} ${units[unit]}`;
}

function shortTime(timestamp: unknown): string {
  if (typeof timestamp !== "string" || !timestamp) return now();
  const parsed = new Date(timestamp);
  return Number.isNaN(parsed.getTime())
    ? now()
    : parsed.toLocaleTimeString("es-PE", {
        hour: "2-digit",
        minute: "2-digit",
        hourCycle: "h23",
      });
}

/* ---------------------------------------------------------------------- */

export const api = {
  health: () =>
    request<{ status: string }>("/api/health", undefined, () => ({
      status: "mock",
    })),

  systemStatus: async (): Promise<SystemStatus> => {
    const raw = await request<Record<string, number> | null>(
      "/api/system/status",
      undefined,
      () => null,
    );
    if (!raw) return { cpu: 18, memory: 42, sync: true, online: false };
    return {
      cpu: Math.round(raw.cpu_percent ?? 0),
      memory: Math.round(raw.memory_percent ?? 0),
      sync: true,
      online: true,
    };
  },

  tools: async (): Promise<ToolItem[]> => {
    const raw = await request<{ tools?: unknown[] } | null>(
      "/api/tools",
      undefined,
      () => null,
    );
    if (!raw?.tools) return tools;
    return raw.tools.map((item) => {
      const tool = item as Record<string, unknown>;
      return {
        id: String(tool.name),
        name: String(tool.name),
        description: String(tool.description ?? ""),
        risk: RISK_LABELS[String(tool.risk_level)] ?? "Medio",
        available: Boolean(tool.enabled),
      };
    });
  },

  activity: async (): Promise<Activity[]> => {
    const raw = await request<{ entries?: unknown[] } | null>(
      "/api/activity?limit=25",
      undefined,
      () => null,
    );
    if (!raw?.entries) return initialActivity;
    return raw.entries.map((item) => {
      const entry = item as Record<string, unknown>;
      const status = String(entry.status);
      return {
        id: String(entry.id),
        time: shortTime(entry.timestamp),
        title: String(entry.tool),
        detail: String(entry.message ?? ""),
        kind:
          status === "success"
            ? "success"
            : status === "awaiting_confirmation"
              ? "pending"
              : status === "cancelled"
                ? "info"
                : "error",
      };
    });
  },

  searchFiles: async (query: string): Promise<FileItem[]> => {
    const raw = await request<{ results?: unknown[] } | null>(
      "/api/files/search?q=" + encodeURIComponent(query),
      undefined,
      () => null,
    );
    if (!raw?.results) {
      return files.filter((file) =>
        (file.name + file.path).toLowerCase().includes(query.toLowerCase()),
      );
    }
    return raw.results.map((item) => {
      const file = item as Record<string, unknown>;
      const name = String(file.name);
      return {
        id: String(file.path),
        name,
        type:
          file.type === "directory"
            ? "Carpeta"
            : (name.split(".").pop() ?? "archivo").toUpperCase(),
        size: file.type === "directory" ? "—" : humanSize(file.size),
        modified: shortTime(file.modified),
        path: String(file.path),
      };
    });
  },

  chat: async (message: string, assistant: string): Promise<Message> => {
    const payload = await request<BackendChat | null>(
      "/api/chat",
      json({ message, assistant: assistant || "jarkko" }),
      () => null,
    );

    if (!payload) {
      return {
        id: id(),
        role: "assistant",
        time: now(),
        text:
          "No pude contactar con el servicio local de JARKKO. " +
          "Comprueba que la aplicación lo haya arrancado (puerto 8765).",
        kind: "error",
      };
    }

    return {
      id: id(),
      role: "assistant",
      time: now(),
      text: payload.message,
      kind: messageKind(payload),
    };
  },

  executeAction: (tool: string, args: Record<string, unknown> = {}) =>
    request<unknown>(
      "/api/actions/execute",
      json({ tool, arguments: args, assistant: "jarkko" }),
      () => ({ status: "mock", tool }),
    ),

  confirmAction: (confirmationId: string, approved: boolean) =>
    request<unknown>(
      "/api/actions/confirm",
      json({ confirmation_id: confirmationId, approved }),
      () => ({ status: "mock", approved }),
    ),
};
