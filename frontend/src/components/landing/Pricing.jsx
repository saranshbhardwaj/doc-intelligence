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

  const colorClasses = {
    gray: {
      bg: "bg-gray-50 dark:bg-gray-800",
      border: "border-gray-200 dark:border-gray-700",
      button: "bg-gray-600 hover:bg-gray-700 text-white",
      icon: "bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400",
    },
    blue: {
      bg: "bg-blue-50 dark:bg-blue-900/20",
      border: "border-blue-500 dark:border-blue-500",
      button:
        "bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-700 hover:to-purple-700 text-white shadow-lg",
      icon: "bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400",
    },
    purple: {
      bg: "bg-purple-50 dark:bg-purple-900/20",
      border: "border-purple-300 dark:border-purple-700",
      button: "bg-purple-600 hover:bg-purple-700 text-white",
      icon: "bg-purple-100 dark:bg-purple-900/30 text-purple-600 dark:text-purple-400",
    },
  };

  return (
    <div className="py-24 bg-gray-50 dark:bg-gray-800">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Section header */}
        <div className="text-center mb-16">
          <h2 className="text-4xl sm:text-5xl font-bold text-gray-900 dark:text-white mb-4">
            Simple,
            <span className="bg-gradient-to-r from-blue-600 to-purple-600 bg-clip-text text-transparent">
              {" "}
              Transparent Pricing
            </span>
          </h2>
          <p className="text-xl text-gray-600 dark:text-gray-300 max-w-2xl mx-auto">
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
                    <span className="px-4 py-1 bg-gradient-to-r from-blue-600 to-purple-600 text-white text-sm font-semibold rounded-full shadow-lg">
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
                <h3 className="text-2xl font-bold text-gray-900 dark:text-white mb-2">
                  {plan.name}
                </h3>

                {/* Price */}
                <div className="mb-4">
                  <span className="text-5xl font-extrabold text-gray-900 dark:text-white">
                    {plan.price}
                  </span>
                  {plan.period && (
                    <span className="text-gray-600 dark:text-gray-400 ml-2">
                      / {plan.period}
                    </span>
                  )}
                </div>

                {/* Description */}
                <p className="text-gray-600 dark:text-gray-400 mb-6">
                  {plan.description}
                </p>

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
                      <Check className="w-5 h-5 text-green-600 dark:text-green-400 flex-shrink-0 mt-0.5" />
                      <span className="text-sm text-gray-700 dark:text-gray-300">
                        {feature}
                      </span>
                    </div>
                  ))}
                </div>

                {/* Limitations (if any) */}
                {plan.limitations.length > 0 && (
                  <div className="pt-4 border-t border-gray-200 dark:border-gray-700 space-y-2">
                    {plan.limitations.map((limitation, idx) => (
                      <div key={idx} className="flex items-start gap-3">
                        <span className="text-sm text-gray-500 dark:text-gray-500">
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
          <p className="text-gray-600 dark:text-gray-400">
            All plans include 7-day money-back guarantee • Cancel anytime • No
            credit card required for Free tier
          </p>
        </div>
      </div>
    </div>
  );
}
