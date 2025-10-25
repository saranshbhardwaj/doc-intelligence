// src/components/results/sections/ManagementTeam.jsx
import { Users } from "lucide-react";
import Section from "../Section";
import { safeText } from "../../../utils/formatters";

export default function ManagementTeam({ data }) {
  if (
    !Array.isArray(data.management_team) ||
    data.management_team.length === 0
  ) {
    return null;
  }

  return (
    <Section title="Management Team" icon={Users}>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {data.management_team.map((member, index) => {
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
              key={index}
              className="bg-gradient-to-br from-gray-50 to-white p-5 rounded-xl border border-gray-200 hover:shadow-lg transition-shadow"
            >
              <div className="flex items-start gap-3">
                <div className="w-12 h-12 bg-blue-600 rounded-full flex items-center justify-center text-white font-bold text-xl flex-shrink-0">
                  {initials}
                </div>
                <div className="flex-1 min-w-0">
                  <h4 className="font-bold text-gray-900 text-lg">
                    {safeText(member.name)}
                  </h4>
                  {member.title && (
                    <p className="text-sm text-blue-600 font-semibold">
                      {safeText(member.title)}
                    </p>
                  )}
                  {member.background && (
                    <p className="text-sm text-gray-600 mt-2">
                      {safeText(member.background)}
                    </p>
                  )}
                  {member.linkedin && (
                    <a
                      href={member.linkedin}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-blue-500 hover:text-blue-700 mt-2 inline-flex items-center gap-1"
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
