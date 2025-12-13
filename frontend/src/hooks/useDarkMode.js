// src/hooks/useDarkMode.js
import { useEffect, useState } from "react";

export function useDarkMode() {
  // Check localStorage or system preference
  const [isDark, setIsDark] = useState(() => {
    const saved = localStorage.getItem("darkMode");
    if (saved !== null) {
      return saved === "true";
    }
    // Default to light theme when no preference saved
    return false;
  });

  useEffect(() => {
    // Save to localStorage
    localStorage.setItem("darkMode", isDark);

    // Apply to document
    if (isDark) {
      document.documentElement.classList.add("dark");
    } else {
      document.documentElement.classList.remove("dark");
    }
  }, [isDark]);

  const toggle = () => setIsDark(!isDark);

  return { isDark, toggle };
}
