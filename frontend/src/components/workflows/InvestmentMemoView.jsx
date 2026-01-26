/**
 * Investment Memo View - Production-grade Investment Memo workflow results
 *
 * Features:
 * - Beautiful hero header with gradient
 * - Key metrics dashboard at top
 * - Enhanced card components
 * - Professional spacing and typography
 * - Dark mode support
 * - Smooth animations
 */

import { FileText, Users, Leaf, AlertTriangle } from "lucide-react";
import { Card } from "../ui/card";
import SectionCard from "./SectionCard";
import FinancialsCard from "./FinancialsCard";
import RisksCard from "./RisksCard";
import OpportunitiesCard from "./OpportunitiesCard";
import NextStepsCard from "./NextStepsCard";
import WorkflowMetricsDashboard from "./WorkflowMetricsDashboard";

export default function InvestmentMemoView({ artifact, run }) {

  if (!artifact || !artifact.artifact) {
    console.warn("No artifact or artifact.artifact found", { artifact });
    return (
      <div className="text-center py-12 text-muted-foreground">
        No artifact data available
      </div>
    );
  }

  const data = artifact.artifact.parsed || artifact.artifact;

  const currency = data.currency || run.currency || "USD";

  return (
    <div className="space-y-6">
      {/* Hero Header */}
      <Card className="bg-gradient-to-r from-primary via-primary/90 to-primary/80 rounded-xl shadow-2xl overflow-hidden">
        <div className="p-8 text-primary-foreground">
          <div className="flex items-start justify-between gap-6">
            <div className="flex-1">
              <div className="flex items-center gap-3 mb-3">
                <div className="p-3 bg-white/10 backdrop-blur-sm rounded-lg">
                  <FileText className="w-8 h-8" />
                </div>
                <div>
                  <h1 className="text-3xl md:text-4xl font-bold">
                    {data.company_overview?.company_name || "Investment Memo"}
                  </h1>
                  {data.company_overview?.industry && (
                    <p className="text-primary-foreground/90 text-lg mt-1">
                      {data.company_overview.industry}
                    </p>
                  )}
                </div>
              </div>

              {data.company_overview?.description && (
                <p className="text-primary-foreground/80 text-sm md:text-base leading-relaxed max-w-3xl">
                  {data.company_overview.description}
                </p>
              )}
            </div>

            {/* Meta Info */}
            <div className="hidden md:flex flex-col items-end gap-2 text-right">
              {run.created_at && (
                <div className="bg-white/10 backdrop-blur-sm rounded-lg px-4 py-2">
                  <div className="text-xs text-primary-foreground/70 uppercase tracking-wide">
                    Generated
                  </div>
                  <div className="text-sm font-semibold">
                    {new Date(run.created_at).toLocaleDateString()}
                  </div>
                </div>
              )}
              {run.latency_ms && (
                <div className="text-xs text-primary-foreground/70">
                  Processing: {(run.latency_ms / 1000).toFixed(1)}s
                </div>
              )}
            </div>
          </div>
        </div>
      </Card>

      {/* Key Metrics Dashboard */}
      <WorkflowMetricsDashboard data={data} run={run} />

      {/* Main Content Sections */}
      {data.sections && data.sections.length > 0 && (
        <div className="space-y-6">
          {data.sections.map((section, idx) => (
            <SectionCard
              key={section.key || idx}
              section={section}
              index={idx}
              currency={currency}
              richCitations={artifact.artifact.rich_citations || []}
            />
          ))}
        </div>
      )}

      {/* Risks - Enhanced with Grouping */}
      {data.risks && data.risks.length > 0 && <RisksCard risks={data.risks} />}

      {/* Opportunities - Enhanced with Categories */}
      {data.opportunities && data.opportunities.length > 0 && (
        <OpportunitiesCard opportunities={data.opportunities} />
      )}

      {/* Management & Culture */}
      {data.management && (
        <Card className="rounded-xl shadow-lg overflow-hidden border-l-4 border-primary">
          <div className="px-6 py-4 bg-gradient-to-r from-primary/5 to-primary/10 dark:from-primary/10 dark:to-primary/20 border-b border-border">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-primary/10 rounded-lg">
                <Users className="w-6 h-6 text-primary" />
              </div>
              <h2 className="text-xl font-bold text-foreground">
                Management & Culture
              </h2>
            </div>
          </div>
          <div className="p-6">
            <p className="text-muted-foreground leading-relaxed mb-6">
              {data.management.summary}
            </p>

            {/* Key People Cards */}
            {data.management.key_people &&
              data.management.key_people.length > 0 && (
                <div className="mb-6">
                  <h3 className="font-semibold text-foreground mb-4 text-sm uppercase tracking-wide flex items-center gap-2">
                    <Users className="w-4 h-4" />
                    Key People
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {data.management.key_people.map((person, idx) => {
                      const initials = person.name
                        ? person.name
                            .split(" ")
                            .map((word) => word.charAt(0))
                            .join("")
                            .substring(0, 2)
                            .toUpperCase()
                        : "?";

                      return (
                        <div
                          key={idx}
                          className="bg-gradient-to-br from-background to-muted/20 p-5 rounded-lg border border-border hover:shadow-lg hover:border-primary/30 transition-all"
                        >
                          <div className="flex items-start gap-3">
                            {/* Avatar with Initials */}
                            <div className="w-12 h-12 bg-primary rounded-full flex items-center justify-center text-primary-foreground font-bold text-xl flex-shrink-0">
                              {initials}
                            </div>

                            {/* Person Info */}
                            <div className="flex-1 min-w-0 space-y-1">
                              <h4 className="text-base font-bold text-foreground">
                                {person.name}
                              </h4>
                              {person.title && (
                                <p className="text-sm font-semibold text-primary">
                                  {person.title}
                                </p>
                              )}
                              {person.tenure_years && (
                                <p className="text-xs text-muted-foreground">
                                  {person.tenure_years}{" "}
                                  {person.tenure_years === 1 ? "year" : "years"}{" "}
                                  tenure
                                </p>
                              )}
                              {person.background && (
                                <p className="text-xs text-muted-foreground mt-2 leading-relaxed">
                                  {person.background}
                                </p>
                              )}
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

            <div className="grid md:grid-cols-2 gap-6">
              {data.management.strengths &&
                data.management.strengths.length > 0 && (
                  <div>
                    <h3 className="font-semibold text-foreground mb-3 text-sm uppercase tracking-wide text-success">
                      Strengths
                    </h3>
                    <ul className="space-y-2">
                      {data.management.strengths.map((strength, idx) => (
                        <li
                          key={idx}
                          className="flex items-start gap-2 text-sm text-muted-foreground"
                        >
                          <span className="text-success font-bold mt-0.5">
                            ✓
                          </span>
                          <span className="flex-1">{strength}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

              {data.management.gaps && data.management.gaps.length > 0 && (
                <div>
                  <h3 className="font-semibold text-foreground mb-3 text-sm uppercase tracking-wide text-warning">
                    Gaps
                  </h3>
                  <ul className="space-y-2">
                    {data.management.gaps.map((gap, idx) => (
                      <li
                        key={idx}
                        className="flex items-start gap-2 text-sm text-muted-foreground"
                      >
                        <span className="text-warning font-bold mt-0.5">!</span>
                        <span className="flex-1">{gap}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </div>
        </Card>
      )}

      {/* ESG Snapshot */}
      {data.esg && (
        <Card className="rounded-xl shadow-lg overflow-hidden border-l-4 border-success">
          <div className="px-6 py-4 bg-gradient-to-r from-success/5 to-success/10 dark:from-success/10 dark:to-success/20 border-b border-border">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-success/10 rounded-lg">
                <Leaf className="w-6 h-6 text-success" />
              </div>
              <h2 className="text-xl font-bold text-foreground">
                ESG Snapshot
              </h2>
            </div>
          </div>
          <div className="p-6">
            {data.esg.factors && data.esg.factors.length > 0 && (
              <div className="grid grid-cols-3 gap-4 mb-6">
                {data.esg.factors.map((factor, idx) => (
                  <div
                    key={idx}
                    className="p-4 bg-gradient-to-br from-background to-muted/30 rounded-lg border border-border"
                  >
                    <div className="text-xs font-bold text-muted-foreground uppercase tracking-wide mb-2">
                      {factor.dimension}
                    </div>
                    <div
                      className={`font-bold text-lg ${
                        factor.status === "Positive"
                          ? "text-success"
                          : factor.status === "Negative"
                          ? "text-destructive"
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
              <p className="text-muted-foreground leading-relaxed">
                {data.esg.overall}
              </p>
            )}
          </div>
        </Card>
      )}

      {/* Next Steps - Enhanced Timeline */}
      {data.next_steps && data.next_steps.length > 0 && (
        <NextStepsCard nextSteps={data.next_steps} />
      )}

      {/* Inconsistencies */}
      {data.inconsistencies && data.inconsistencies.length > 0 && (
        <Card className="rounded-xl shadow-lg overflow-hidden border-l-4 border-warning">
          <div className="px-6 py-4 bg-gradient-to-r from-warning/5 to-warning/10 dark:from-warning/10 dark:to-warning/20 border-b border-border">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-warning/10 rounded-lg">
                <AlertTriangle className="w-6 h-6 text-warning" />
              </div>
              <h2 className="text-xl font-bold text-foreground">
                Inconsistencies Found
              </h2>
            </div>
          </div>
          <div className="p-6">
            <ul className="list-disc list-inside space-y-2 text-muted-foreground">
              {data.inconsistencies.map((item, idx) => (
                <li key={idx} className="leading-relaxed">
                  {item}
                </li>
              ))}
            </ul>
          </div>
        </Card>
      )}

      {/* Footer */}
      <Card className="rounded-xl p-6 text-center text-sm text-muted-foreground bg-gradient-to-br from-background to-muted/20">
        <p className="font-medium">
          This is a confidential document prepared for investment evaluation
          purposes.
        </p>
        <p className="mt-2 text-xs">
          Generated using AI-powered workflow analysis from document
          intelligence.
        </p>
      </Card>
    </div>
  );
}
