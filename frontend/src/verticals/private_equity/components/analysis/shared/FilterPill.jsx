export default function FilterPill({ active, onClick, children }) {
  return (
    <button
      onClick={onClick}
      className={`text-xs px-2.5 py-1 rounded-full font-semibold transition-colors ${
        active
          ? "bg-primary text-primary-foreground"
          : "bg-background border border-border/60 text-muted-foreground hover:text-foreground hover:border-border"
      }`}
    >
      {children}
    </button>
  );
}
