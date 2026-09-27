import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  Activity,
  ArrowRight,
  AudioLines,
  BookOpen,
  CalendarDays,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock3,
  Command,
  Copy,
  FilePenLine,
  FileText,
  Files,
  FolderPlus,
  Globe2,
  HardDrive,
  Home,
  LayoutGrid,
  Menu,
  Mic,
  MoreHorizontal,
  MoveRight,
  Plus,
  Search,
  Send,
  Settings2,
  ShieldCheck,
  Sparkles,
  SquareCheckBig,
  Wrench,
  X,
} from "lucide-react";
import { api, apiMode } from "../services/api";
import { connectEvents, type BackendEvent } from "../services/websocket";
import {
  files,
  initialActivity,
  initialMessages,
  initialTasks,
  tools,
} from "../mock/data";
import type {
  Activity as ActivityItem,
  Assistant,
  AssistantStatus,
  FileItem,
  Message,
  Page,
  Task,
} from "../types";
import { Orb } from "../components/Orb";
import {
  PageHeader,
  SearchField,
  SectionHeader,
} from "../components/Primitives";

const nav: { id: Page; label: string; icon: typeof Home }[] = [
  { id: "home", label: "Inicio", icon: Home },
  { id: "conversation", label: "Conversación", icon: Command },
  { id: "tasks", label: "Tareas", icon: SquareCheckBig },
  { id: "files", label: "Archivos", icon: Files },
  { id: "calendar", label: "Calendario", icon: CalendarDays },
  { id: "knowledge", label: "Conocimiento", icon: BookOpen },
  { id: "tools", label: "Herramientas", icon: Wrench },
];
const pageNames: Record<Page, string> = {
  home: "Inicio",
  conversation: "Conversación",
  tasks: "Tareas",
  files: "Archivos",
  calendar: "Calendario",
  knowledge: "Conocimiento",
  tools: "Herramientas",
  activity: "Actividad",
  settings: "Configuración",
};
const statusText: Record<AssistantStatus, string> = {
  idle: "Listo para ayudarte",
  listening: "Escuchando…",
  thinking: "Analizando…",
  planning: "Preparando acción…",
  executing: "Ejecutando…",
  waiting_confirmation: "Esperando confirmación…",
  success: "Completado",
  error: "Necesita atención",
};
const timeNow = () =>
  new Date().toLocaleTimeString("es-PE", {
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  });
const id = () => crypto.randomUUID();
const bars = Array.from(
  { length: 25 },
  (_, index) =>
    7 +
    Math.round(Math.abs(Math.sin(index * 1.36) * Math.cos(index * 0.29)) * 24),
);
export function App() {
  const [clock, setClock] = useState(() => new Date());
  const [assistant, setAssistantState] = useState<Assistant>(() =>
    localStorage.getItem("jarvis-ekko-assistant") === "ekko"
      ? "ekko"
      : "jarvis",
  );
  const [page, setPage] = useState<Page>("home");
  const [railExpanded, setRailExpanded] = useState(false);
  const [status, setStatus] = useState<AssistantStatus>("idle");
  const [messages, setMessages] = useState<Message[]>(initialMessages);
  const [activity, setActivity] = useState<ActivityItem[]>(initialActivity);
  const [tasks, setTasks] = useState<Task[]>(initialTasks);
  const [input, setInput] = useState("");
  const [notice, setNotice] = useState("");
  const [taskFilter, setTaskFilter] = useState<"todas" | Task["status"]>(
    "todas",
  );
  const [fileQuery, setFileQuery] = useState("");
  const [knowledgeQuery, setKnowledgeQuery] = useState("");
  const [confirmFile, setConfirmFile] = useState<FileItem | null>(null);
  const [pendingAction, setPendingAction] = useState("");
  const [autoStart, setAutoStart] = useState(false);
  const [criticalConfirm, setCriticalConfirm] = useState(true);
  const [system, setSystem] = useState({
    cpu: 18,
    memory: 42,
    sync: true,
    online: true,
  });
  const feedRef = useRef<HTMLDivElement>(null);
  const ekko = assistant === "ekko";
  const displayMessage = (message: Message) => {
    if (!ekko) return message.text;
    if (message.id === "m1") return "Organiza mis archivos de la semana y muéstrame un resumen.";
    if (message.id === "m2") return "He encontrado 12 archivos relevantes de esta semana. Puedes revisar el resumen antes de organizarlos.";
    return message.text;
  };
  const setAssistant = (value: Assistant) => {
    setAssistantState(value);
    localStorage.setItem("jarvis-ekko-assistant", value);
    setStatus("idle");
  };
  const addActivity = (
    title: string,
    detail: string,
    kind: ActivityItem["kind"] = "info",
  ) =>
    setActivity((previous) => [
      { id: id(), time: timeNow(), title, detail, kind },
      ...previous,
    ]);
  const showNotice = (text: string) => setNotice(text);
  useEffect(() => {
    document.documentElement.dataset.assistant = assistant;
  }, [assistant]);
  useEffect(() => { const timer = window.setInterval(() => setClock(new Date()), 30000); return () => window.clearInterval(timer) }, []);
  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(""), 3600);
    return () => window.clearTimeout(timer);
  }, [notice]);
  useEffect(() => {
    api
      .systemStatus()
      .then(setSystem)
      .catch(() => {});
    return connectEvents((event: BackendEvent) => {
      if (
        event.type === "assistant.status" &&
        typeof event.payload === "string"
      )
        setStatus(event.payload as AssistantStatus);
      if (
        event.type === "system.status" &&
        event.payload &&
        typeof event.payload === "object"
      )
        setSystem(event.payload as typeof system);
      if (event.type === "confirmation.required")
        setStatus("waiting_confirmation");
      if (event.type === "action.completed")
        addActivity(
          "Acción completada",
          "Resultado recibido del servicio local",
          "success",
        );
      if (event.type === "action.failed")
        addActivity("Acción fallida", "Revisa la actividad reciente", "error");
    });
  }, []);
  useEffect(() => {
    feedRef.current?.scrollTo({
      top: feedRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages]);
  const sendMessage = async (text: string) => {
    const clean = text.trim();
    if (!clean) return;
    setInput("");
    setMessages((previous) => [
      ...previous,
      { id: id(), role: "user", text: clean, time: timeNow() },
    ]);
    setStatus("thinking");
    try {
      const answer = await api.chat(clean, assistant);
      setMessages((previous) => [...previous, answer]);
      addActivity("Consulta procesada", clean, "success");
      setStatus("success");
    } catch {
      setMessages((previous) => [
        ...previous,
        {
          id: id(),
          role: "assistant",
          time: timeNow(),
          text: "No pude completar la solicitud. Revisa la conexión local o activa los datos de muestra.",
          kind: "error",
        },
      ]);
      setStatus("error");
    }
    window.setTimeout(() => setStatus("idle"), 1800);
  };
  const onSend = (event: FormEvent) => {
    event.preventDefault();
    void sendMessage(input);
  };
  const cycleTask = (task: Task) => {
    const next =
      task.status === "pendiente"
        ? "en progreso"
        : task.status === "en progreso"
          ? "completada"
          : "pendiente";
    setTasks((previous) =>
      previous.map((item) =>
        item.id === task.id ? { ...item, status: next } : item,
      ),
    );
    addActivity("Tarea actualizada", task.title + " · " + next, "success");
  };
  const fileAction = (file: FileItem, action: string) => {
    if (action === "Mover" || action === "Renombrar") {
      setConfirmFile(file);
      setPendingAction(action);
      setStatus("waiting_confirmation");
      return;
    }
    showNotice(
      action + " · " + file.name + " estará disponible al conectar el backend.",
    );
  };
  const confirmAction = (accept: boolean) => {
    if (!confirmFile) return;
    void api.confirmAction(confirmFile.id, accept);
    if (accept) {
      addActivity(
        "Acción confirmada",
        "Operación simulada sobre " + confirmFile.name,
        "success",
      );
      showNotice("Acción confirmada en modo de muestra.");
    } else showNotice("Acción cancelada.");
    setConfirmFile(null);
    setStatus(accept ? "success" : "idle");
    window.setTimeout(() => setStatus("idle"), 1700);
  };
  const taskCounts = {
    pending: tasks.filter((task) => task.status !== "completada").length,
    urgent: tasks.filter((task) => task.urgent && task.status !== "completada")
      .length,
  };
  return (
    <div className="app-shell" data-page={page}>
      <header className="titlebar">
        <div className="title-brand">
          <span className="brand-glyph">
            <span />
          </span>
          <strong>{assistant.toUpperCase()}</strong>
          <span className="title-divider" />
          <span className="title-descriptor">Asistente de escritorio</span>
        </div>
        <div className="title-location">
          <span className="online-dot" />
          <span>
            {apiMode === "mock"
              ? "Modo de muestra"
              : system.online
                ? "Sistema en línea"
                : "Sin conexión"}
          </span>
          <span className="slash">/</span>
          <span>{pageNames[page]}</span>
        </div>
        <div className="title-actions">
          <button
            className="quick-switch"
            onClick={() => setAssistant(ekko ? "jarvis" : "ekko")}
            title="Cambiar entre JARVIS y EKKO"
          >
            {assistant.toUpperCase()}
            <ChevronDown size={13} />
          </button>
          <button
            className="title-icon"
            aria-label="Abrir actividad"
            onClick={() => setPage("activity")}
          >
            <Activity size={17} />
          </button>
        </div>
      </header>
      <div className="main-frame">
        <aside className={"sidebar" + (railExpanded ? " expanded" : "")}>
          <button className="rail-menu" aria-label={railExpanded ? "Contraer menú" : "Expandir menú"} aria-expanded={railExpanded} onClick={() => setRailExpanded(!railExpanded)}><Menu size={19}/></button><span className="sidebar-label">ESPACIO DE TRABAJO</span>
          <nav aria-label="Navegación principal">
            {nav.map(({ id: target, label, icon: Icon }) => (
              <button
                key={target}
                className={"nav-item" + (page === target ? " active" : "")}
                aria-label={label}
                onClick={() => setPage(target)}
              >
                <Icon size={17} strokeWidth={1.8} />
                <span>{label}</span>
                {page === target && <i />}
              </button>
            ))}
          </nav>
          <div className="sidebar-spacer" />
          <div className="sidebar-bottom">
            <div className="sidebar-rule" />
            <button
              className={"nav-item" + (page === "activity" ? " active" : "")}
              aria-label="Actividad"
              onClick={() => setPage("activity")}
            >
              <Activity size={17} />
              <span>Actividad</span>
              <em>{activity.length}</em>
            </button>
            <button
              className={"nav-item" + (page === "settings" ? " active" : "")}
              aria-label="Configuración"
              onClick={() => setPage("settings")}
            >
              <Settings2 size={17} />
              <span>Configuración</span>
            </button>
            <div className="sidebar-presence">
              <span className="presence-light" />
              <div>
                <strong>{assistant.toUpperCase()} ACTIVO</strong>
                <small>{ekko ? "A tu ritmo" : "Modo operacional"}</small>
              </div>
            </div>
          </div>
        </aside>
        <main className="workspace" id="main-content">
          {page === "home" && (
            <div className="home-page cinematic-home">
              <div className="home-topline">
                <div className="home-wordmark">
                  <strong>{assistant.toUpperCase()}</strong>
                  <span>ASISTENTE DE INTELIGENCIA ARTIFICIAL</span>
                </div>
                <div className="home-clock">
                  <span className="clock-icon"><Clock3 size={17} /></span>
                  <div><strong>{clock.toLocaleTimeString("es-PE", { hour: "2-digit", minute: "2-digit", hourCycle: "h23" })}</strong><small>{clock.toLocaleDateString("es-PE", { weekday: "long", day: "numeric", month: "short" })}</small></div>
                </div>
              </div>
              <section className="hero">
                <div className="hero-copy">
                  <span className="hero-kicker">{ekko ? "TU DÍA, CON CLARIDAD" : "CONTROL Y CONTEXTO EN TIEMPO REAL"}</span>
                  <h1>{ekko ? <>Hola,<br /><em>Sebastián.</em></> : <>Buenas tardes,<br /><em>Sebastián.</em></>}</h1>
                  <p>{ekko ? "Todo en orden. ¿En qué te ayudo hoy?" : "¿En qué puedo ayudarte hoy?"}</p>
                  <div className="quick-actions">
                    {ekko ? (
                      <>
                        <button onClick={() => setPage("conversation")}><Command size={20}/><span>Continuar<br/>conversación</span></button>
                        <button onClick={() => setPage("tasks")}><SquareCheckBig size={20}/><span>Revisar<br/>tareas</span></button>
                        <button onClick={() => setPage("files")}><Files size={20}/><span>Buscar<br/>archivos</span></button>
                        <button onClick={() => setPage("calendar")}><CalendarDays size={20}/><span>Organizar<br/>mi día</span></button>
                      </>
                    ) : (
                      <>
                        <button onClick={() => setPage("tools")}><Command size={20}/><span>Abrir<br/>aplicación</span></button>
                        <button onClick={() => setPage("tools")}><Globe2 size={20}/><span>Buscar<br/>en la web</span></button>
                        <button onClick={() => setPage("files")}><Files size={20}/><span>Gestionar<br/>archivos</span></button>
                        <button onClick={() => setPage("knowledge")}><Sparkles size={20}/><span>Analizar<br/>información</span></button>
                      </>
                    )}
                  </div>
                </div>
                <div className="hero-orb"><Orb status={status} /><span className="orb-caption">{statusText[status]}</span></div>
                <div className="system-panel">
                  <div className="system-head"><strong>{ekko ? "Estado del sistema" : "Sistema"}</strong><span><i className="online-dot"/> {apiMode === "mock" ? "Demo" : "Operativo"}</span></div>
                  <div className="system-metrics">
                    <div><span>CPU</span><strong>{system.cpu}%</strong><i><b style={{width:system.cpu + "%"}}/></i></div>
                    <div><span>RAM</span><strong>{system.memory}%</strong><i><b style={{width:system.memory + "%"}}/></i></div>
                    <div><span>DISCO</span><strong>61%</strong><i><b style={{width:"61%"}}/></i></div>
                  </div>
                  <button className="system-row" onClick={() => setPage("tasks")}><span className="system-row-icon urgent"><SquareCheckBig size={17}/></span><span><strong>{taskCounts.urgent} tarea prioritaria</strong><small>Requiere tu atención</small></span><ChevronRight size={16}/></button>
                  <button className="system-row" onClick={() => setPage("calendar")}><span className="system-row-icon"><CalendarDays size={17}/></span><span><strong>3 reuniones hoy</strong><small>Próxima · 16:00</small></span><ChevronRight size={16}/></button>
                  <button className="system-row" onClick={() => setPage(ekko ? "knowledge" : "files")}><span className="system-row-icon"><Files size={17}/></span><span><strong>{ekko ? "7 fuentes conectadas" : "12 archivos recientes"}</strong><small>{ekko ? "Contexto sincronizado" : "Ver actividad"}</small></span><ChevronRight size={16}/></button>
                </div>
              </section>
              <div className="home-footer-note"><span className="online-dot"/>{ekko ? "EKKO está presente cuando lo necesites" : "JARVIS está listo para actuar"}<span className="note-line"/></div>
            </div>
          )}
          {page === "conversation" && (
            <div className="page-content conversation-page">
              <PageHeader
                title="Conversación"
                subtitle={
                  "Un espacio para pensar y actuar con " +
                  assistant.toUpperCase()
                }
                action={
                  <span className="subtle-badge">
                    <span className="online-dot" /> En línea
                  </span>
                }
              />
              <div className="conversation-intro">
                <Orb status={status} small />
                <div>
                  <strong>
                    {ekko
                      ? "Pensamiento en movimiento."
                      : "Listo para la siguiente instrucción."}
                  </strong>
                  <p>
                    Usa la conversación para reunir contexto, preparar planes y
                    revisar resultados.
                  </p>
                </div>
              </div>
              <div className="conversation-cards">
                <button
                  onClick={() =>
                    void sendMessage("Resume mis prioridades de hoy")
                  }
                >
                  <Sparkles size={17} /> Resume mis prioridades{" "}
                  <ArrowRight size={15} />
                </button>
                <button
                  onClick={() =>
                    void sendMessage(
                      "Busca los archivos recientes del proyecto",
                    )
                  }
                >
                  <Search size={17} /> Busca archivos recientes{" "}
                  <ArrowRight size={15} />
                </button>
                <button onClick={() => setPage("activity")}>
                  <Activity size={17} /> Revisa acciones recientes{" "}
                  <ArrowRight size={15} />
                </button>
              </div>
              <SectionHeader
                title="Historial reciente"
                meta={messages.length + " mensajes"}
              />
              <div className="thread-preview">
                {messages.map((message) => (
                  <div className="thread-message" key={message.id}>
                    <span className={"thread-avatar " + message.role}>
                      {message.role === "user"
                        ? "T"
                        : assistant[0].toUpperCase()}
                    </span>
                    <div>
                      <div className="thread-meta">
                        <strong>
                          {message.role === "user"
                            ? "Tú"
                            : assistant.toUpperCase()}
                        </strong>
                        <time>{message.time}</time>
                      </div>
                      <p>{displayMessage(message)}</p>
                      {message.kind === "plan" && (
                        <ol className="thread-plan">
                          <li>Reunir contexto</li>
                          <li>Revisar acciones</li>
                          <li>Confirmar ejecución</li>
                        </ol>
                      )}
                      {message.kind === "summary" && (
                        <button
                          className="inline-link"
                          onClick={() => setPage("calendar")}
                        >
                          Abrir agenda <ArrowRight size={13} />
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
          {page === "tasks" && (
            <div className="page-content">
              <PageHeader
                title="Tareas"
                subtitle="Tu trabajo en curso, con las prioridades a la vista."
                action={
                  <button
                    className="outline-button"
                    onClick={() => {
                      const title = "Nueva tarea";
                      setTasks((previous) => [
                        {
                          id: id(),
                          title,
                          detail:
                            "Añade los detalles al conectar el servicio local",
                          due: "Sin fecha",
                          status: "pendiente",
                        },
                        ...previous,
                      ]);
                      showNotice("Tarea de muestra creada.");
                    }}
                  >
                    <Plus size={16} /> Nueva tarea
                  </button>
                }
              />
              <div className="page-stats">
                <div>
                  <span>PENDIENTES</span>
                  <strong>{taskCounts.pending}</strong>
                </div>
                <div>
                  <span>PRIORITARIAS</span>
                  <strong>{taskCounts.urgent}</strong>
                </div>
                <div>
                  <span>COMPLETADAS</span>
                  <strong>
                    {
                      tasks.filter((task) => task.status === "completada")
                        .length
                    }
                  </strong>
                </div>
              </div>
              <div className="filter-row">
                {(
                  ["todas", "pendiente", "en progreso", "completada"] as const
                ).map((filter) => (
                  <button
                    key={filter}
                    className={taskFilter === filter ? "selected" : ""}
                    onClick={() => setTaskFilter(filter)}
                  >
                    {filter === "todas" ? "Todas" : filter}
                  </button>
                ))}
              </div>
              <div className="task-list">
                {tasks
                  .filter(
                    (task) =>
                      taskFilter === "todas" || task.status === taskFilter,
                  )
                  .map((task) => (
                    <div className="task-row" key={task.id}>
                      <button
                        className={
                          "task-check " + task.status.replace(" ", "-")
                        }
                        onClick={() => cycleTask(task)}
                        title="Cambiar estado"
                      >
                        {task.status === "completada" && <Check size={15} />}
                      </button>
                      <div>
                        <strong>
                          {task.title}
                          {task.urgent && task.status !== "completada" && (
                            <span className="urgent-label"> · Prioritaria</span>
                          )}
                        </strong>
                        <p>{task.detail}</p>
                      </div>
                      <span
                        className={"task-pill " + (task.urgent ? "urgent" : "")}
                      >
                        {task.status}
                      </span>
                      <time>{task.due}</time>
                      <button
                        className="row-arrow"
                        onClick={() => cycleTask(task)}
                        aria-label={"Cambiar estado de " + task.title}
                      >
                        <ChevronRight size={17} />
                      </button>
                    </div>
                  ))}
              </div>
            </div>
          )}
          {page === "files" && (
            <div className="page-content">
              <PageHeader
                title="Archivos"
                subtitle="Encuentra y organiza lo que necesitas, en un solo lugar."
                action={
                  <button
                    className="outline-button"
                    onClick={() =>
                      showNotice(
                        "La creación de carpetas se activará al conectar el backend.",
                      )
                    }
                  >
                    <FolderPlus size={16} /> Nueva carpeta
                  </button>
                }
              />
              <div className="files-toolbar">
                <SearchField
                  value={fileQuery}
                  onChange={setFileQuery}
                  placeholder="Buscar por nombre o ruta…"
                />
                <span>
                  {
                    files.filter((file) =>
                      (file.name + file.path)
                        .toLowerCase()
                        .includes(fileQuery.toLowerCase()),
                    ).length
                  }{" "}
                  archivos
                </span>
              </div>
              <div className="file-table">
                <div className="file-table-head">
                  <span>NOMBRE</span>
                  <span>TIPO</span>
                  <span>TAMAÑO</span>
                  <span>MODIFICADO</span>
                  <span>RUTA</span>
                  <span>ACCIONES</span>
                </div>
                {files
                  .filter((file) =>
                    (file.name + file.path)
                      .toLowerCase()
                      .includes(fileQuery.toLowerCase()),
                  )
                  .map((file) => (
                    <div className="file-row" key={file.id}>
                      <div className="file-name">
                        <span className="file-type-icon">
                          <FileText size={17} />
                        </span>
                        <strong>{file.name}</strong>
                      </div>
                      <span>{file.type}</span>
                      <span>{file.size}</span>
                      <span>{file.modified}</span>
                      <span className="file-path">{file.path}</span>
                      <div className="file-actions">
                        <button
                          title="Abrir"
                          onClick={() => fileAction(file, "Abrir")}
                        >
                          <ArrowRight size={15} />
                        </button>
                        <button
                          title="Mover"
                          onClick={() => fileAction(file, "Mover")}
                        >
                          <MoveRight size={15} />
                        </button>
                        <button
                          title="Copiar"
                          onClick={() => fileAction(file, "Copiar")}
                        >
                          <Copy size={15} />
                        </button>
                        <button
                          title="Renombrar"
                          onClick={() => fileAction(file, "Renombrar")}
                        >
                          <FilePenLine size={15} />
                        </button>
                      </div>
                    </div>
                  ))}
                {files.filter((file) =>
                  (file.name + file.path)
                    .toLowerCase()
                    .includes(fileQuery.toLowerCase()),
                ).length === 0 && (
                  <div className="empty-state">
                    No hay archivos que coincidan. Prueba otro nombre o ruta.
                  </div>
                )}
              </div>
            </div>
          )}
          {page === "calendar" && (
            <div className="page-content">
              <PageHeader
                title="Calendario"
                subtitle="Tu día organizado, sin perder el contexto."
                action={
                  <span className="subtle-badge">
                    <CalendarDays size={15} /> Hoy
                  </span>
                }
              />
              <div className="calendar-layout">
                <div className="calendar-main">
                  <SectionHeader title="Hoy" meta="3 reuniones" />
                  {[
                    ["09:00", "Revisión de proyecto", "Sala virtual · 45 min"],
                    [
                      "11:30",
                      "Análisis de datos",
                      "Bloque de enfoque · 60 min",
                    ],
                    [
                      "16:00",
                      "Revisión de propuesta",
                      "Equipo de producto · 45 min",
                    ],
                  ].map(([time, title, meta]) => (
                    <div className="calendar-event" key={time}>
                      <time>{time}</time>
                      <span className="event-line" />
                      <div>
                        <strong>{title}</strong>
                        <small>{meta}</small>
                      </div>
                      <button
                        onClick={() =>
                          void sendMessage("Prepárame para " + title)
                        }
                      >
                        Preparar <ArrowRight size={14} />
                      </button>
                    </div>
                  ))}
                </div>
                <div className="calendar-aside">
                  <Clock3 size={19} />
                  <strong>Tu próximo bloque</strong>
                  <p>Revisión de propuesta a las 16:00.</p>
                  <button
                    onClick={() =>
                      void sendMessage(
                        "Resume los puntos para la revisión de propuesta",
                      )
                    }
                  >
                    Preparar resumen <ArrowRight size={14} />
                  </button>
                </div>
              </div>
            </div>
          )}
          {page === "knowledge" && (
            <div className="page-content">
              <PageHeader
                title="Conocimiento"
                subtitle="Información útil, conectada con tus proyectos."
              />
              <SearchField
                value={knowledgeQuery}
                onChange={setKnowledgeQuery}
                placeholder="Buscar en tu conocimiento…"
              />
              <div className="knowledge-grid">
                {[
                  {
                    title: "Proyecto JARVIS",
                    detail: "Diseño, arquitectura y decisiones del producto",
                    count: "8 documentos",
                    icon: Sparkles,
                  },
                  {
                    title: "Reuniones",
                    detail: "Notas y acuerdos de trabajo recientes",
                    count: "12 documentos",
                    icon: CalendarDays,
                  },
                  {
                    title: "Análisis",
                    detail: "Informes, datos y conclusiones",
                    count: "6 documentos",
                    icon: LayoutGrid,
                  },
                ]
                  .filter((item) =>
                    item.title
                      .toLowerCase()
                      .includes(knowledgeQuery.toLowerCase()),
                  )
                  .map((item) => (
                    <button
                      key={item.title}
                      className="knowledge-card"
                      onClick={() =>
                        showNotice(
                          "La consulta de conocimiento se activará al conectar el backend.",
                        )
                      }
                    >
                      <item.icon size={19} />
                      <strong>{item.title}</strong>
                      <p>{item.detail}</p>
                      <span>
                        {item.count}
                        <ArrowRight size={14} />
                      </span>
                    </button>
                  ))}
              </div>
            </div>
          )}
          {page === "tools" && (
            <div className="page-content">
              <PageHeader
                title="Herramientas"
                subtitle="Capacidades disponibles para actuar en tu escritorio."
              />
              <div className="tools-intro">
                <ShieldCheck size={17} />
                <span>
                  Las herramientas con cambios en archivos solicitarán
                  confirmación antes de ejecutarse.
                </span>
              </div>
              <div className="tools-grid">
                {tools.map((tool, index) => {
                  const icons = [
                    Command,
                    Globe2,
                    Search,
                    MoveRight,
                    Copy,
                    FolderPlus,
                    HardDrive,
                  ];
                  const Icon = icons[index];
                  return (
                    <div className="tool-card" key={tool.id}>
                      <div className="tool-card-top">
                        <span className="tool-icon">
                          <Icon size={19} />
                        </span>
                        <span className="available">
                          <span className="online-dot" /> Disponible
                        </span>
                      </div>
                      <strong>{tool.name}</strong>
                      <p>{tool.description}</p>
                      <div className="tool-card-bottom">
                        <span>
                          RIESGO{" "}
                          <b className={"risk-" + tool.risk.toLowerCase()}>
                            {tool.risk}
                          </b>
                        </span>
                        <button
                          onClick={() =>
                            showNotice(
                              tool.name +
                                " estará disponible al conectar el backend.",
                            )
                          }
                          aria-label={"Probar " + tool.name}
                        >
                          <ArrowRight size={16} />
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
          {page === "activity" && (
            <div className="page-content">
              <PageHeader
                title="Actividad"
                subtitle="Un registro claro de lo que ha hecho tu asistente."
              />
              <div className="activity-list">
                {activity.map((item) => (
                  <div className="activity-row" key={item.id}>
                    <time>{item.time}</time>
                    <span className={"activity-symbol " + item.kind}>
                      {item.kind === "success" ? (
                        <Check size={15} />
                      ) : item.kind === "error" ? (
                        <X size={15} />
                      ) : (
                        <Activity size={15} />
                      )}
                    </span>
                    <div>
                      <strong>{item.title}</strong>
                      <p>{item.detail}</p>
                    </div>
                    <span className="activity-kind">
                      {item.kind === "success"
                        ? "Completado"
                        : item.kind === "error"
                          ? "Error"
                          : "Información"}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
          {page === "settings" && (
            <div className="page-content settings-page">
              <PageHeader
                title="Configuración"
                subtitle="Ajusta la experiencia a tu forma de trabajar."
              />
              <SectionHeader title="Apariencia" />
              <div className="settings-panel">
                <div className="setting-row">
                  <div>
                    <strong>Asistente</strong>
                    <p>Elige la identidad que te acompaña.</p>
                  </div>
                  <div className="assistant-choice">
                    <button
                      className={!ekko ? "selected" : ""}
                      onClick={() => setAssistant("jarvis")}
                    >
                      <span className="choice-dot jarvis-dot" /> JARVIS
                    </button>
                    <button
                      className={ekko ? "selected" : ""}
                      onClick={() => setAssistant("ekko")}
                    >
                      <span className="choice-dot ekko-dot" /> EKKO
                    </button>
                  </div>
                </div>
                <div className="setting-row">
                  <div>
                    <strong>Tema</strong>
                    <p>Interfaz oscura optimizada para escritorio.</p>
                  </div>
                  <span className="setting-value">
                    Modo oscuro <Check size={15} />
                  </span>
                </div>
              </div>
              <SectionHeader title="Preferencias" />
              <div className="settings-panel">
                <div className="setting-row">
                  <div>
                    <strong>Voz</strong>
                    <p>Interacción visual preparada para entrada de voz.</p>
                  </div>
                  <span className="setting-value">
                    Preparada <AudioLines size={16} />
                  </span>
                </div>
                <div className="setting-row">
                  <div>
                    <strong>Proveedor de IA</strong>
                    <p>Se configurará desde el servicio local.</p>
                  </div>
                  <span className="setting-value">
                    Pendiente <ChevronRight size={16} />
                  </span>
                </div>
                <div className="setting-row">
                  <div>
                    <strong>Confirmar acciones críticas</strong>
                    <p>
                      Pide autorización antes de mover o modificar archivos.
                    </p>
                  </div>
                  <button
                    className={"toggle " + (criticalConfirm ? "on" : "")}
                    onClick={() => setCriticalConfirm(!criticalConfirm)}
                    aria-label="Confirmar acciones críticas"
                    aria-pressed={criticalConfirm}
                  >
                    <i />
                  </button>
                </div>
                <div className="setting-row">
                  <div>
                    <strong>Inicio automático</strong>
                    <p>Preparado para la futura aplicación de Windows.</p>
                  </div>
                  <button
                    className={"toggle " + (autoStart ? "on" : "")}
                    onClick={() => setAutoStart(!autoStart)}
                    aria-label="Inicio automático"
                    aria-pressed={autoStart}
                  >
                    <i />
                  </button>
                </div>
              </div>
              <div className="settings-foot">
                Fuente de datos actual:{" "}
                {apiMode === "mock"
                  ? "muestras locales"
                  : "servicio local con respaldo de muestras"}
              </div>
            </div>
          )}
        </main>
        <aside className="assistant-panel">
          <div className="assistant-panel-head">
            <div>
              <strong>
                <span className="online-dot" />
                {ekko ? "CONVERSA CON EKKO" : "JARVIS"}
              </strong>
              <small>
                {apiMode === "mock" ? "Demo local" : "En línea"} ·{" "}
                {statusText[status]}
              </small>
            </div>
            <button
              className="quiet-icon"
              aria-label="Abrir conversación"
              onClick={() => setPage("conversation")}
            >
              <MoreHorizontal size={19} />
            </button>
          </div>
          <div className="assistant-feed" ref={feedRef}>
            {messages.map((message) => (
              <div className={"chat-message " + message.role} key={message.id}>
                <div className="chat-meta">
                  <strong>
                    {message.role === "user" ? "Tú" : assistant.toUpperCase()}
                  </strong>
                  <time>{message.time}</time>
                </div>
                <div
                  className={
                    "chat-bubble" +
                    (message.kind === "error" ? " chat-error" : "")
                  }
                >
                  <p>{displayMessage(message)}</p>
                  {message.kind === "plan" && (
                    <ol className="chat-plan">
                      <li>Reunir contexto relevante</li>
                      <li>Revisar las acciones propuestas</li>
                      <li>Ejecutar tras tu confirmación</li>
                    </ol>
                  )}
                  {message.kind === "result" && (
                    <span className="chat-result">
                      <Check size={12} /> Resultado preparado
                    </span>
                  )}
                  {message.kind === "summary" && (
                    <>
                      <div className="summary-details">
                        <div>
                          <strong>03</strong>
                          <span>reuniones</span>
                        </div>
                        <div>
                          <strong>01</strong>
                          <span>prioridad</span>
                        </div>
                        <div>
                          <strong>16:00</strong>
                          <span>propuesta</span>
                        </div>
                      </div>
                      <div className="chat-actions">
                        <button onClick={() => setPage("calendar")}>
                          Ver agenda completa <ArrowRight size={13} />
                        </button>
                        <button
                          onClick={() => {
                            setPage("tasks");
                            showNotice("Crea un recordatorio desde Tareas.");
                          }}
                        >
                          {ekko ? "Crear carpeta organizada" : "Crear recordatorio"} <ArrowRight size={13} />
                        </button>
                      </div>
                    </>
                  )}
                  {message.kind === "file" && (
                    <div className="chat-file">
                      <FileText size={17} />
                      <span>
                        <strong>Reporte_Q3.pdf</strong>
                        <small>PDF · 2,4 MB</small>
                      </span>
                      <button onClick={() => setPage("files")}>Ver</button>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
          {confirmFile && (
            <div className="confirmation-card">
              <span>CONFIRMACIÓN REQUERIDA</span>
              <strong>{pendingAction} archivo</strong>
              <p>
                {confirmFile.name}
                <br />
                {confirmFile.path}
                {pendingAction === "Mover" && (
                  <>
                    {" "}
                    <MoveRight size={12} /> Documentos / Organizados
                  </>
                )}
              </p>
              <div>
                <button onClick={() => confirmAction(false)}>Cancelar</button>
                <button onClick={() => confirmAction(true)}>Confirmar</button>
              </div>
            </div>
          )}
          <form className="assistant-compose" onSubmit={onSend}>
            <div className="compose-field">
              <input
                aria-label="Mensaje para el asistente"
                value={input}
                onChange={(event) => setInput(event.target.value)}
                placeholder={
                  ekko
                    ? "Escribe o habla con EKKO…"
                    : "Escribe una instrucción…"
                }
              />
              <button aria-label="Enviar mensaje" disabled={!input.trim()}>
                <Send size={16} />
              </button>
            </div>
            <small>
              <ShieldCheck size={13} /> Acciones críticas requieren confirmación
            </small>
          </form>
        </aside>
      </div>
      <footer className={"voice-bar voice-" + status}>
        <div className="voice-label">
          <AudioLines size={18} />
          <span>
            {status === "idle"
              ? (ekko ? "Habla con naturalidad…" : "Dime qué necesitas…")
              : statusText[status]}
          </span>
        </div>
        <div className="voice-center">
          <div className="waveform left">
            {bars.map((height, index) => (
              <i
                key={index}
                style={{ height: height, animationDelay: index * -0.06 + "s" }}
              />
            ))}
          </div>
          <button
            className={
              "voice-mic" + (status === "listening" ? " listening" : "")
            }
            aria-label={
              status === "listening" ? "Detener escucha" : "Activar escucha"
            }
            aria-pressed={status === "listening"}
            onClick={() => {
              const next = status === "listening" ? "idle" : "listening";
              setStatus(next);
              if (next === "listening")
                showNotice(
                  "Modo de escucha visual. La captura de voz estará disponible al conectar el backend.",
                );
            }}
          >
            <Mic size={23} />
          </button>
          <div className="waveform right">
            {bars.map((height, index) => (
              <i
                key={index}
                style={{ height: height, animationDelay: index * -0.06 + "s" }}
              />
            ))}
          </div>
        </div>
        <div className="voice-mode">
          {ekko ? "PRESENCIA DISCRETA" : "CONTROL POR VOZ"}
          <button
            aria-label="Restablecer estado"
            onClick={() => setStatus("idle")}
          >
            <X size={15} />
          </button>
        </div>
      </footer>
      {notice && (
        <div className="toast" role="status">
          <CheckCircle2 size={17} />
          {notice}
        </div>
      )}
    </div>
  );
}




