export type Assistant = "jarvis" | "ekko";
export type AssistantStatus =
  | "idle"
  | "listening"
  | "thinking"
  | "planning"
  | "executing"
  | "waiting_confirmation"
  | "success"
  | "error";
export type Page =
  | "home"
  | "conversation"
  | "tasks"
  | "files"
  | "calendar"
  | "knowledge"
  | "tools"
  | "activity"
  | "settings";
export type Message = {
  id: string;
  role: "user" | "assistant";
  text: string;
  time: string;
  kind?: "summary" | "file" | "plan" | "confirmation" | "result" | "error";
};
export type Activity = {
  id: string;
  time: string;
  title: string;
  detail: string;
  kind: "success" | "info" | "pending" | "error";
};
export type Task = {
  id: string;
  title: string;
  detail: string;
  due: string;
  status: "pendiente" | "en progreso" | "completada";
  urgent?: boolean;
};
export type FileItem = {
  id: string;
  name: string;
  type: string;
  size: string;
  modified: string;
  path: string;
};
export type ToolItem = {
  id: string;
  name: string;
  description: string;
  risk: "Bajo" | "Medio" | "Alto";
  available: boolean;
};
export type SystemStatus = {
  cpu: number;
  memory: number;
  sync: boolean;
  online: boolean;
};
