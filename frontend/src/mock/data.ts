import type { Activity, FileItem, Message, Task, ToolItem } from "../types";
export const initialMessages: Message[] = [
  {
    id: "m1",
    role: "user",
    text: "Analiza mi agenda de hoy y resúmeme los puntos importantes.",
    time: "14:28",
  },
  {
    id: "m2",
    role: "assistant",
    text: "Tienes 3 reuniones programadas. La revisión de la propuesta es a las 16:00 y hay 1 tarea prioritaria pendiente.",
    time: "14:29",
    kind: "summary",
  },
];
export const initialActivity: Activity[] = [
  {
    id: "a1",
    time: "14:32",
    title: "Chrome abierto",
    detail: "Aplicación iniciada correctamente",
    kind: "success",
  },
  {
    id: "a2",
    time: "14:29",
    title: "Reporte_Q3.pdf movido",
    detail: "Descargas → Documentos",
    kind: "success",
  },
  {
    id: "a3",
    time: "14:20",
    title: "Búsqueda realizada",
    detail: "“facturas septiembre”",
    kind: "info",
  },
];
export const initialTasks: Task[] = [
  {
    id: "t1",
    title: "Revisar propuesta de producto",
    detail: "Comentarios finales antes de compartir con el equipo",
    due: "Hoy · 16:00",
    status: "pendiente",
    urgent: true,
  },
  {
    id: "t2",
    title: "Análisis de datos de septiembre",
    detail: "Validar tendencias y preparar conclusiones",
    due: "Mañana · 11:00",
    status: "en progreso",
  },
  {
    id: "t3",
    title: "Reunión con el equipo de diseño",
    detail: "Alinear prioridades del próximo sprint",
    due: "Hoy · 10:30",
    status: "completada",
  },
  {
    id: "t4",
    title: "Diseño de nueva propuesta",
    detail: "Preparar primeras opciones de interfaz",
    due: "Miércoles · 15:00",
    status: "pendiente",
  },
];
export const files: FileItem[] = [
  {
    id: "f1",
    name: "Reporte_Q3.pdf",
    type: "PDF",
    size: "2,4 MB",
    modified: "Hoy, 09:41",
    path: "Documentos / Reportes",
  },
  {
    id: "f2",
    name: "Diseño_Jarvis.fig",
    type: "FIG",
    size: "18,6 MB",
    modified: "Ayer, 17:26",
    path: "Proyectos / Jarvis",
  },
  {
    id: "f3",
    name: "Notas_Reunión.docx",
    type: "DOCX",
    size: "824 KB",
    modified: "Ayer, 11:08",
    path: "Documentos / Reuniones",
  },
  {
    id: "f4",
    name: "main.py",
    type: "PY",
    size: "14 KB",
    modified: "22 sep, 14:03",
    path: "Proyectos / Automatización",
  },
];
export const tools: ToolItem[] = [
  {
    id: "open-app",
    name: "Abrir aplicaciones",
    description: "Inicia aplicaciones instaladas en tu PC.",
    risk: "Bajo",
    available: true,
  },
  {
    id: "open-web",
    name: "Abrir web",
    description: "Abre direcciones y búsquedas en el navegador.",
    risk: "Bajo",
    available: true,
  },
  {
    id: "find-files",
    name: "Buscar archivos",
    description: "Localiza documentos por nombre o contexto.",
    risk: "Bajo",
    available: true,
  },
  {
    id: "move-files",
    name: "Mover archivos",
    description: "Organiza archivos entre carpetas con confirmación.",
    risk: "Medio",
    available: true,
  },
  {
    id: "copy-files",
    name: "Copiar archivos",
    description: "Duplica archivos en una ubicación elegida.",
    risk: "Medio",
    available: true,
  },
  {
    id: "create-folders",
    name: "Crear carpetas",
    description: "Prepara nuevas carpetas para tus proyectos.",
    risk: "Medio",
    available: true,
  },
  {
    id: "system-info",
    name: "Información del sistema",
    description: "Consulta estado y recursos del equipo.",
    risk: "Bajo",
    available: true,
  },
];
