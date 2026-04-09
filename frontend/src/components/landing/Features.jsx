// src/components/landing/Features.jsx
import {
  Zap,
  FileSpreadsheet,
  ShieldAlert,
  MessageSquare,
  Building2,
  BarChart3,
  Target,
  Clock,
  CheckCircle2,
  UploadCloud,
  BrainCircuit,
  Download,
} from "lucide-react";

export default function Features() {
  return (
    <div className="py-24 bg-background">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Section header */}
        <div className="text-center mb-16">
          <h2 className="text-4xl sm:text-5xl font-bold text-foreground mb-4">
            Everything You Need for
            <span className="bg-gradient-to-r from-primary to-accent bg-clip-text text-transparent">
              {" "}Deal Intelligence
            </span>
          </h2>
          <p className="text-xl text-muted-foreground max-w-3xl mx-auto">
            Built for PE and real estate analysts. Extract, analyze, and model
            faster than ever before.
          </p>
        </div>

        {/* Bento grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-6">
          {/* Smart Extraction — wide card */}
          <div className="md:col-span-2 glass-card rounded-3xl p-8 flex flex-col md:flex-row gap-8 group hover:-translate-y-0.5 transition-transform duration-300">
            <div className="flex-1 space-y-4">
              <div className="w-12 h-12 rounded-2xl bg-primary/10 flex items-center justify-center">
                <Zap className="w-6 h-6 text-primary" />
              </div>
              <h3 className="text-2xl font-bold text-foreground">Smart Extraction</h3>
              <p className="text-muted-foreground leading-relaxed">
                Upload PDFs or Excel. AI extracts structured data instantly, financials, metrics, and key terms with 95%+ accuracy.
              </p>
              <ul className="space-y-1.5 text-sm text-muted-foreground">
                <li className="flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 text-primary flex-shrink-0" />
                  Automated rent roll normalization
                </li>
                <li className="flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 text-primary flex-shrink-0" />
                  Multi-page PDF parsing
                </li>
                <li className="flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 text-primary flex-shrink-0" />
                  Source-cited extraction
                </li>
              </ul>
            </div>
            <div className="flex-1 flex items-center justify-center bg-muted/40 rounded-2xl p-6 min-h-[140px]">
              <div className="w-full space-y-3">
                <div className="h-2 bg-muted rounded-full w-3/4 animate-pulse" />
                <div className="h-2 bg-primary/20 rounded-full w-full" />
                <div className="h-2 bg-muted rounded-full w-1/2 animate-pulse" />
                <div className="grid grid-cols-3 gap-2 pt-2">
                  <div className="h-10 bg-background rounded-lg border border-border shadow-sm" />
                  <div className="h-10 bg-background rounded-lg border border-border shadow-sm" />
                  <div className="h-10 bg-background rounded-lg border border-border shadow-sm" />
                </div>
              </div>
            </div>
          </div>

          {/* AI Chat */}
          <div className="glass-card rounded-3xl p-8 flex flex-col justify-between group hover:-translate-y-0.5 transition-transform duration-300">
            <div className="space-y-4">
              <div className="w-12 h-12 rounded-2xl bg-accent/10 flex items-center justify-center">
                <MessageSquare className="w-6 h-6 text-accent" />
              </div>
              <h3 className="text-xl font-bold text-foreground">Ask Anything</h3>
              <p className="text-muted-foreground">
                "What is the total NOI across Q3 properties?" Get instant, cited answers from your deal docs.
              </p>
            </div>
            <div className="mt-8 pt-4 border-t border-border">
              <div className="bg-muted/50 rounded-xl px-4 py-3 flex items-center gap-3">
                <div className="w-2 h-2 rounded-full bg-primary animate-pulse" />
                <span className="text-xs font-medium text-muted-foreground">AI is ready to answer...</span>
              </div>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-6">
          {/* PE Workflows */}
          <div className="glass-card rounded-3xl p-8 group hover:-translate-y-0.5 transition-transform duration-300">
            <div className="space-y-4">
              <div className="w-12 h-12 rounded-2xl bg-primary/10 flex items-center justify-center">
                <BarChart3 className="w-6 h-6 text-primary" />
              </div>
              <h3 className="text-xl font-bold text-foreground">PE Workflows</h3>
              <p className="text-muted-foreground">
                Investment memos, red flag analysis, deal screening — automated from your uploaded documents.
              </p>
            </div>
          </div>

          {/* Red Flag Detection — dark card spanning 2 cols */}
          <div className="md:col-span-2 bg-foreground rounded-3xl p-8 relative overflow-hidden group hover:-translate-y-0.5 transition-transform duration-300">
            <div className="absolute inset-0 opacity-20 pointer-events-none">
              <div className="absolute top-0 right-0 w-64 h-64 bg-primary rounded-full -mr-32 -mt-32 blur-[80px]" />
            </div>
            <div className="relative z-10 flex flex-col md:flex-row items-start md:items-center gap-8">
              <div className="flex-1 space-y-4">
                <div className="inline-flex items-center gap-2 bg-destructive/20 text-destructive px-3 py-1 rounded-full text-xs font-bold tracking-widest uppercase">
                  <ShieldAlert className="w-3.5 h-3.5" />
                  Risk Detection
                </div>
                <h3 className="text-2xl font-bold text-background">Red Flag Detection</h3>
                <p className="text-background/70 leading-relaxed">
                  Automatic risk scoring highlights leverage issues, margin declines, and anomalies hidden in deal documents.
                </p>
              </div>
              <div className="flex-shrink-0 flex justify-center">
                <div className="relative">
                  <div className="w-20 h-20 rounded-3xl bg-primary shadow-[0_0_40px_hsl(var(--primary)/0.5)] flex items-center justify-center">
                    <ShieldAlert className="w-10 h-10 text-primary-foreground" />
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {/* RE Workflows */}
          <div className="glass-card rounded-3xl p-8 group hover:-translate-y-0.5 transition-transform duration-300">
            <div className="space-y-4">
              <div className="w-12 h-12 rounded-2xl bg-accent/10 flex items-center justify-center">
                <Building2 className="w-6 h-6 text-accent" />
              </div>
              <h3 className="text-xl font-bold text-foreground">RE Workflows</h3>
              <p className="text-muted-foreground">
                Underwriting models, property analysis, template fill — generated directly from your deal docs.
              </p>
              <div className="grid grid-cols-4 gap-1 pt-2">
                <div className="h-7 bg-muted rounded" />
                <div className="h-10 bg-muted rounded" />
                <div className="h-8 bg-primary/15 rounded" />
                <div className="h-12 bg-muted rounded" />
              </div>
            </div>
          </div>

          {/* Excel Export */}
          <div className="glass-card rounded-3xl p-8 group hover:-translate-y-0.5 transition-transform duration-300">
            <div className="space-y-4">
              <div className="w-12 h-12 rounded-2xl bg-primary/10 flex items-center justify-center">
                <FileSpreadsheet className="w-6 h-6 text-primary" />
              </div>
              <h3 className="text-xl font-bold text-foreground">1-Click Excel Export</h3>
              <p className="text-muted-foreground">
                Structured data ready to drop into your financial models. Clean, formatted, and model-ready.
              </p>
              <div className="bg-muted/50 rounded-xl p-3 flex items-center justify-between mt-4">
                <span className="text-xs font-mono text-muted-foreground">deal_summary.xlsx</span>
                <Download className="w-4 h-4 text-muted-foreground" />
              </div>
            </div>
          </div>

          {/* Empty slot — use for a CTA or leave clean */}
          <div className="glass-card rounded-3xl p-8 flex flex-col justify-center items-center text-center gap-4 border-dashed group hover:-translate-y-0.5 transition-transform duration-300">
            <div className="w-12 h-12 rounded-2xl bg-muted flex items-center justify-center">
              <Target className="w-6 h-6 text-muted-foreground" />
            </div>
            <h3 className="text-xl font-bold text-foreground">PE & RE Focused</h3>
            <p className="text-muted-foreground text-sm">Built for private equity and real estate professionals — not generic tools.</p>
          </div>
        </div>

        {/* How It Works */}
        <div className="mt-28">
          <h3 className="text-3xl font-bold text-center text-foreground mb-4">How It Works</h3>
          <p className="text-center text-muted-foreground mb-16 max-w-xl mx-auto">
            From raw documents to investment-ready intelligence in minutes.
          </p>
          <div className="relative max-w-4xl mx-auto">
            {/* Connecting line */}
            <div className="hidden md:block absolute top-10 left-[18%] right-[18%] h-px bg-border" />

            <div className="grid grid-cols-1 md:grid-cols-3 gap-10">
              {[
                {
                  num: "1",
                  Icon: UploadCloud,
                  title: "Upload Your Documents",
                  desc: "Drop PDFs or Excel files. Processing starts immediately.",
                  color: "bg-primary/10 text-primary",
                  circleColor: "bg-primary text-primary-foreground",
                },
                {
                  num: "2",
                  Icon: BrainCircuit,
                  title: "AI Extracts & Analyzes",
                  desc: "Reads every page, extracting financials, risks, and metrics across PE and RE deals.",
                  color: "bg-accent/10 text-accent",
                  circleColor: "bg-accent text-accent-foreground",
                },
                {
                  num: "3",
                  Icon: Download,
                  title: "Get Structured Output",
                  desc: "Download Excel, run AI workflows, or ask questions — your data, your way.",
                  color: "bg-primary/10 text-primary",
                  circleColor: "bg-primary text-primary-foreground",
                },
              ].map((step) => (
                <div key={step.num} className="flex flex-col items-center text-center">
                  <div className={`w-20 h-20 rounded-3xl ${step.color} flex items-center justify-center mb-5 shadow-lg border border-current/10 group hover:scale-110 transition-transform`}>
                    <step.Icon className="w-9 h-9" />
                  </div>
                  <div className={`w-8 h-8 ${step.circleColor} rounded-full flex items-center justify-center text-sm font-bold mb-4 shadow-sm -mt-3 relative z-10`}>
                    {step.num}
                  </div>
                  <h4 className="text-xl font-semibold text-foreground mb-2">{step.title}</h4>
                  <p className="text-muted-foreground">{step.desc}</p>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Trust indicators */}
        <div className="mt-20 glass-card rounded-3xl p-8">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            <div className="flex items-center gap-4">
              <CheckCircle2 className="w-8 h-8 text-primary flex-shrink-0" />
              <div>
                <div className="font-semibold text-foreground">Bank-Level Security</div>
                <div className="text-sm text-muted-foreground">Your documents are encrypted and deleted after processing</div>
              </div>
            </div>
            <div className="flex items-center gap-4">
              <Clock className="w-8 h-8 text-accent flex-shrink-0" />
              <div>
                <div className="font-semibold text-foreground">10x Faster</div>
                <div className="text-sm text-muted-foreground">What takes 3 hours manually takes 5 minutes with Basilfy</div>
              </div>
            </div>
            <div className="flex items-center gap-4">
              <Target className="w-8 h-8 text-primary flex-shrink-0" />
              <div>
                <div className="font-semibold text-foreground">PE & RE Focused</div>
                <div className="text-sm text-muted-foreground">Built for private equity and real estate professionals</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
