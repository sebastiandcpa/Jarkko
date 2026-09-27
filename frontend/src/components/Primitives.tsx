import type { ReactNode } from "react";
import { ArrowRight, Search } from "lucide-react";
export function SectionHeader({
  title,
  meta,
  onClick,
}: {
  title: string;
  meta?: string;
  onClick?: () => void;
}) {
  return (
    <div className="section-heading">
      <h2>{title}</h2>
      {meta &&
        (onClick ? (
          <button onClick={onClick}>
            {meta}
            <ArrowRight size={14} />
          </button>
        ) : (
          <span>{meta}</span>
        ))}
    </div>
  );
}
export function PageHeader({
  title,
  subtitle,
  action,
}: {
  title: string;
  subtitle: string;
  action?: ReactNode;
}) {
  return (
    <div className="page-header">
      <div>
        <h1>{title}</h1>
        <p>{subtitle}</p>
      </div>
      {action}
    </div>
  );
}
export function SearchField({
  value,
  onChange,
  placeholder,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
}) {
  return (
    <label className="search-field">
      <Search size={16} />
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
      />
    </label>
  );
}
