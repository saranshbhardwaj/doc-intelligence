// src/components/landing/FAQ.jsx
import { useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";

export default function FAQ() {
  const [openIndex, setOpenIndex] = useState(null);

  const faqs = [
    {
      question: "What file formats do you support?",
      answer:
        "We currently support digital PDF files (text-based PDFs). Scanned PDFs or image-based documents are not supported yet. This work is in progress.",
    },
    {
      question: "How accurate is the extraction?",
      answer:
        "We achieve 95%+ accuracy on standard CIM documents. The system specializes in reading and understanding financial documents like a senior analyst. However, we always recommend reviewing the extracted data, especially for critical deal decisions.",
    },
    {
      question: "Is my data secure? What happens to my CIMs?",
      answer:
        "Your data security is our top priority. All uploads are encrypted in transit and at rest. Your CIM documents are processed and then deleted from our servers after 30 days. We never share your documents with third parties, and all processing is confidential.",
    },
    {
      question: "What's the difference between Free and Pro plans?",
      answer:
        "Free plan includes 2 CIM extractions per month. Pro plan ($99/month) offers 500 extractions, 30-day extraction history, priority support, comparison mode to analyze multiple CIMs side-by-side, and custom red flag rules.",
    },
    {
      question: "Can I compare multiple CIMs?",
      answer:
        "Yes! Pro and Enterprise plans include comparison mode, which allows you to upload 2-3 CIMs and get a side-by-side Excel comparison highlighting the best metrics across deals. This feature is coming soon to all plans.",
    },
    {
      question: "How long does processing take?",
      answer:
        "Most CIMs (40-80 pages) are processed in 1-6 minutes. You'll see real-time progress updates while your document is being analyzed.",
    },
    {
      question: "What data do you extract from CIMs?",
      answer:
        "We extract 12+ categories including: company overview, financials (revenue, EBITDA, margins, FCF), balance sheet, valuation multiples, capital structure, customer metrics, market analysis, management team, risks, and strategic rationale. All data is delivered in structured Excel format.",
    },
    {
      question: "Do you support languages other than English?",
      answer:
        "Currently, we only support English-language CIM documents. Support for other languages is on our roadmap.",
    },
    {
      question: "What if the extraction has errors?",
      answer:
        "If you find inaccuracies, please use the feedback form on the results page. We review all feedback and continuously improve our AI models. For critical errors, contact us at saranshbhardwaj@gmail.com and we'll re-process your document manually.",
    },
    {
      question: "Can I cancel my subscription anytime?",
      answer:
        "Yes! Pro subscriptions can be cancelled anytime. You'll retain access until the end of your billing period, and there are no cancellation fees. We also offer a 7-day free trial and money-back guarantee.",
    },
  ];

  const toggleFAQ = (index) => {
    setOpenIndex(openIndex === index ? null : index);
  };

  return (
    <div className="py-24 bg-background " id="faq">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Section header */}
        <div className="text-center mb-12">
          <h2 className="text-4xl sm:text-5xl font-bold text-foreground mb-4">
            Frequently Asked
            <span className="bg-gradient-to-r from-blue-600 to-purple-600 bg-clip-text text-transparent">
              {" "}
              Questions
            </span>
          </h2>
          <p className="text-xl text-muted-foreground dark:text-gray-300">
            Everything you need to know about Sand Cloud
          </p>
        </div>

        {/* FAQ List */}
        <div className="space-y-4">
          {faqs.map((faq, index) => (
            <div
              key={index}
              className="border border-border dark:border-gray-700 rounded-xl overflow-hidden bg-background dark:bg-card transition-all duration-200 hover:border-blue-500 dark:hover:border-blue-500"
            >
              <button
                onClick={() => toggleFAQ(index)}
                className="
                  w-full px-6 py-5
                  flex items-center justify-between text-left
                  hover:bg-popover
                  transition-colors
                "
              >
                <span className="text-lg font-semibold text-foreground pr-8">
                  {faq.question}
                </span>
                {openIndex === index ? (
                  <ChevronUp className="w-5 h-5 text-blue-600 dark:text-blue-400 flex-shrink-0" />
                ) : (
                  <ChevronDown className="w-5 h-5 text-muted-foreground flex-shrink-0" />
                )}
              </button>

              {openIndex === index && (
                <div className="px-6 pb-5 pt-2 bg-card border-t border-border dark:border-gray-700">
                  <p className="text-muted-foreground dark:text-gray-300 leading-relaxed">
                    {faq.answer}
                  </p>
                </div>
              )}
            </div>
          ))}
        </div>

        {/* Contact CTA */}
        <div className="mt-12 text-center p-8 bg-gradient-to-r from-blue-50 to-purple-50 dark:from-gray-800 dark:to-gray-800 rounded-xl border border-blue-200 dark:border-gray-700">
          <h3 className="text-xl font-bold text-foreground mb-2">
            Still have questions?
          </h3>
          <p className="text-muted-foreground dark:text-gray-300 mb-4">
            Can't find the answer you're looking for? Reach out to our team.
          </p>
          <a
            href="mailto:saranshbhardwaj@gmail.com"
            className="inline-block px-6 py-3 bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-700 hover:to-purple-700 text-foreground font-semibold rounded-lg transition-all duration-200"
          >
            Contact Us
          </a>
        </div>
      </div>
    </div>
  );
}
