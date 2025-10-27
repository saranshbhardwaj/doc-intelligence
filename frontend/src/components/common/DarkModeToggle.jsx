// src/components/common/DarkModeToggle.jsx
import { Sun, Moon } from "lucide-react";

export default function DarkModeToggle({ isDark, toggle, variant = "fixed" }) {
  const baseClasses = "p-3 rounded-full transition-all duration-200";

  const variantClasses = {
    fixed: `fixed bottom-6 right-6 z-50 shadow-lg bg-white dark:bg-gray-800
            text-gray-800 dark:text-gray-200 border border-gray-200 dark:border-gray-700
            hover:shadow-xl hover:scale-110`,
    inline: `bg-gray-100 dark:bg-gray-800 text-gray-800 dark:text-gray-200
             hover:bg-gray-200 dark:hover:bg-gray-700`
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
