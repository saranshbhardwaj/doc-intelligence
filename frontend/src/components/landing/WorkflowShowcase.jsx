// src/components/landing/WorkflowShowcase.jsx
import { useState } from "react";
import {
  FileText,
  AlertTriangle,
  Search,
  ClipboardCheck,
  Building2,
  BarChart2,
  Table,
  MapPin,
} from "lucide-react";

const peWorkflows = [
  {
    icon: FileText,
    title: "Investment Memo",
    description:
      "Generate comprehensive investment memos from CIMs and deal documents in minutes.",
    color: "blue",
  },
  {
    icon: AlertTriangle,
    title: "Red Flag Analysis",
    description:
      "Automated risk detection, anomaly scoring, and concern highlighting across your documents.",
    color: "red",
  },
  {
    icon: Search,
    title: "Deal Screening",
    description:
      "Quickly qualify deals with AI-extracted KPIs, margins, and growth metrics.",
    color: "purple",
  },
  {
    icon: ClipboardCheck,
    title: "Due Diligence",
    description:
      "Build DD checklists and summaries automatically from uploaded deal documents.",
    color: "green",
  },
];

const reWorkflows = [
  {
    icon: Building2,
    title: "Property Underwriting",
    description:
      "Build underwriting models from rent rolls, operating statements, and offering memos.",
    color: "blue",
  },
  {
    icon: BarChart2,
    title: "Property Analysis",
    description:
      "Extract NOI, cap rates, occupancy, and key metrics from any real estate document.",
    color: "orange",
  },
  {
    icon: Table,
    title: "Template Fill",
    description:
      "Auto-populate your Excel templates with data extracted from deal documents.",
    color: "green",
  },
  {
    icon: MapPin,
    title: "Market Analysis",
    description:
      "Pull market data, comparable deals, and location details from offering memoranda.",
    color: "purple",
  },
];

const colorClasses = {
  blue: "bg-primary/15 text-primary",
  green: "bg-green-100 dark:bg-green-900/30 text-green-600 dark:text-green-400",
  red: "bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400",
  purple: "bg-accent/20 text-accent",
  orange:
    "bg-orange-100 dark:bg-orange-900/30 text-orange-600 dark:text-orange-400",
};

export default function WorkflowShowcase() {
  const [activeTab, setActiveTab] = useState("pe");

  const workflows = activeTab === "pe" ? peWorkflows : reWorkflows;

  return (
    <div className="py-24 bg-muted/30 dark:bg-gray-900/50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Section header */}
        <div className="text-center mb-12">
          <h2 className="text-4xl sm:text-5xl font-bold text-foreground mb-4">
            Powerful Workflows for
            <span className="bg-gradient-to-r from-primary to-accent bg-clip-text text-transparent">
              {" "}
              Every Deal Type
            </span>
          </h2>
          <p className="text-xl text-muted-foreground dark:text-gray-300 max-w-3xl mx-auto">
            Whether you're screening PE deals or underwriting real estate, AI
            handles the heavy lifting.
          </p>
        </div>

        {/* Tab switcher */}
        <div className="flex justify-center mb-10">
          <div className="inline-flex rounded-xl border border-border dark:border-gray-700 bg-background dark:bg-card p-1 gap-1">
            <button
              onClick={() => setActiveTab("pe")}
              className={`px-6 py-2.5 rounded-lg font-semibold text-sm transition-all duration-200 ${
                activeTab === "pe"
                  ? "bg-gradient-to-r from-primary to-accent text-primary-foreground shadow-md"
                  : "text-muted-foreground dark:text-gray-400 hover:text-foreground dark:hover:text-foreground"
              }`}
            >
              Private Equity
            </button>
            <button
              onClick={() => setActiveTab("re")}
              className={`px-6 py-2.5 rounded-lg font-semibold text-sm transition-all duration-200 ${
                activeTab === "re"
                  ? "bg-gradient-to-r from-primary to-accent text-primary-foreground shadow-md"
                  : "text-muted-foreground dark:text-gray-400 hover:text-foreground dark:hover:text-foreground"
              }`}
            >
              Real Estate
            </button>
          </div>
        </div>

        {/* Workflow cards grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {workflows.map((workflow, index) => {
            const Icon = workflow.icon;
            return (
              <div
                key={index}
                className="group flex items-start gap-5 p-6 rounded-2xl bg-background dark:bg-card border border-border dark:border-gray-700 hover:border-primary/70 dark:hover:border-primary/70 hover:shadow-lg transition-all duration-300 transform hover:scale-105"
              >
                <div
                  className={`flex-shrink-0 w-12 h-12 rounded-xl ${
                    colorClasses[workflow.color]
                  } flex items-center justify-center group-hover:scale-110 transition-transform duration-300`}
                >
                  <Icon className="w-6 h-6" />
                </div>
                <div>
                  <h3 className="text-lg font-bold text-foreground mb-1">
                    {workflow.title}
                  </h3>
                  <p className="text-muted-foreground dark:text-muted-foreground leading-relaxed">
                    {workflow.description}
                  </p>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
