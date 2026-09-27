import type { AssistantStatus } from "../types";
export function Orb({
  status,
  small = false,
}: {
  status: AssistantStatus;
  small?: boolean;
}) {
  return (
    <div
      className={"orb orb-" + status + (small ? " orb-small" : "")}
      role="img"
      aria-label={"Orbe: " + status}
    >
      <div className="orb-halo" />
      <div className="orb-orbit orbit-a" />
      <div className="orb-orbit orbit-b" />
      <div className="orb-sphere">
        <span className="orb-line orb-line-a" />
        <span className="orb-line orb-line-b" />
        <span className="orb-line orb-line-c" />
        <span className="orb-core" />
        {Array.from({ length: 15 }, (_, index) => (
          <i key={index} className={"particle particle-" + index} />
        ))}
      </div>
      <span className="orb-satellite satellite-a" />
      <span className="orb-satellite satellite-b" />
    </div>
  );
}
