// src/components/results/sections/CompanyHeader.jsx
import { Building2 } from "lucide-react";
import { safeText } from "../../../utils/formatters";

export default function CompanyHeader({ data, metadata }) {
  return (
    <div className="bg-primary text-primary-foreground rounded-xl shadow-xl p-8">
      {/* Header */}
      <div className="flex items-center gap-4 mb-4">
        <Building2 className="w-12 h-12 text-primary-foreground" />
        <div>
          <h1 className="text-4xl font-bold">
            {safeText(data.company_info?.company_name || "Company Report")}
          </h1>
          <p className="text-sm text-foreground mt-1">
            Confidential Information Memorandum
          </p>
        </div>
      </div>

      {/* Industry Tags */}
      {data.company_info?.industry && (
        <div className="flex gap-2 mt-4 flex-wrap">
          <span className="bg-secondary text-secondary-foreground px-4 py-2 rounded-full text-sm font-semibold">
            {safeText(data.company_info.industry)}
          </span>
          {data.company_info.secondary_industry && (
            <span className="bg-secondary text-secondary-foreground px-4 py-2 rounded-full text-sm font-semibold">
              {safeText(data.company_info.secondary_industry)}
            </span>
          )}
        </div>
      )}

      {/* Metadata */}
      {metadata?.pages && (
        <div className="mt-4 text-sm text-foreground">
          {`${metadata.pages} pages processed`}
        </div>
      )}
    </div>
  );
}
