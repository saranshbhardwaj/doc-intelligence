// src/components/Section.jsx
export default function Section({
  title,
  icon: Icon,
  children,
  highlight = false,
}) {
  return (
    <div
      className={`bg-card 
                 rounded-xl shadow-md overflow-hidden border-l-4 
                 transition-colors duration-200 ${
                   highlight
                     ? "border-blue-600"
                     : "border-border dark:border-gray-700"
                 }`}
    >
      <div
        className={`px-6 py-4 
                   ${
                     highlight
                       ? "bg-gradient-to-r from-blue-50 to-white dark:from-blue-900/30 dark:to-gray-800"
                       : "bg-background dark:bg-gray-700/50"
                   } 
                   border-b border-border dark:border-gray-700`}
      >
        <div className="flex items-center gap-3">
          {Icon && (
            <Icon
              className={`w-6 h-6 ${
                highlight
                  ? "text-blue-600 dark:text-blue-400"
                  : "text-muted-foreground dark:text-muted-foreground"
              }`}
            />
          )}
          <h3 className="text-xl font-bold text-muted-foreground ">{title}</h3>
        </div>
      </div>
      <div className="px-6 py-5">{children}</div>
    </div>
  );
}
