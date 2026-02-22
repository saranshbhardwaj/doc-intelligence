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
} from "lucide-react";

export default function Features() {
  const features = [
    {
      icon: Zap,
      title: "Smart Extraction",
      description:
        "Upload PDFs or Excel. AI extracts structured data instantly — financials, metrics, and key terms.",
      color: "blue",
    },
    {
      icon: MessageSquare,
      title: "AI Chat",
      description:
        "Ask questions across your entire document library. Get instant, cited answers from your deal docs.",
      color: "green",
    },
    {
      icon: BarChart3,
      title: "PE Workflows",
      description:
        "Investment memos, red flag analysis, deal screening — automated from your uploaded documents.",
      color: "purple",
    },
    {
      icon: Building2,
      title: "RE Workflows",
      description:
        "Underwriting models, property analysis, template fill — generated directly from your deal docs.",
      color: "orange",
    },
    {
      icon: FileSpreadsheet,
      title: "Excel Export",
      description:
        "Structured data ready to drop into your financial models. Clean, formatted, and model-ready.",
      color: "green",
    },
    {
      icon: ShieldAlert,
      title: "Red Flag Detection",
      description:
        "Automatic risk scoring and anomaly detection highlights leverage issues, margin declines, and more.",
      color: "red",
    },
  ];

  const colorClasses = {
    blue: "bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400",
    green:
      "bg-green-100 dark:bg-green-900/30 text-green-600 dark:text-green-400",
    red: "bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400",
    purple:
      "bg-purple-100 dark:bg-purple-900/30 text-purple-600 dark:text-purple-400",
    orange:
      "bg-orange-100 dark:bg-orange-900/30 text-orange-600 dark:text-orange-400",
    pink: "bg-pink-100 dark:bg-pink-900/30 text-pink-600 dark:text-pink-400",
  };

  return (
    <div className="py-24 bg-background ">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Section header */}
        <div className="text-center mb-16">
          <h2 className="text-4xl sm:text-5xl font-bold text-foreground mb-4">
            Everything You Need for
            <span className="bg-gradient-to-r from-blue-600 to-purple-600 bg-clip-text text-transparent">
              {" "}
              Deal Intelligence
            </span>
          </h2>
          <p className="text-xl text-muted-foreground dark:text-gray-300 max-w-3xl mx-auto">
            Built for PE and real estate analysts. Extract, analyze, and model
            faster than ever before.
          </p>
        </div>

        {/* Features grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8 mb-16">
          {features.map((feature, index) => {
            const Icon = feature.icon;
            return (
              <div
                key={index}
                className="group p-8 rounded-2xl bg-background dark:bg-card border border-border dark:border-gray-700 hover:border-blue-500 dark:hover:border-blue-500 hover:shadow-xl transition-all duration-300 transform hover:scale-105"
              >
                <div
                  className={`w-14 h-14 rounded-xl ${
                    colorClasses[feature.color]
                  } flex items-center justify-center mb-5 group-hover:scale-110 transition-transform duration-300`}
                >
                  <Icon className="w-7 h-7" />
                </div>
                <h3 className="text-xl font-bold text-foreground mb-3">
                  {feature.title}
                </h3>
                <p className="text-muted-foreground dark:text-muted-foreground leading-relaxed">
                  {feature.description}
                </p>
              </div>
            );
          })}
        </div>

        {/* How it works */}
        <div className="mt-24">
          <h3 className="text-3xl font-bold text-center text-foreground mb-12">
            How It Works
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            <div className="text-center">
              <div className="w-16 h-16 bg-gradient-to-br from-blue-500 to-blue-600 rounded-full flex items-center justify-center text-foreground text-2xl font-bold mx-auto mb-4 shadow-lg">
                1
              </div>
              <h4 className="text-xl font-semibold text-foreground mb-2">
                Upload Your Documents
              </h4>
              <p className="text-muted-foreground dark:text-muted-foreground">
                Drop your PDFs or Excel files. Processing starts immediately.
              </p>
            </div>

            <div className="text-center">
              <div className="w-16 h-16 bg-gradient-to-br from-purple-500 to-purple-600 rounded-full flex items-center justify-center text-foreground text-2xl font-bold mx-auto mb-4 shadow-lg">
                2
              </div>
              <h4 className="text-xl font-semibold text-foreground mb-2">
                AI Extracts & Analyzes
              </h4>
              <p className="text-muted-foreground dark:text-muted-foreground">
                The tool reads every page, extracting financials, risks, and
                metrics across PE and RE deals.
              </p>
            </div>

            <div className="text-center">
              <div className="w-16 h-16 bg-gradient-to-br from-pink-500 to-pink-600 rounded-full flex items-center justify-center text-foreground text-2xl font-bold mx-auto mb-4 shadow-lg">
                3
              </div>
              <h4 className="text-xl font-semibold text-foreground mb-2">
                Get Structured Output
              </h4>
              <p className="text-muted-foreground dark:text-muted-foreground">
                Download Excel, run AI workflows, or ask questions — your data, your way.
              </p>
            </div>
          </div>
        </div>

        {/* Trust indicators */}
        <div className="mt-20 p-8 rounded-2xl bg-gradient-to-r from-blue-50 to-purple-50 dark:from-gray-800 dark:to-gray-800 border border-blue-200 dark:border-gray-700">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            <div className="flex items-center gap-4">
              <CheckCircle2 className="w-8 h-8 text-green-600 dark:text-green-400 flex-shrink-0" />
              <div>
                <div className="font-semibold text-foreground">
                  Bank-Level Security
                </div>
                <div className="text-sm text-muted-foreground dark:text-muted-foreground">
                  Your documents are encrypted and deleted after processing
                </div>
              </div>
            </div>
            <div className="flex items-center gap-4">
              <Clock className="w-8 h-8 text-blue-600 dark:text-blue-400 flex-shrink-0" />
              <div>
                <div className="font-semibold text-foreground">10x Faster</div>
                <div className="text-sm text-muted-foreground dark:text-muted-foreground">
                  What takes 3 hours manually takes 5 minutes with DealWorks
                </div>
              </div>
            </div>
            <div className="flex items-center gap-4">
              <Target className="w-8 h-8 text-purple-600 dark:text-purple-400 flex-shrink-0" />
              <div>
                <div className="font-semibold text-foreground">
                  PE & RE Focused
                </div>
                <div className="text-sm text-muted-foreground dark:text-muted-foreground">
                  Built for private equity and real estate professionals
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
