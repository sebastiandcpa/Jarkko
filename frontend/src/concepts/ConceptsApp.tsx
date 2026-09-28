import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import {
  Activity,
  ArrowLeft,
  ArrowRight,
  Boxes,
  CalendarDays,
  Check,
  ChevronRight,
  CircleHelp,
  Cpu,
  FolderOpen,
  Gauge,
  Grid2X2,
  Menu,
  MessageCircle,
  Mic,
  Orbit,
  Send,
  Settings2,
  ShieldCheck,
  Sparkles,
  X,
} from "lucide-react";
import city from "../assets/jarvis-scene.png";
import orb from "../assets/jarkko-orb-core.png";
import { BlackHoleVisual } from "./BlackHoleVisual";

type Panel = "sistema" | "agenda" | "chat" | "archivos" | "herramientas";
type ConceptId =
  "arc" | "aether" | "vector" | "pulse" | "eclipse" | "prism" | "flux";
type SceneProps = {
  listening: boolean;
  time: string;
  open: (panel: Panel) => void;
  toggleVoice: () => void;
};

const concepts: {
  id: ConceptId;
  name: string;
  eyebrow: string;
  description: string;
}[] = [
  {
    id: "arc",
    name: "ARC",
    eyebrow: "CENTRO DE MANDO",
    description:
      "Un núcleo técnico y paneles de control con energía azul y ámbar.",
  },
  {
    id: "aether",
    name: "AETHER",
    eyebrow: "PRESENCIA HOLOGRÁFICA",
    description:
      "La esfera como protagonista, con controles discretos en los bordes.",
  },
  {
    id: "vector",
    name: "VECTOR",
    eyebrow: "INTELIGENCIA OPERATIVA",
    description:
      "Información, herramientas y decisiones visibles de un vistazo.",
  },
  {
    id: "pulse",
    name: "PULSE",
    eyebrow: "VOZ Y MOVIMIENTO",
    description: "Un espacio inmersivo con un núcleo vivo y muy poca interfaz.",
  },
  {
    id: "eclipse",
    name: "ECLIPSE",
    eyebrow: "HORIZONTE DE EVENTOS",
    description:
      "Un agujero negro realista con disco de acreción y luz curvada.",
  },
  {
    id: "prism",
    name: "PRISMA",
    eyebrow: "INTELIGENCIA CRISTALINA",
    description:
      "Un cristal facetado responde con destellos violetas, turquesa y oro.",
  },
  {
    id: "flux",
    name: "FLUJO",
    eyebrow: "ENERGÍA EN MOVIMIENTO",
    description: "Una cinta de luz multicolor da forma a la voz de Jarkko.",
  },
];

const actionDetails: Record<
  Panel,
  { title: string; intro: string; rows: string[] }
> = {
  sistema: {
    title: "Estado del sistema",
    intro: "Vista de muestra del rendimiento y la conexión de Jarkko.",
    rows: [
      "CPU · 28%",
      "Memoria · 42%",
      "Conexión · Estable",
      "Núcleo visual · Activo",
    ],
  },
  agenda: {
    title: "Agenda de hoy",
    intro: "Así se presentaría el contexto de tu día en este diseño.",
    rows: [
      "09:30 · Revisión de prioridades",
      "12:00 · Reunión de proyecto",
      "16:00 · Bloque de enfoque",
      "18:30 · Resumen del día",
    ],
  },
  chat: {
    title: "Conversación",
    intro: "Prueba el panel y envía un mensaje de ejemplo.",
    rows: [],
  },
  archivos: {
    title: "Archivos recientes",
    intro: "Una vista interactiva de cómo Jarkko encontraría tus documentos.",
    rows: [
      "Plan_de_trabajo.pdf",
      "Ideas_Jarkko.md",
      "Resumen_semanal.docx",
      "Diseño_interfaz.fig",
    ],
  },
  herramientas: {
    title: "Herramientas",
    intro: "Accesos rápidos disponibles en el concepto visual.",
    rows: [
      "Buscar en la web",
      "Organizar archivos",
      "Crear recordatorio",
      "Analizar información",
    ],
  },
};

function ActionButton({
  icon,
  children,
  onClick,
  className = "",
}: {
  icon: ReactNode;
  children: ReactNode;
  onClick: () => void;
  className?: string;
}) {
  return (
    <button
      type="button"
      className={`concept-action ${className}`}
      onClick={onClick}
    >
      {icon}
      <span>{children}</span>
      <ArrowRight size={14} />
    </button>
  );
}

function VoiceButton({
  listening,
  toggleVoice,
  className = "",
}: Pick<SceneProps, "listening" | "toggleVoice"> & { className?: string }) {
  return (
    <button
      type="button"
      className={`concept-voice ${className} ${listening ? "is-listening" : ""}`}
      aria-label={
        listening
          ? "Detener simulación de escucha"
          : "Activar simulación de escucha"
      }
      aria-pressed={listening}
      onClick={toggleVoice}
    >
      <Mic size={24} strokeWidth={1.6} />
    </button>
  );
}

function ArcScene({ listening, time, open, toggleVoice }: SceneProps) {
  return (
    <div
      className="concept-scene arc-scene"
      style={{
        backgroundImage: `linear-gradient(90deg, #020912ed, #04111bdc 45%, #020912eb), url(${city})`,
      }}
    >
      <div className="arc-grid" aria-hidden="true" />
      <div className="arc-topline">
        <span>
          <i /> JARKKO / ARC SYSTEM
        </span>
        <span>PROTOCOLO PERSONAL · {time}</span>
      </div>
      <aside className="arc-column arc-column-left">
        <div className="arc-label">01 / CONEXIÓN</div>
        <h1>
          Buenas noches,
          <br />
          <strong>Sebastián.</strong>
        </h1>
        <p>Todo el contexto que necesitas, en un solo lugar.</p>
        <div className="arc-rule" />
        <ActionButton
          icon={<CalendarDays size={18} />}
          onClick={() => open("agenda")}
        >
          Abrir agenda
        </ActionButton>
        <ActionButton
          icon={<FolderOpen size={18} />}
          onClick={() => open("archivos")}
        >
          Encontrar archivos
        </ActionButton>
        <ActionButton
          icon={<MessageCircle size={18} />}
          onClick={() => open("chat")}
        >
          Conversar
        </ActionButton>
        <div className="arc-left-bottom">
          <span>ACCESO AUTORIZADO</span>
          <ShieldCheck size={18} />
          <b>SESIÓN ACTIVA</b>
        </div>
      </aside>
      <section className="arc-center" aria-label="Núcleo holográfico ARC">
        <div className="arc-halo" />
        <div className="arc-reactor">
          <div className="arc-ring arc-ring-one" />
          <div className="arc-ring arc-ring-two" />
          <div className="arc-ring arc-ring-three" />
          <div className="arc-ring arc-ring-four" />
          <div className="arc-reactor-core">
            <span className="arc-triangle" />
            <span className="arc-core-dot" />
          </div>
        </div>
        <div className="arc-center-caption">
          <span>NÚCLEO JARKKO</span>
          <strong>{listening ? "ESCUCHANDO" : "EN LÍNEA"}</strong>
          <span>HACE POSIBLE LO IMPOSIBLE</span>
        </div>
      </section>
      <aside className="arc-column arc-column-right">
        <div className="arc-label">02 / TELEMETRÍA</div>
        <div className="arc-metric">
          <span>ESTADO GENERAL</span>
          <strong>OPERATIVO</strong>
          <small>Todos los módulos activos</small>
        </div>
        <div className="arc-bars">
          <div>
            <span>PROCESAMIENTO</span>
            <b>68%</b>
            <i style={{ width: "68%" }} />
          </div>
          <div>
            <span>MEMORIA</span>
            <b>42%</b>
            <i style={{ width: "42%" }} />
          </div>
          <div>
            <span>SINCRONIZACIÓN</span>
            <b>91%</b>
            <i style={{ width: "91%" }} />
          </div>
        </div>
        <button
          type="button"
          className="arc-alert"
          onClick={() => open("sistema")}
        >
          <Activity size={18} />
          <span>
            Informe de sistemas<small>Ver detalles en tiempo real</small>
          </span>
          <ChevronRight size={17} />
        </button>
        <div className="arc-right-bottom">
          <span>RESPUESTA ESTIMADA</span>
          <strong>0.8 s</strong>
        </div>
      </aside>
      <div className="arc-voice-dock">
        <span className="arc-wave" />
        <VoiceButton listening={listening} toggleVoice={toggleVoice} />
        <span className="arc-wave arc-wave-right" />
        <span className="arc-voice-label">
          {listening ? "ESCUCHANDO TU IDEA…" : "PULSA PARA HABLAR"}
        </span>
      </div>
    </div>
  );
}

function AetherScene({ listening, time, open, toggleVoice }: SceneProps) {
  return (
    <div className="concept-scene aether-scene">
      <header className="aether-head">
        <div>
          <span>JARKKO / 02</span>
          <strong>Presencia que piensa contigo.</strong>
        </div>
        <span>
          {time} <i /> CONECTADO
        </span>
      </header>
      <button
        type="button"
        className="aether-edge aether-edge-left"
        aria-label="Abrir herramientas"
        onClick={() => open("herramientas")}
      >
        <Grid2X2 size={21} />
        <span>MENÚ</span>
      </button>
      <button
        type="button"
        className="aether-edge aether-edge-right"
        aria-label="Abrir conversación"
        onClick={() => open("chat")}
      >
        <MessageCircle size={21} />
        <span>CHAT</span>
      </button>
      <div className="aether-orbit aether-orbit-one" />
      <div className="aether-orbit aether-orbit-two" />
      <div className="aether-orb">
        <img src={orb} alt="Esfera holográfica de Jarkko" draggable={false} />
      </div>
      <div className="aether-tag aether-tag-left">
        <span>CONTEXTO</span>
        <strong>7 fuentes conectadas</strong>
        <button type="button" onClick={() => open("archivos")}>
          Ver fuentes <ArrowRight size={12} />
        </button>
      </div>
      <div className="aether-tag aether-tag-right">
        <span>ESTADO DEL NÚCLEO</span>
        <strong>{listening ? "Escucha activa" : "Atento a ti"}</strong>
        <button type="button" onClick={() => open("sistema")}>
          Ver sistema <ArrowRight size={12} />
        </button>
      </div>
      <div className="aether-voice">
        <span>{listening ? "Te escucho…" : "¿En qué te ayudo hoy?"}</span>
        <VoiceButton listening={listening} toggleVoice={toggleVoice} />
        <span className="aether-wave" />
      </div>
      <div className="aether-foot">
        PENSAMIENTO EN MOVIMIENTO <span>•</span> SIEMPRE PRESENTE
      </div>
    </div>
  );
}

function VectorScene({ listening, time, open, toggleVoice }: SceneProps) {
  return (
    <div className="concept-scene vector-scene">
      <div className="vector-grid" aria-hidden="true" />
      <aside className="vector-rail">
        <b>
          J<span>·</span>
        </b>
        <button
          type="button"
          aria-label="Abrir herramientas"
          onClick={() => open("herramientas")}
        >
          <Grid2X2 size={19} />
        </button>
        <button
          type="button"
          aria-label="Abrir archivos"
          onClick={() => open("archivos")}
        >
          <FolderOpen size={19} />
        </button>
        <button
          type="button"
          aria-label="Abrir agenda"
          onClick={() => open("agenda")}
        >
          <CalendarDays size={19} />
        </button>
        <button
          type="button"
          aria-label="Abrir conversación"
          onClick={() => open("chat")}
        >
          <MessageCircle size={19} />
        </button>
        <span />
        <button
          type="button"
          aria-label="Abrir sistema"
          onClick={() => open("sistema")}
        >
          <Settings2 size={19} />
        </button>
      </aside>
      <div className="vector-main">
        <header className="vector-head">
          <div>
            <span>JARKKO / VECTOR</span>
            <h1>Claridad para actuar.</h1>
          </div>
          <div className="vector-head-time">
            <b>{time}</b>
            <span>INTERFAZ OPERATIVA</span>
          </div>
        </header>
        <div className="vector-content">
          <section className="vector-core-card">
            <div className="vector-card-label">
              <span>01 — NÚCLEO DE INTELIGENCIA</span>
              <span>{listening ? "CAPTANDO VOZ" : "ACTIVO"}</span>
            </div>
            <div className="vector-globe">
              <div className="vector-globe-lat lat-one" />
              <div className="vector-globe-lat lat-two" />
              <div className="vector-globe-lat lat-three" />
              <div className="vector-globe-long long-one" />
              <div className="vector-globe-long long-two" />
              <div className="vector-globe-inner">
                <Sparkles size={52} strokeWidth={0.8} />
              </div>
            </div>
            <div className="vector-globe-foot">
              <span>
                {listening
                  ? "Análisis de voz en curso"
                  : "Esperando tu siguiente idea"}
              </span>
              <VoiceButton listening={listening} toggleVoice={toggleVoice} />
            </div>
          </section>
          <section className="vector-work">
            <div className="vector-card-label">
              <span>02 — ESPACIO DE TRABAJO</span>
              <button type="button" onClick={() => open("herramientas")}>
                VER TODO <ArrowRight size={12} />
              </button>
            </div>
            <h2>¿Qué hacemos ahora?</h2>
            <div className="vector-action-grid">
              <button type="button" onClick={() => open("agenda")}>
                <CalendarDays />
                <strong>Mi día</strong>
                <small>Agenda y prioridades</small>
                <ArrowRight size={15} />
              </button>
              <button type="button" onClick={() => open("archivos")}>
                <FolderOpen />
                <strong>Archivos</strong>
                <small>Encuentra lo esencial</small>
                <ArrowRight size={15} />
              </button>
              <button type="button" onClick={() => open("chat")}>
                <MessageCircle />
                <strong>Conversar</strong>
                <small>Piensa en voz alta</small>
                <ArrowRight size={15} />
              </button>
              <button type="button" onClick={() => open("sistema")}>
                <Gauge />
                <strong>Sistema</strong>
                <small>Todo bajo control</small>
                <ArrowRight size={15} />
              </button>
            </div>
            <div className="vector-strip">
              <span>
                <i /> SINCRONIZADO
              </span>
              <span>4 TAREAS PRIORITARIAS</span>
              <button type="button" onClick={() => open("agenda")}>
                REVISAR <ChevronRight size={13} />
              </button>
            </div>
          </section>
        </div>
        <footer className="vector-bottom">
          <span>JARKKO ESTÁ LISTO</span>
          <span>PROTOCOLO SEGURO / v03</span>
        </footer>
      </div>
    </div>
  );
}

function PulseScene({ listening, time, open, toggleVoice }: SceneProps) {
  return (
    <div className="concept-scene pulse-scene">
      <div className="pulse-stars" aria-hidden="true" />
      <header className="pulse-head">
        <div>
          <span className="pulse-brand-mark">J</span>
          <span>
            JARKKO <small>/ PULSE</small>
          </span>
        </div>
        <div>
          <span>{time}</span>
          <button
            type="button"
            aria-label="Abrir sistema"
            onClick={() => open("sistema")}
          >
            <Settings2 size={18} />
          </button>
        </div>
      </header>
      <div className="pulse-side pulse-side-left">
        <span>01</span>
        <i />
        <span>04</span>
      </div>
      <div className="pulse-side pulse-side-right">
        <span>ESCUCHA</span>
        <i />
        <span>RESPUESTA</span>
      </div>
      <main className="pulse-center">
        <span className="pulse-kicker">UN ESPACIO PARA PENSAR</span>
        <h1>
          Tu siguiente idea
          <br />
          empieza aquí.
        </h1>
        <div className="pulse-orb">
          <div className="pulse-orb-aura" />
          <div className="pulse-orb-shell">
            <div className="pulse-orb-shimmer" />
            <div className="pulse-orb-core" />
          </div>
          <span className="pulse-orbit pulse-orbit-a" />
          <span className="pulse-orbit pulse-orbit-b" />
        </div>
        <p>
          {listening
            ? "Te escucho. Sigue hablando con naturalidad."
            : "Habla con Jarkko o explora lo que necesitas."}
        </p>
        <div className="pulse-voice-row">
          <span className="pulse-wave" />
          <VoiceButton listening={listening} toggleVoice={toggleVoice} />
          <span className="pulse-wave pulse-wave-right" />
        </div>
        <div className="pulse-actions">
          <button type="button" onClick={() => open("chat")}>
            <MessageCircle size={16} /> Conversar
          </button>
          <button type="button" onClick={() => open("agenda")}>
            <CalendarDays size={16} /> Mi día
          </button>
          <button type="button" onClick={() => open("archivos")}>
            <FolderOpen size={16} /> Archivos
          </button>
        </div>
      </main>
      <div className="pulse-foot">
        <span>INTELIGENCIA EN CALMA</span>
        <span>
          <i /> LISTO PARA TI
        </span>
      </div>
    </div>
  );
}

function EclipseScene({ listening, time, open, toggleVoice }: SceneProps) {
  return (
    <div className="concept-scene eclipse-scene">
      <BlackHoleVisual listening={listening} />
      <header className="eclipse-head">
        <div>
          <span>JARKKO / ECLIPSE</span>
          <strong>Todo gira alrededor de tus ideas.</strong>
        </div>
        <div>
          <span>{time}</span>
          <i /> SISTEMA EN LÍNEA
        </div>
      </header>
      <button
        type="button"
        className="eclipse-control eclipse-control-left"
        aria-label="Abrir herramientas"
        onClick={() => open("herramientas")}
      >
        <Grid2X2 size={20} />
        <span>EXPLORAR</span>
      </button>
      <button
        type="button"
        className="eclipse-control eclipse-control-right"
        aria-label="Abrir conversación"
        onClick={() => open("chat")}
      >
        <MessageCircle size={20} />
        <span>CONVERSAR</span>
      </button>
      <div className="eclipse-voice">
        <div>
          <span>HORIZONTE ACTIVO</span>
          <strong>
            {listening ? "Captando tu voz…" : "Listo para escucharte"}
          </strong>
        </div>
        <VoiceButton listening={listening} toggleVoice={toggleVoice} />
        <div className="eclipse-wave" />
      </div>
      <footer className="eclipse-foot">
        <span>CAMBIA EL CENTRO DE GRAVEDAD</span>
        <span>05 / JARKKO LAB</span>
      </footer>
    </div>
  );
}

function PrismScene({ listening, time, open, toggleVoice }: SceneProps) {
  return (
    <div className="concept-scene prism-scene">
      <div className="prism-light-grid" aria-hidden="true" />
      <header className="prism-head">
        <div>
          <span>JARKKO / PRISMA</span>
          <strong>Una idea. Infinitas perspectivas.</strong>
        </div>
        <div>
          <i /> {time} · ACTIVO
        </div>
      </header>
      <button
        type="button"
        className="prism-edge prism-edge-left"
        aria-label="Abrir herramientas"
        onClick={() => open("herramientas")}
      >
        <Grid2X2 size={20} />
        <span>MENÚ</span>
      </button>
      <button
        type="button"
        className="prism-edge prism-edge-right"
        aria-label="Abrir conversación"
        onClick={() => open("chat")}
      >
        <MessageCircle size={20} />
        <span>CHAT</span>
      </button>
      <div className="prism-halo" />
      <div
        className="prism-object"
        role="img"
        aria-label="Cristal holográfico facetado de Jarkko"
      >
        <div className="prism-shard shard-a" />
        <div className="prism-shard shard-b" />
        <div className="prism-shard shard-c" />
        <svg viewBox="0 0 500 600" aria-hidden="true">
          <defs>
            <linearGradient id="prism-left" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0" stopColor="#6ceaff" />
              <stop offset=".5" stopColor="#6a75ff" />
              <stop offset="1" stopColor="#29104e" />
            </linearGradient>
            <linearGradient id="prism-right" x1="1" y1="0" x2="0" y2="1">
              <stop offset="0" stopColor="#ffc26a" />
              <stop offset=".52" stopColor="#df64f7" />
              <stop offset="1" stopColor="#42208e" />
            </linearGradient>
            <linearGradient id="prism-core" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0" stopColor="#e6fbff" />
              <stop offset=".5" stopColor="#94ccff" />
              <stop offset="1" stopColor="#ff91e8" />
            </linearGradient>
          </defs>
          <path
            className="prism-outline"
            d="M250 20 L405 165 L385 425 L250 575 L115 425 L95 165 Z"
          />
          <path
            className="prism-face"
            d="M250 20 L95 165 L115 425 L250 575 Z"
            fill="url(#prism-left)"
          />
          <path
            className="prism-face"
            d="M250 20 L405 165 L385 425 L250 575 Z"
            fill="url(#prism-right)"
          />
          <path className="prism-facet" d="M250 20 L95 165 L250 210 Z" />
          <path className="prism-facet" d="M250 20 L405 165 L250 210 Z" />
          <path
            className="prism-facet prism-facet-bright"
            d="M115 425 L250 210 L250 575 Z"
          />
          <path
            className="prism-facet prism-facet-bright"
            d="M385 425 L250 210 L250 575 Z"
          />
          <path
            className="prism-heart"
            d="M250 210 L318 290 L250 410 L182 290 Z"
            fill="url(#prism-core)"
          />
          <path
            className="prism-lines"
            d="M250 20 L250 575 M95 165 L250 210 L405 165 M115 425 L250 210 L385 425 M115 425 L250 575 L385 425"
          />
        </svg>
      </div>
      <div className="prism-chip prism-chip-left">
        <span>CAPA 01</span>
        <strong>Comprende</strong>
        <button type="button" onClick={() => open("archivos")}>
          Fuentes conectadas <ChevronRight size={13} />
        </button>
      </div>
      <div className="prism-chip prism-chip-right">
        <span>CAPA 02</span>
        <strong>Organiza</strong>
        <button type="button" onClick={() => open("agenda")}>
          Tu día de hoy <ChevronRight size={13} />
        </button>
      </div>
      <div className="prism-voice">
        <span>
          {listening ? "La luz responde a tu voz" : "Activa el núcleo"}
        </span>
        <VoiceButton listening={listening} toggleVoice={toggleVoice} />
        <span className="prism-levels">
          <i />
          <i />
          <i />
          <i />
          <i />
          <i />
          <i />
        </span>
      </div>
      <div className="prism-foot">
        LA INTELIGENCIA TIENE NUEVA FORMA <span>•</span> 06 / 07
      </div>
    </div>
  );
}

function FluxScene({ listening, time, open, toggleVoice }: SceneProps) {
  return (
    <div className="concept-scene flux-scene">
      <div className="flux-grid" aria-hidden="true" />
      <header className="flux-head">
        <div>
          <span>
            JARKKO <i /> FLUJO
          </span>
          <strong>La voz toma forma.</strong>
        </div>
        <span>{time} / CONEXIÓN ESTABLE</span>
      </header>
      <button
        type="button"
        className="flux-edge flux-edge-left"
        aria-label="Abrir herramientas"
        onClick={() => open("herramientas")}
      >
        <Menu size={21} />
        <span>EXPLORAR</span>
      </button>
      <button
        type="button"
        className="flux-edge flux-edge-right"
        aria-label="Abrir conversación"
        onClick={() => open("chat")}
      >
        <MessageCircle size={21} />
        <span>CONVERSAR</span>
      </button>
      <div
        className="flux-field"
        role="img"
        aria-label="Cintas de energía multicolor de Jarkko"
      >
        <div className="flux-ambient" />
        <svg
          viewBox="0 0 1000 500"
          preserveAspectRatio="xMidYMid meet"
          aria-hidden="true"
        >
          <defs>
            <linearGradient id="flux-one">
              <stop offset="0" stopColor="#46e6d0" />
              <stop offset=".35" stopColor="#6cf7a2" />
              <stop offset=".67" stopColor="#ffe179" />
              <stop offset="1" stopColor="#ff7b9d" />
            </linearGradient>
            <linearGradient id="flux-two">
              <stop offset="0" stopColor="#60beff" />
              <stop offset=".48" stopColor="#a878ff" />
              <stop offset="1" stopColor="#ff7da1" />
            </linearGradient>
            <filter id="flux-glow">
              <feGaussianBlur stdDeviation="12" />
            </filter>
          </defs>
          <path
            className="flux-blur"
            d="M-40 270 C175 -20 300 520 500 250 S825 -40 1040 240"
            stroke="url(#flux-one)"
            filter="url(#flux-glow)"
          />
          <path
            className="flux-ribbon flux-ribbon-a"
            d="M-40 270 C175 -20 300 520 500 250 S825 -40 1040 240"
            stroke="url(#flux-one)"
          />
          <path
            className="flux-ribbon flux-ribbon-b"
            d="M-40 170 C185 480 320 0 500 250 S810 505 1040 190"
            stroke="url(#flux-two)"
          />
          <path
            className="flux-filament"
            d="M-40 285 C175 -5 300 535 500 265 S825 -25 1040 255"
            stroke="#d8fff4"
          />
          <path
            className="flux-filament flux-filament-two"
            d="M-40 152 C185 462 320 -18 500 232 S810 487 1040 172"
            stroke="#edd5ff"
          />
        </svg>
        <div className="flux-core-line" />
      </div>
      <div className="flux-top-caption">
        <span>RESPIRA. PIENSA. ACTÚA.</span>
        <strong>
          {listening ? "Estoy escuchando…" : "¿Qué tienes en mente?"}
        </strong>
      </div>
      <div className="flux-lower">
        <button type="button" onClick={() => open("agenda")}>
          <CalendarDays size={18} /> Tu día <ArrowRight size={14} />
        </button>
        <div className="flux-voice">
          <span className="flux-voice-line" />
          <VoiceButton listening={listening} toggleVoice={toggleVoice} />
          <span className="flux-voice-line flux-voice-line-right" />
        </div>
        <button type="button" onClick={() => open("archivos")}>
          <FolderOpen size={18} /> Archivos <ArrowRight size={14} />
        </button>
      </div>
      <footer className="flux-foot">
        <span>ENERGÍA QUE SE CONVIERTE EN ACCIÓN</span>
        <button type="button" onClick={() => open("sistema")}>
          ESTADO DEL SISTEMA <Activity size={14} />
        </button>
      </footer>
    </div>
  );
}

export function ConceptsApp() {
  const initial = new URLSearchParams(window.location.search).get(
    "concept",
  ) as ConceptId | null;
  const [active, setActive] = useState<ConceptId>(
    concepts.some((item) => item.id === initial) ? initial! : "arc",
  );
  const [listening, setListening] = useState(false);
  const [panel, setPanel] = useState<Panel | null>(null);
  const [message, setMessage] = useState("");
  const [sent, setSent] = useState<string[]>([]);
  const [clock, setClock] = useState(new Date());
  const current = concepts.find((item) => item.id === active)!;
  const time = clock.toLocaleTimeString("es-PE", {
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  });

  useEffect(() => {
    const timer = window.setInterval(() => setClock(new Date()), 30000);
    return () => window.clearInterval(timer);
  }, []);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setPanel(null);
      if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
      if (event.target instanceof HTMLInputElement) return;
      const index = concepts.findIndex((item) => item.id === active);
      const next =
        (index + (event.key === "ArrowRight" ? 1 : -1) + concepts.length) %
        concepts.length;
      changeConcept(concepts[next].id);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [active]);

  function changeConcept(id: ConceptId) {
    setActive(id);
    setListening(false);
    setPanel(null);
    const url = new URL(window.location.href);
    url.searchParams.set("concept", id);
    window.history.replaceState({}, "", url);
  }
  function submitMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!message.trim()) return;
    setSent((old) => [...old, message.trim()]);
    setMessage("");
  }
  const sceneProps: SceneProps = {
    listening,
    time,
    open: setPanel,
    toggleVoice: () => setListening((value) => !value),
  };

  return (
    <div
      className={`concept-gallery theme-${active} ${listening ? "is-listening" : ""}`}
    >
      <nav className="gallery-nav" aria-label="Comparar conceptos">
        <div className="gallery-wordmark">
          <span className="gallery-glyph">
            <Orbit size={19} />
          </span>
          <div>
            <strong>JARKKO</strong>
            <small>LABORATORIO DE DISEÑO</small>
          </div>
        </div>
        <div className="gallery-switcher">
          {concepts.map((item, index) => (
            <button
              type="button"
              key={item.id}
              className={active === item.id ? "active" : ""}
              aria-current={active === item.id ? "page" : undefined}
              onClick={() => changeConcept(item.id)}
            >
              <span>0{index + 1}</span>
              {item.name}
            </button>
          ))}
        </div>
        <a className="gallery-back" href="/">
          Volver a Jarkko <ArrowRight size={15} />
        </a>
      </nav>
      <div className="gallery-stage" key={active}>
        {active === "arc" && <ArcScene {...sceneProps} />}
        {active === "aether" && <AetherScene {...sceneProps} />}
        {active === "vector" && <VectorScene {...sceneProps} />}
        {active === "pulse" && <PulseScene {...sceneProps} />}
        {active === "eclipse" && <EclipseScene {...sceneProps} />}
        {active === "prism" && <PrismScene {...sceneProps} />}
        {active === "flux" && <FluxScene {...sceneProps} />}
      </div>
      <div className="gallery-caption">
        <div>
          <span>
            CONCEPTO{" "}
            {String(
              concepts.findIndex((item) => item.id === active) + 1,
            ).padStart(2, "0")}{" "}
            / {String(concepts.length).padStart(2, "0")}
          </span>
          <strong>{current.eyebrow}</strong>
          <small>{current.description}</small>
        </div>
        <div className="gallery-caption-actions">
          <span>Prueba los controles en pantalla</span>
          <button
            type="button"
            aria-label="Concepto anterior"
            onClick={() =>
              changeConcept(
                concepts[
                  (concepts.findIndex((item) => item.id === active) +
                    concepts.length -
                    1) %
                    concepts.length
                ].id,
              )
            }
          >
            <ArrowLeft size={19} />
          </button>
          <button
            type="button"
            aria-label="Concepto siguiente"
            onClick={() =>
              changeConcept(
                concepts[
                  (concepts.findIndex((item) => item.id === active) + 1) %
                    concepts.length
                ].id,
              )
            }
          >
            <ArrowRight size={19} />
          </button>
        </div>
      </div>
      {panel && (
        <div
          className="concept-modal-backdrop"
          onMouseDown={() => setPanel(null)}
        >
          <aside
            className="concept-modal"
            role="dialog"
            aria-modal="true"
            aria-label={actionDetails[panel].title}
            onMouseDown={(event) => event.stopPropagation()}
          >
            <header>
              <span>JARKKO / VISTA DE MUESTRA</span>
              <button
                type="button"
                aria-label="Cerrar panel"
                onClick={() => setPanel(null)}
              >
                <X size={20} />
              </button>
            </header>
            <div className="concept-modal-body">
              <div className="concept-modal-icon">
                {panel === "chat" ? (
                  <MessageCircle size={25} />
                ) : panel === "sistema" ? (
                  <Cpu size={25} />
                ) : panel === "agenda" ? (
                  <CalendarDays size={25} />
                ) : panel === "archivos" ? (
                  <FolderOpen size={25} />
                ) : (
                  <Boxes size={25} />
                )}
              </div>
              <h2>{actionDetails[panel].title}</h2>
              <p>{actionDetails[panel].intro}</p>
              {panel === "chat" ? (
                <>
                  <div className="concept-messages">
                    <div className="concept-message-assistant">
                      Hola, Sebastián. ¿Qué te gustaría hacer hoy?
                    </div>
                    {sent.map((text, index) => (
                      <div className="concept-message-user" key={index}>
                        {text}
                      </div>
                    ))}
                    {sent.length > 0 && (
                      <div className="concept-message-assistant">
                        Entendido. Esta es una muestra visual; la respuesta real
                        se conectará en la aplicación final.
                      </div>
                    )}
                  </div>
                  <form className="concept-chat-form" onSubmit={submitMessage}>
                    <input
                      aria-label="Escribir mensaje"
                      placeholder="Escribe un mensaje de prueba…"
                      value={message}
                      onChange={(event) => setMessage(event.target.value)}
                    />
                    <button type="submit" aria-label="Enviar mensaje">
                      <Send size={17} />
                    </button>
                  </form>
                </>
              ) : (
                <div className="concept-modal-rows">
                  {actionDetails[panel].rows.map((row) => (
                    <div key={row}>
                      <span>
                        <Check size={15} />
                      </span>
                      {row}
                      <ChevronRight size={15} />
                    </div>
                  ))}
                </div>
              )}
            </div>
            <footer>
              <CircleHelp size={15} /> Prototipo interactivo · datos de ejemplo
            </footer>
          </aside>
        </div>
      )}
    </div>
  );
}
