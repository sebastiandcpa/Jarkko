import type { AssistantStatus } from "../types";
import orbImage from "../assets/jarkko-orb-core.png";

const satellites = [
  {
    color: "green",
    path: "M 840 220 C 965 286 1052 544 942 700 C 788 876 366 876 193 735 C 60 628 45 506 100 430 C 208 249 633 83 840 220 Z",
  },
  {
    color: "blue",
    path: "M 942 700 C 788 876 366 876 193 735 C 60 628 45 506 100 430 C 208 249 633 83 840 220 C 965 286 1052 544 942 700 Z",
  },
  {
    color: "green",
    path: "M 193 735 C 60 628 45 506 100 430 C 208 249 633 83 840 220 C 965 286 1052 544 942 700 C 788 876 366 876 193 735 Z",
  },
  {
    color: "green",
    path: "M 100 430 C 208 249 633 83 840 220 C 965 286 1052 544 942 700 C 788 876 366 876 193 735 C 60 628 45 506 100 430 Z",
  },
] as const;

export function JarkkoOrb({ status }: { status: AssistantStatus }) {
  return (
    <div
      className={`jarkko-orb jarkko-orb--${status}`}
      role="img"
      aria-label={`Esfera de Jarkko: ${status}`}
    >
      <span className="jarkko-orb__aura" aria-hidden="true" />
      <img src={orbImage} alt="" draggable={false} />
      <svg
        className="jarkko-orb__satellites"
        viewBox="0 0 1000 1000"
        aria-hidden="true"
        focusable="false"
      >
        <defs>
          <radialGradient id="satellite-green">
            <stop offset="0" stopColor="#ffffff" />
            <stop offset="0.27" stopColor="#cafff0" />
            <stop offset="0.64" stopColor="#4af5be" />
            <stop offset="1" stopColor="#087d70" />
          </radialGradient>
          <radialGradient id="satellite-blue">
            <stop offset="0" stopColor="#ffffff" />
            <stop offset="0.28" stopColor="#dafaff" />
            <stop offset="0.66" stopColor="#35bfff" />
            <stop offset="1" stopColor="#0754b7" />
          </radialGradient>
        </defs>
        {satellites.map(({ color, path }, index) => (
          <g
            key={index}
            className={`jarkko-orb__satellite jarkko-orb__satellite--${color}`}
          >
            <circle r="44" className="jarkko-orb__satellite-glow" />
            <circle r="23" className="jarkko-orb__satellite-shell" />
            <circle
              r="5"
              cx="-7"
              cy="-7"
              className="jarkko-orb__satellite-shine"
            />
            <animateMotion dur="64s" repeatCount="indefinite" path={path} />
          </g>
        ))}
      </svg>
      <span className="jarkko-orb__voice-shape" aria-hidden="true" />
      <span className="jarkko-orb__response" aria-hidden="true" />
    </div>
  );
}
