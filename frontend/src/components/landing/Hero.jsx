// src/components/landing/Hero.jsx
import { ArrowRight, Zap, TrendingUp, Workflow, FileText, BarChart3, FileSpreadsheet, Shield, MessageSquare } from "lucide-react";

export default function Hero({ onGetStarted }) {
  return (
    <div className="relative overflow-hidden bg-background py-24 sm:py-32">
      {/* Background glow orbs */}
      <div className="absolute top-0 left-1/4 w-96 h-96 bg-primary/10 rounded-full blur-3xl pointer-events-none" />
      <div className="absolute top-10 right-1/4 w-96 h-96 bg-accent/10 rounded-full blur-3xl pointer-events-none" />

      {/* Floating decorative icons */}
      <div className="hidden md:block absolute top-24 left-[10%] animate-float opacity-70">
        <div className="w-14 h-14 rounded-2xl bg-primary/10 border border-primary/20 backdrop-blur flex items-center justify-center shadow-lg">
          <FileText className="w-6 h-6 text-primary" />
        </div>
      </div>
      <div className="hidden md:block absolute top-40 left-[20%] animate-float-delayed opacity-60">
        <div className="w-10 h-10 rounded-2xl bg-accent/10 border border-accent/20 backdrop-blur flex items-center justify-center shadow-md">
          <BarChart3 className="w-5 h-5 text-accent" />
        </div>
      </div>
      <div className="hidden md:block absolute bottom-32 left-[14%] animate-float-slow opacity-50">
        <div className="w-12 h-12 rounded-2xl bg-primary/10 border border-primary/20 backdrop-blur flex items-center justify-center shadow-md">
          <FileSpreadsheet className="w-5 h-5 text-primary" />
        </div>
      </div>
      <div className="hidden md:block absolute top-24 right-[10%] animate-float-delayed opacity-70">
        <div className="w-14 h-14 rounded-2xl bg-accent/10 border border-accent/20 backdrop-blur flex items-center justify-center shadow-lg">
          <Shield className="w-6 h-6 text-accent" />
        </div>
      </div>
      <div className="hidden md:block absolute top-44 right-[20%] animate-float opacity-60">
        <div className="w-10 h-10 rounded-2xl bg-primary/10 border border-primary/20 backdrop-blur flex items-center justify-center shadow-md">
          <MessageSquare className="w-5 h-5 text-primary" />
        </div>
      </div>
      <div className="hidden md:block absolute bottom-32 right-[14%] animate-float-slow opacity-50">
        <div className="w-12 h-12 rounded-2xl bg-accent/10 border border-accent/20 backdrop-blur flex items-center justify-center shadow-md">
          <TrendingUp className="w-5 h-5 text-accent" />
        </div>
      </div>

      {/* SVG connecting lines (desktop only) */}
      <svg
        className="hidden md:block absolute inset-0 w-full h-full pointer-events-none"
        xmlns="http://www.w3.org/2000/svg"
        preserveAspectRatio="none"
      >
        <line
          x1="21%" y1="30%" x2="42%" y2="46%"
          stroke="hsl(var(--primary) / 0.15)" strokeWidth="1"
          className="animate-dash-flow"
        />
        <line
          x1="79%" y1="30%" x2="58%" y2="46%"
          stroke="hsl(var(--accent) / 0.15)" strokeWidth="1"
          className="animate-dash-flow"
        />
      </svg>

      <div className="relative max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center">
          {/* Badge */}
          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-primary/10 text-primary border border-primary/20 text-sm font-medium mb-8">
            <Zap className="w-4 h-4" />
            Now in Closed Beta
          </div>

          {/* Main heading */}
          <h1 className="font-display text-5xl sm:text-6xl lg:text-7xl font-extrabold text-foreground mb-6 leading-tight">
            Turn Offering Memorandums
            <br className="hidden sm:block" />
            <span className="bg-gradient-to-r from-primary to-accent bg-clip-text text-transparent">
              {" "}into Excel in Minutes
            </span>
          </h1>

          {/* Subheading */}
          <p className="text-xl sm:text-2xl text-muted-foreground mb-10 max-w-3xl mx-auto leading-relaxed">
            Upload your OM or rent roll. LatticeBlu extracts cap rates, NOI, occupancy,
            and asking price. It fills your Excel template automatically.
            Review, fix anything off, and move on.
          </p>

          {/* CTAs */}
          <div className="flex flex-col sm:flex-row gap-4 justify-center items-center mb-16">
            <button
              onClick={onGetStarted}
              className="group px-10 py-4 bg-primary text-primary-foreground font-bold rounded-full shadow-xl shadow-primary/25 hover:bg-primary/90 hover:scale-105 active:scale-95 transition-all duration-200 flex items-center gap-2"
            >
              Get Started Free
              <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
            </button>
            <a
              href="#features"
              className="px-10 py-4 rounded-full font-semibold border-2 border-border hover:bg-muted transition-colors text-foreground"
            >
              See How It Works
            </a>
          </div>

          {/* Glass stat cards */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-5 max-w-3xl mx-auto mb-20">
            <div className="glass-card rounded-[2rem] p-6 text-center">
              <div className="text-4xl font-extrabold text-primary mb-1">4 min</div>
              <div className="text-sm text-muted-foreground">Average processing time</div>
            </div>
            <div className="glass-card rounded-[2rem] p-6 text-center">
              <div className="text-4xl font-extrabold text-accent mb-1">95%+</div>
              <div className="text-sm text-muted-foreground">Extraction accuracy</div>
            </div>
            <div className="glass-card rounded-[2rem] p-6 text-center">
              <div className="text-4xl font-extrabold text-primary mb-1">10x</div>
              <div className="text-sm text-muted-foreground">Faster than manual review</div>
            </div>
          </div>
        </div>

        {/* Feature highlights */}
        <div className="mt-16 grid grid-cols-1 md:grid-cols-3 gap-6 max-w-5xl mx-auto">
          <div className="glass-card rounded-3xl flex items-start gap-4 p-6">
            <div className="flex-shrink-0 w-12 h-12 bg-primary/10 rounded-xl flex items-center justify-center">
              <Zap className="w-6 h-6 text-primary" />
            </div>
            <div>
              <h3 className="font-semibold text-foreground mb-1">Lightning Fast</h3>
              <p className="text-sm text-muted-foreground">Process 100+ page documents in under 5 minutes</p>
            </div>
          </div>

          <div className="glass-card rounded-3xl flex items-start gap-4 p-6">
            <div className="flex-shrink-0 w-12 h-12 bg-accent/10 rounded-xl flex items-center justify-center">
              <TrendingUp className="w-6 h-6 text-accent" />
            </div>
            <div>
              <h3 className="font-semibold text-foreground mb-1">Excel Export</h3>
              <p className="text-sm text-muted-foreground">Structured data ready for your financial models</p>
            </div>
          </div>

          <div className="glass-card rounded-3xl flex items-start gap-4 p-6">
            <div className="flex-shrink-0 w-12 h-12 bg-primary/10 rounded-xl flex items-center justify-center">
              <Workflow className="w-6 h-6 text-primary" />
            </div>
            <div>
              <h3 className="font-semibold text-foreground mb-1">AI Workflows</h3>
              <p className="text-sm text-muted-foreground">Investment memos, underwriting & more</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
