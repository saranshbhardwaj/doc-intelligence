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
  ArrowRight,
} from "lucide-react";

const peWorkflows = [
  {
    icon: FileText,
    title: "Investment Memo",
    description:
      "Generate comprehensive investment memos from CIMs and deal documents in minutes.",
    color: "bg-primary/10 text-primary",
  },
  {
    icon: AlertTriangle,
    title: "Red Flag Analysis",
    description:
      "Automated risk detection, anomaly scoring, and concern highlighting across your documents.",
    color: "bg-destructive/10 text-destructive",
  },
  {
    icon: Search,
    title: "Deal Screening",
    description:
      "Quickly qualify deals with AI-extracted KPIs, margins, and growth metrics.",
    color: "bg-accent/10 text-accent",
  },
  {
    icon: ClipboardCheck,
    title: "Due Diligence",
    description:
      "Build DD checklists and summaries automatically from uploaded deal documents.",
    color: "bg-primary/10 text-primary",
  },
];

const reWorkflows = [
  {
    icon: Building2,
    title: "Property Underwriting",
    description:
      "Build underwriting models from rent rolls, operating statements, and offering memos.",
    color: "bg-primary/10 text-primary",
  },
  {
    icon: BarChart2,
    title: "Property Analysis",
    description:
      "Extract NOI, cap rates, occupancy, and key metrics from any real estate document.",
    color: "bg-accent/10 text-accent",
  },
  {
    icon: Table,
    title: "Template Fill",
    description:
      "Auto-populate your Excel templates with data extracted from deal documents.",
    color: "bg-primary/10 text-primary",
  },
  {
    icon: MapPin,
    title: "Market Analysis",
    description:
      "Pull market data, comparable deals, and location details from offering memoranda.",
    color: "bg-accent/10 text-accent",
  },
];

export default function WorkflowShowcase() {
  const [activeTab, setActiveTab] = useState("pe");

  const workflows = activeTab === "pe" ? peWorkflows : reWorkflows;

  return (
    <div className="py-24 bg-muted/20">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Section header */}
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-8 mb-14">
          <div>
            <span className="text-primary font-bold tracking-widest text-xs uppercase mb-3 block">
              Solutions
            </span>
            <h2 className="text-4xl sm:text-5xl font-bold text-foreground">
              Powerful Workflows for
              <br />
              <span className="bg-gradient-to-r from-primary to-accent bg-clip-text text-transparent">
                Every Deal Type
              </span>
            </h2>
          </div>

          {/* Tab switcher */}
          <div className="glass-card p-1.5 rounded-xl flex self-start md:self-auto">
            <button
              onClick={() => setActiveTab("pe")}
              className={`px-6 py-2.5 rounded-lg text-sm font-semibold transition-all duration-200 ${
                activeTab === "pe"
                  ? "bg-primary text-primary-foreground shadow-md"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              Private Equity
            </button>
            <button
              onClick={() => setActiveTab("re")}
              className={`px-6 py-2.5 rounded-lg text-sm font-semibold transition-all duration-200 ${
                activeTab === "re"
                  ? "bg-primary text-primary-foreground shadow-md"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              Real Estate
            </button>
          </div>
        </div>

        {/* Workflow cards grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {workflows.map((workflow, index) => {
            const Icon = workflow.icon;
            return (
              <div
                key={index}
                className="glass-card rounded-3xl p-7 group hover:-translate-y-1 hover:border-primary/40 transition-all duration-300"
              >
                <div
                  className={`w-12 h-12 rounded-xl ${workflow.color} flex items-center justify-center mb-5 group-hover:bg-primary group-hover:text-primary-foreground transition-colors duration-200`}
                >
                  <Icon className="w-6 h-6" />
                </div>
                <h3 className="text-lg font-bold text-foreground mb-2">
                  {workflow.title}
                </h3>
                <p className="text-muted-foreground text-sm leading-relaxed mb-5">
                  {workflow.description}
                </p>
                <span className="inline-flex items-center gap-1 text-xs font-bold text-primary group-hover:gap-2 transition-all">
                  Explore workflow
                  <ArrowRight className="w-3.5 h-3.5" />
                </span>
              </div>
            );
          })}
        </div>

        {/* Works with your tools */}
        <div className="mt-16 text-center">
          <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground/60 mb-6">
            Works with your existing tools
          </p>
          <div className="flex flex-wrap justify-center items-center gap-8 md:gap-14 opacity-50">
            <span className="text-sm font-black text-foreground tracking-tight">Microsoft Excel</span>
            <span className="text-sm font-black text-foreground tracking-tight">Google Sheets</span>
            <span className="text-sm font-black text-foreground tracking-tight">PDF / DOCX</span>
            <span className="text-sm font-black text-foreground tracking-tight">XLSX Templates</span>
          </div>
        </div>
      </div>
    </div>
  );
}
