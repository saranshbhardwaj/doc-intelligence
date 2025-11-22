// src/components/Section.jsx
export default function Section({
  title,
  icon: Icon,
  children,
  highlight = false,
}) {
  return (
    <div
      className={`bg-card rounded-xl shadow-md overflow-hidden border-l-4
        transition-colors duration-200 ${
          highlight ? "border-primary" : "border-border"
        }`}
    >
      <div
        className={`px-6 py-4 border-b border-border ${
          highlight ? "bg-card" : "bg-background"
        }`}
      >
        <div className="flex items-center gap-3">
          {Icon && (
            <Icon
              className={`w-6 h-6 ${
                highlight ? "text-primary" : "text-muted-foreground"
              }`}
            />
          )}
          <h3 className="text-xl font-bold text-foreground">{title}</h3>
        </div>
      </div>

      <div className="px-6 py-5">{children}</div>
    </div>
  );
}
