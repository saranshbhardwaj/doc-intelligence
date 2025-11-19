// src/components/results/sections/CompanyHeader.jsx
import { Building2 } from "lucide-react";
import { safeText } from "../../../utils/formatters";

export default function CompanyHeader({ data, metadata }) {
  return (
    <div
      className="bg-gradient-to-r from-blue-600 to-blue-800 
                dark:from-blue-700 dark:to-blue-900 
                rounded-xl shadow-xl p-8 text-foreground"
    >
      <div className="flex items-center gap-4 mb-4">
        <Building2 className="w-12 h-12" />
        <div>
          <h1 className="text-4xl font-bold">
            {safeText(data.company_info?.company_name || "Company Report")}
          </h1>
          <p className="text-blue-100 text-lg mt-1">
            Confidential Information Memorandum
          </p>
        </div>
      </div>
      {data.company_info?.industry && (
        <div className="flex gap-2 mt-4">
          <span className="bg-primary px-4 py-2 rounded-full text-sm font-semibold">
            {safeText(data.company_info.industry)}
          </span>
          {data.company_info.secondary_industry && (
            <span className="bg-primary px-4 py-2 rounded-full text-sm font-semibold">
              {safeText(data.company_info.secondary_industry)}
            </span>
          )}
        </div>
      )}
      <div className="mt-4 text-sm text-blue-100">
        {metadata?.pages && `${metadata.pages} pages processed`}
      </div>
    </div>
  );
}
