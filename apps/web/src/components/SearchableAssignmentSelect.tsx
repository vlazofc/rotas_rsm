import { useState } from "react";

interface SearchableAssignmentSelectProps {
  value: string;
  query: string;
  placeholder: string;
  emptyLabel: string;
  options: { id: number; label: string }[];
  onQueryChange: (query: string, selectedId: string) => void;
  required?: boolean;
}

export default function SearchableAssignmentSelect({ value, query, placeholder, emptyLabel, options, onQueryChange, required = true }: SearchableAssignmentSelectProps) {
  const [open, setOpen] = useState(false);
  const normalizedQuery = query.trim().toLocaleLowerCase("pt-BR");
  const filtered = options.filter((option) => option.label.toLocaleLowerCase("pt-BR").includes(normalizedQuery)).slice(0, 30);

  return (
    <div className="assignment-search-select">
      <input
        required={required}
        className="input"
        type="search"
        role="combobox"
        aria-autocomplete="list"
        placeholder={placeholder}
        autoComplete="off"
        value={query}
        aria-expanded={open}
        onFocus={() => setOpen(true)}
        onBlur={() => window.setTimeout(() => setOpen(false), 150)}
        onChange={(event) => {
          const nextQuery = event.target.value;
          const exact = options.find((option) => option.label.localeCompare(nextQuery.trim(), "pt-BR", { sensitivity: "accent" }) === 0);
          onQueryChange(nextQuery, exact ? String(exact.id) : "");
          setOpen(true);
        }}
        onKeyDown={(event) => {
          if (event.key === "Escape") setOpen(false);
          if (event.key === "Enter" && open && normalizedQuery && filtered.length) {
            event.preventDefault();
            onQueryChange(filtered[0].label, String(filtered[0].id));
            setOpen(false);
          }
        }}
      />
      {value && <span className="assignment-selected-mark" aria-label="Selecionado">✓</span>}
      {open && (
        <div className="assignment-search-options" role="listbox">
          {filtered.length ? filtered.map((option) => (
            <button
              key={option.id}
              type="button"
              role="option"
              aria-selected={String(option.id) === value}
              className={String(option.id) === value ? "selected" : ""}
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => { onQueryChange(option.label, String(option.id)); setOpen(false); }}
            >
              {option.label}
              {String(option.id) === value && <span>✓</span>}
            </button>
          )) : <p>{emptyLabel}</p>}
        </div>
      )}
    </div>
  );
}
