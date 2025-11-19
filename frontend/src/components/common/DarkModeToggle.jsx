// src/components/common/DarkModeToggle.jsx
import { Sun, Moon } from "lucide-react";

export default function DarkModeToggle({ isDark, toggle, variant = "fixed" }) {
  const baseClasses = "p-3 rounded-full transition-all duration-200";

  const variantClasses = {
    fixed: `
      fixed bottom-6 right-6 z-50 shadow-lg
      bg-card text-foreground border border-border
      hover:shadow-xl hover:scale-110
    `,

    inline: `
      bg-card text-foreground border border-border
      hover:bg-muted
    `,
  };

  return (
    <button
      onClick={toggle}
      className={`${baseClasses} ${variantClasses[variant]}`}
      aria-label="Toggle dark mode"
    >
      {isDark ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
    </button>
  );
}
