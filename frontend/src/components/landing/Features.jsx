// src/components/landing/Features.jsx
import {
  Zap,
  FileSpreadsheet,
  ShieldAlert,
  TrendingUp,
  BarChart3,
  Users,
  Target,
  Clock,
  CheckCircle2,
} from "lucide-react";

export default function Features() {
  const features = [
    {
      icon: Zap,
      title: "AI-Powered Extraction",
      description:
        "Our AI models read and understand CIMs like a senior analyst, extracting all key metrics automatically.",
      color: "blue",
    },
    {
      icon: FileSpreadsheet,
      title: "Excel-Ready Output",
      description:
        "Get perfectly formatted Excel files with 12+ sheets covering financials, risks, valuation, and more.",
      color: "green",
    },
    {
      icon: ShieldAlert,
      title: "Automated Red Flags",
      description:
        "Quantitative risk detection highlights leverage issues, declining margins, and customer concentration.",
      color: "red",
    },
    {
      icon: TrendingUp,
      title: "Financial Analysis",
      description:
        "Revenue, EBITDA, FCF, margins, and growth metrics extracted with full historical and projected years.",
      color: "purple",
    },
    {
      icon: BarChart3,
      title: "Valuation & Ratios",
      description:
        "Key multiples, debt ratios, liquidity metrics, and ROE/ROA calculated automatically.",
      color: "orange",
    },
    {
      icon: Users,
      title: "Deal Context",
      description:
        "Management bios, customer analysis, market sizing, and strategic rationale all in one place.",
      color: "pink",
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
              Deal Analysis
            </span>
          </h2>
          <p className="text-xl text-muted-foreground dark:text-gray-300 max-w-3xl mx-auto">
            Built specifically for PE analysts. Extract, analyze, and model
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
                Upload Your CIM
              </h4>
              <p className="text-muted-foreground dark:text-muted-foreground">
                Drop your PDF (up to 60 pages). Processing starts immediately.
              </p>
            </div>

            <div className="text-center">
              <div className="w-16 h-16 bg-gradient-to-br from-purple-500 to-purple-600 rounded-full flex items-center justify-center text-foreground text-2xl font-bold mx-auto mb-4 shadow-lg">
                2
              </div>
              <h4 className="text-xl font-semibold text-foreground mb-2">
                AI Extracts Data
              </h4>
              <p className="text-muted-foreground dark:text-muted-foreground">
                The tool reads every page, extracting financials, risks, and
                metrics.
              </p>
            </div>

            <div className="text-center">
              <div className="w-16 h-16 bg-gradient-to-br from-pink-500 to-pink-600 rounded-full flex items-center justify-center text-foreground text-2xl font-bold mx-auto mb-4 shadow-lg">
                3
              </div>
              <h4 className="text-xl font-semibold text-foreground mb-2">
                Download Excel
              </h4>
              <p className="text-muted-foreground dark:text-muted-foreground">
                Get structured data in Excel, ready to import into your model.
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
                  Your CIMs are encrypted and deleted after processing
                </div>
              </div>
            </div>
            <div className="flex items-center gap-4">
              <Clock className="w-8 h-8 text-blue-600 dark:text-blue-400 flex-shrink-0" />
              <div>
                <div className="font-semibold text-foreground">10x Faster</div>
                <div className="text-sm text-muted-foreground dark:text-muted-foreground">
                  What takes 3 hours manually takes 5 minutes with Sand Cloud
                </div>
              </div>
            </div>
            <div className="flex items-center gap-4">
              <Target className="w-8 h-8 text-purple-600 dark:text-purple-400 flex-shrink-0" />
              <div>
                <div className="font-semibold text-foreground">
                  PE-Optimized
                </div>
                <div className="text-sm text-muted-foreground dark:text-muted-foreground">
                  Built by PE analysts for PE analysts
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
