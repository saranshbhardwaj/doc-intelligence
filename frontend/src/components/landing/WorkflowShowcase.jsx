// src/components/landing/WorkflowShowcase.jsx
import {
  Building2,
  BarChart2,
  Table,
  MapPin,
  ArrowRight,
} from "lucide-react";

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

  return (
    <div className="py-24 bg-muted/20">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Section header */}
        <div className="mb-14">
          <span className="text-primary font-bold tracking-widest text-xs uppercase mb-3 block">
            What You Can Do
          </span>
          <h2 className="text-4xl sm:text-5xl font-bold text-foreground">
            Purpose-Built for
            <br />
            <span className="bg-gradient-to-r from-primary to-accent bg-clip-text text-transparent">
              Real Estate Deals
            </span>
          </h2>
        </div>

        {/* Workflow cards grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {reWorkflows.map((workflow, index) => {
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
