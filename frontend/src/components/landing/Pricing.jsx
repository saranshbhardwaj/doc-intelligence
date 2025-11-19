// src/components/landing/Pricing.jsx
import { Check, Zap, Crown, Building2 } from "lucide-react";

export default function Pricing({ onSelectPlan }) {
  const plans = [
    {
      name: "Free",
      icon: Zap,
      price: "$0",
      period: "forever",
      description: "Perfect for trying out the platform",
      features: [
        "2 CIM extractions per month",
        "All extraction features",
        "Excel export",
        "Red flag detection",
        "Email support",
      ],
      limitations: ["Limited to 50 pages per CIM", "No extraction history"],
      cta: "Start Free",
      popular: false,
      color: "gray",
    },
    {
      name: "Pro",
      icon: Crown,
      price: "$99",
      period: "per month",
      description: "For active PE analysts",
      features: [
        "500 CIM extractions per month",
        "All extraction features",
        "Excel export",
        "Red flag detection",
        "Extraction history (30 days)",
        "Priority support",
        "Comparison mode (2-3 CIMs)",
        "Custom red flag rules",
      ],
      limitations: [],
      cta: "Start 7-Day Trial",
      popular: true,
      color: "blue",
    },
    {
      name: "Enterprise",
      icon: Building2,
      price: "Custom",
      period: "contact us",
      description: "For PE firms and teams",
      features: [
        "Everything in Pro",
        "Unlimited team members",
        "90-day extraction history",
        "Dedicated account manager",
        "Custom integrations",
        "SLA guarantee",
        "Training & onboarding",
        "White-label options",
      ],
      limitations: [],
      cta: "Contact Sales",
      popular: false,
      color: "purple",
    },
  ];

  // Semantic tokens only — no hard-coded tailwind palette or dark: classes
  const colorClasses = {
    gray: {
      bg: "bg-card",
      border: "border-border",
      button: "bg-popover text-foreground hover:bg-muted",
      icon: "bg-popover text-muted-foreground",
    },
    blue: {
      // Use primary / accent tokens; gradient uses color names from tailwind config
      bg: "bg-card",
      border: "border-border",
      button:
        "bg-gradient-to-r from-primary to-accent text-primary-foreground shadow-lg hover:opacity-95",
      icon: "bg-popover text-primary-foreground",
    },
    purple: {
      bg: "bg-card",
      border: "border-border",
      button: "bg-accent text-accent-foreground hover:bg-accent/90",
      icon: "bg-popover text-accent-foreground",
    },
  };

  return (
    <div className="py-24 bg-background text-foreground">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Section header */}
        <div className="text-center mb-16">
          <h2 className="text-4xl sm:text-5xl font-bold text-foreground mb-4">
            Simple,
            <span className="bg-gradient-to-r from-primary to-accent bg-clip-text text-transparent">
              {" "}
              Transparent Pricing
            </span>
          </h2>
          <p className="text-xl text-muted-foreground max-w-2xl mx-auto">
            Start free, upgrade when you need more. No hidden fees.
          </p>
        </div>

        {/* Pricing cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8 max-w-7xl mx-auto">
          {plans.map((plan, index) => {
            const Icon = plan.icon;
            const colors = colorClasses[plan.color];

            return (
              <div
                key={index}
                className={`relative rounded-2xl p-8 ${colors.bg} border-2 ${
                  colors.border
                } ${
                  plan.popular ? "shadow-2xl scale-105" : "shadow-lg"
                } transition-all duration-300 hover:scale-105`}
              >
                {/* Popular badge */}
                {plan.popular && (
                  <div className="absolute -top-4 left-1/2 transform -translate-x-1/2">
                    <span className="px-4 py-1 bg-gradient-to-r from-primary to-accent text-primary-foreground text-sm font-semibold rounded-full shadow-lg">
                      Most Popular
                    </span>
                  </div>
                )}

                {/* Icon */}
                <div
                  className={`w-14 h-14 rounded-xl ${colors.icon} flex items-center justify-center mb-6`}
                >
                  <Icon className="w-7 h-7" />
                </div>

                {/* Plan name */}
                <h3 className="text-2xl font-bold text-foreground mb-2">
                  {plan.name}
                </h3>

                {/* Price */}
                <div className="mb-4">
                  <span className="text-5xl font-extrabold text-foreground">
                    {plan.price}
                  </span>
                  {plan.period && (
                    <span className="text-muted-foreground ml-2">
                      / {plan.period}
                    </span>
                  )}
                </div>

                {/* Description */}
                <p className="text-muted-foreground mb-6">{plan.description}</p>

                {/* CTA Button */}
                <button
                  onClick={() => onSelectPlan(plan.name.toLowerCase())}
                  className={`w-full py-3 px-6 rounded-xl font-semibold ${colors.button} transition-all duration-200 mb-6`}
                >
                  {plan.cta}
                </button>

                {/* Features */}
                <div className="space-y-3 mb-4">
                  {plan.features.map((feature, idx) => (
                    <div key={idx} className="flex items-start gap-3">
                      <Check className="w-5 h-5 text-accent-foreground flex-shrink-0 mt-0.5" />
                      <span className="text-sm text-muted-foreground">
                        {feature}
                      </span>
                    </div>
                  ))}
                </div>

                {/* Limitations (if any) */}
                {plan.limitations.length > 0 && (
                  <div className="pt-4 border-t border-border space-y-2">
                    {plan.limitations.map((limitation, idx) => (
                      <div key={idx} className="flex items-start gap-3">
                        <span className="text-sm text-muted-foreground">
                          • {limitation}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* FAQ or guarantee */}
        <div className="mt-16 text-center">
          <p className="text-muted-foreground">
            All plans include 7-day money-back guarantee • Cancel anytime • No
            credit card required for Free tier
          </p>
        </div>
      </div>
    </div>
  );
}
