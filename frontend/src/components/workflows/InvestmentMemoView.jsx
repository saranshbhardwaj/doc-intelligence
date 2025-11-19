/**
 * Investment Memo View - Beautiful rendering of Investment Memo workflow results
 *
 * Renders sections with Markdown, formatted financials, risks, opportunities, etc.
 */

import {
  FileText,
  TrendingUp,
  AlertTriangle,
  Lightbulb,
  Users,
  Leaf,
} from "lucide-react";
import SectionCard from "./SectionCard";
import FinancialsCard from "./FinancialsCard";
import RisksCard from "./RisksCard";
import OpportunitiesCard from "./OpportunitiesCard";
import NextStepsCard from "./NextStepsCard";

export default function InvestmentMemoView({ artifact, run }) {
  // Debug logging
  console.log("InvestmentMemoView rendered", { artifact, run });

  if (!artifact || !artifact.artifact) {
    console.warn("No artifact or artifact.artifact found", { artifact });
    return (
      <div className="text-center py-12 text-muted-foreground">
        No artifact data available
      </div>
    );
  }

  const data = artifact.artifact.parsed || artifact.artifact;
  console.log("Parsed data:", data);

  const currency = data.currency || run.currency || "USD";

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-gradient-to-r from-blue-600 to-indigo-700 rounded-xl p-8 text-foreground shadow-lg">
        <div className="flex items-center gap-3 mb-3">
          <FileText className="w-8 h-8" />
          <h1 className="text-3xl font-bold">
            {data.company_overview?.company_name || "Investment Memo"}
          </h1>
        </div>
        {data.company_overview?.industry && (
          <p className="text-blue-100 text-lg">
            {data.company_overview.industry}
          </p>
        )}
        <div className="mt-4 flex items-center gap-6 text-sm text-blue-100">
          <span>
            Generated: {new Date(run.created_at).toLocaleDateString()}
          </span>
          {run.latency_ms && (
            <span>Processing time: {(run.latency_ms / 1000).toFixed(1)}s</span>
          )}
          {run.cost_usd && <span>Cost: ${run.cost_usd.toFixed(3)}</span>}
        </div>
      </div>

      {/* Sections */}
      {data.sections && data.sections.length > 0 && (
        <div className="space-y-6">
          {data.sections.map((section, idx) => (
            <SectionCard
              key={section.key || idx}
              section={section}
              index={idx}
            />
          ))}
        </div>
      )}

      {/* Financials */}
      {data.financials && (
        <FinancialsCard financials={data.financials} currency={currency} />
      )}

      {/* Risks */}
      {data.risks && data.risks.length > 0 && <RisksCard risks={data.risks} />}

      {/* Opportunities */}
      {data.opportunities && data.opportunities.length > 0 && (
        <OpportunitiesCard opportunities={data.opportunities} />
      )}

      {/* Management */}
      {data.management && (
        <div className="bg-card rounded-xl shadow-md p-6 border-l-4 border-purple-500">
          <div className="flex items-center gap-3 mb-4">
            <Users className="w-6 h-6 text-purple-600" />
            <h2 className="text-xl font-bold text-foreground">
              Management & Culture
            </h2>
          </div>
          <p className="text-muted-foreground dark:text-gray-300 mb-4">
            {data.management.summary}
          </p>

          {data.management.strengths &&
            data.management.strengths.length > 0 && (
              <div className="mb-4">
                <h3 className="font-semibold text-foreground mb-2">
                  Strengths
                </h3>
                <ul className="list-disc list-inside space-y-1 text-muted-foreground dark:text-gray-300">
                  {data.management.strengths.map((strength, idx) => (
                    <li key={idx}>{strength}</li>
                  ))}
                </ul>
              </div>
            )}

          {data.management.gaps && data.management.gaps.length > 0 && (
            <div>
              <h3 className="font-semibold text-foreground mb-2">Gaps</h3>
              <ul className="list-disc list-inside space-y-1 text-muted-foreground dark:text-gray-300">
                {data.management.gaps.map((gap, idx) => (
                  <li key={idx}>{gap}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* ESG */}
      {data.esg && (
        <div className="bg-card rounded-xl shadow-md p-6 border-l-4 border-green-500">
          <div className="flex items-center gap-3 mb-4">
            <Leaf className="w-6 h-6 text-green-600" />
            <h2 className="text-xl font-bold text-foreground">ESG Snapshot</h2>
          </div>

          {data.esg.factors && data.esg.factors.length > 0 && (
            <div className="grid grid-cols-3 gap-4 mb-4">
              {data.esg.factors.map((factor, idx) => (
                <div
                  key={idx}
                  className="p-3 bg-background dark:bg-gray-700 rounded-lg"
                >
                  <div className="text-xs font-semibold text-muted-foreground dark:text-muted-foreground uppercase mb-1">
                    {factor.dimension}
                  </div>
                  <div
                    className={`font-bold ${
                      factor.status === "Positive"
                        ? "text-green-600"
                        : factor.status === "Negative"
                        ? "text-red-600"
                        : "text-muted-foreground"
                    }`}
                  >
                    {factor.status}
                  </div>
                </div>
              ))}
            </div>
          )}

          {data.esg.overall && (
            <p className="text-muted-foreground dark:text-gray-300">
              {data.esg.overall}
            </p>
          )}
        </div>
      )}

      {/* Next Steps */}
      {data.next_steps && data.next_steps.length > 0 && (
        <NextStepsCard nextSteps={data.next_steps} />
      )}

      {/* Inconsistencies */}
      {data.inconsistencies && data.inconsistencies.length > 0 && (
        <div className="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-xl p-6">
          <div className="flex items-center gap-3 mb-4">
            <AlertTriangle className="w-6 h-6 text-yellow-600" />
            <h2 className="text-xl font-bold text-foreground">
              Inconsistencies Found
            </h2>
          </div>
          <ul className="list-disc list-inside space-y-2 text-muted-foreground dark:text-gray-300">
            {data.inconsistencies.map((item, idx) => (
              <li key={idx}>{item}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Footer */}
      <div className="bg-background dark:bg-card rounded-xl p-6 text-center text-sm text-muted-foreground dark:text-muted-foreground">
        <p>
          This is a confidential document prepared for investment evaluation
          purposes.
        </p>
        <p className="mt-2">
          Generated using AI-powered workflow analysis from document
          intelligence.
        </p>
      </div>
    </div>
  );
}
