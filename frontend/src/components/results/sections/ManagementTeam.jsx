// src/components/results/sections/ManagementTeam.jsx
import { Users } from "lucide-react";
import Section from "../Section";
import { safeText } from "../../../utils/formatters";

export default function ManagementTeam({ data }) {
  if (!Array.isArray(data.management_team) || data.management_team.length === 0)
    return null;

  return (
    <Section title="Management Team" icon={Users}>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {data.management_team.map((member, idx) => {
          const initials = member.name
            ? safeText(member.name)
                .split(" ")
                .map((word) => word.charAt(0))
                .join("")
                .substring(0, 2)
                .toUpperCase()
            : "?";

          return (
            <div
              key={idx}
              className="bg-card p-5 rounded-lg border border-border hover:shadow-lg transition-shadow"
            >
              <div className="flex items-start gap-3">
                {/* Avatar / Initials */}
                <div className="w-12 h-12 bg-primary rounded-full flex items-center justify-center text-primary-foreground font-bold text-xl flex-shrink-0">
                  {initials}
                </div>

                {/* Member Info */}
                <div className="flex-1 min-w-0 space-y-1">
                  <h4 className="text-lg font-bold text-foreground">
                    {safeText(member.name)}
                  </h4>
                  {member.title && (
                    <p className="text-sm font-semibold text-primary">
                      {safeText(member.title)}
                    </p>
                  )}
                  {member.background && (
                    <p className="text-sm text-muted-foreground">
                      {safeText(member.background)}
                    </p>
                  )}
                  {member.linkedin && (
                    <a
                      href={member.linkedin}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-xs text-primary hover:text-primary-foreground"
                    >
                      LinkedIn Profile
                      <svg
                        className="w-3 h-3"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"
                        />
                      </svg>
                    </a>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </Section>
  );
}
