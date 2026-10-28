import { percent } from "../format";

/** The YES/NO split: blue share is the market's chance of YES. */
export function ChanceBar({ chance, size = "sm" }: { chance: number | null; size?: "sm" | "lg" }) {
  const yes = chance == null ? 0.5 : Math.min(Math.max(chance, 0), 1);
  return (
    <div
      className={`chance-bar chance-bar--${size}${chance == null ? " is-empty" : ""}`}
      role="img"
      aria-label={chance == null ? "No price yet" : `${percent(chance)} chance of yes`}
    >
      <span className="chance-bar__yes" style={{ flexGrow: yes }} />
      <span className="chance-bar__no" style={{ flexGrow: 1 - yes }} />
    </div>
  );
}
