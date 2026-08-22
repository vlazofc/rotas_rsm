import { useTranslation } from "react-i18next";
import { LANGUAGES } from "../i18n";
import { useEffect, useRef, useState } from "react";
import { useBranding } from "../context/BrandingContext";

export default function LanguageSwitcher() {
  const { t, i18n } = useTranslation();
  const { branding } = useBranding();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const visibleLanguages = branding.enabled_locales
    ? LANGUAGES.filter((l) => branding.enabled_locales!.includes(l.code))
    : LANGUAGES;
  const languages = visibleLanguages.length ? visibleLanguages : LANGUAGES;
  const current = languages.some((l) => l.code === i18n.resolvedLanguage)
    ? i18n.resolvedLanguage
    : i18n.language;
  const currentLanguage = languages.find((l) => l.code === current);

  useEffect(() => {
    document.documentElement.lang = current || "pt-BR";
  }, [current]);

  useEffect(() => {
    if (!languages.some((l) => l.code === i18n.language) && languages[0]) {
      i18n.changeLanguage(languages[0].code);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [languages.map((l) => l.code).join(",")]);

  useEffect(() => {
    if (!open) return;
    function onClickOutside(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    }
    function onEscape(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onClickOutside);
    document.addEventListener("keydown", onEscape);
    return () => {
      document.removeEventListener("mousedown", onClickOutside);
      document.removeEventListener("keydown", onEscape);
    };
  }, [open]);

  function choose(code: string) {
    i18n.changeLanguage(code);
    setOpen(false);
  }

  return (
    <div className="language-switcher" ref={rootRef}>
      <button
        type="button"
        className="language-trigger"
        onClick={() => setOpen((prev) => !prev)}
        title={t("app.language_group")}
        aria-label={t("app.language_group")}
        aria-expanded={open}
        aria-haspopup="menu"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="10" />
          <line x1="2" y1="12" x2="22" y2="12" />
          <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
        </svg>
        {currentLanguage && <img className="language-flag-mini" src={currentLanguage.flagSrc} alt="" aria-hidden="true" />}
      </button>
      {open && (
        <div className="language-dropdown" role="menu" aria-label={t("app.language_group")}>
          {languages.map((l) => (
            <button
              key={l.code}
              role="menuitem"
              onClick={() => choose(l.code)}
              title={l.label}
              aria-pressed={current === l.code}
              className={`language-option${current === l.code ? " is-active" : ""}`}
            >
              <img className="language-flag" src={l.flagSrc} alt="" aria-hidden="true" />
              <span>{l.label}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
