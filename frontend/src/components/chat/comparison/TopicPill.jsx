/**
 * TopicPill Component
 *
 * Filterable topic badge for comparison view
 * - Click to toggle topic filter
 * - Visual indicator when active
 */

import { X } from "lucide-react";
import { Badge } from "../../ui/badge";

export default function TopicPill({ topic, isActive, onClick }) {
  return (
    <Badge
      variant={isActive ? "default" : "outline"}
      className={`cursor-pointer transition-all gap-1 whitespace-nowrap flex-shrink-0 max-w-[200px] truncate ${
        isActive
          ? "bg-primary text-primary-foreground"
          : "hover:bg-muted"
      }`}
      onClick={onClick}
      title={topic}
    >
      {topic}
      {isActive && <X className="w-3 h-3 ml-1 flex-shrink-0" />}
    </Badge>
  );
}
