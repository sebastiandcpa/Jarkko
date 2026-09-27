import type { AssistantStatus } from "../types";
import orbImage from "../assets/jarkko-orb.png";

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
        <g className="jarkko-orb__satellite jarkko-orb__satellite--blue">
          <circle r="22" className="jarkko-orb__satellite-glow" />
          <circle r="7" className="jarkko-orb__satellite-core" />
          <animateMotion
            dur="54s"
            repeatCount="indefinite"
            path="M 148 515 C 176 287 585 157 848 336 C 1020 454 852 701 569 757 C 294 811 113 686 148 515 Z"
          />
        </g>
        <g className="jarkko-orb__satellite jarkko-orb__satellite--green">
          <circle r="19" className="jarkko-orb__satellite-glow" />
          <circle r="6" className="jarkko-orb__satellite-core" />
          <animateMotion
            dur="67s"
            repeatCount="indefinite"
            path="M 211 676 C 113 536 255 265 535 220 C 804 179 949 323 876 532 C 800 756 377 818 211 676 Z"
          />
        </g>
      </svg>
      <span className="jarkko-orb__response" aria-hidden="true" />
    </div>
  );
}
