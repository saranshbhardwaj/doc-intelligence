// src/components/common/DarkModeToggle.jsx
import { Sun, Moon } from "lucide-react";

export default function DarkModeToggle({ isDark, toggle }) {
  return (
    <button
      onClick={toggle}
      className="fixed bottom-6 right-6 z-50 p-3 rounded-full shadow-lg 
                 bg-white dark:bg-gray-800 
                 text-gray-800 dark:text-gray-200
                 border border-gray-200 dark:border-gray-700
                 hover:shadow-xl transition-all duration-200
                 hover:scale-110"
      aria-label="Toggle dark mode"
    >
      {isDark ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
    </button>
  );
}
