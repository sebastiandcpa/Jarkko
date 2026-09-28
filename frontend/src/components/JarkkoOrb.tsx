import type { AssistantStatus } from "../types";
import { BlackHoleVisual } from "../concepts/BlackHoleVisual";

export function JarkkoOrb({ status }: { status: AssistantStatus }) {
  return (
    <div
      className={`jarkko-orb jarkko-orb--${status}`}
      role="img"
      aria-label={`Agujero negro de Jarkko: ${status}`}
    >
      <BlackHoleVisual listening={status === "listening"} />
    </div>
  );
}
