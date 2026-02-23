// src/components/landing/FAQ.jsx
import { useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";

export default function FAQ() {
  const [openIndex, setOpenIndex] = useState(null);

  const faqs = [
    {
      question: "What file formats do you support?",
      answer:
        "We support text-based PDFs, scanned PDFs, and Word documents. For Excel template fill workflows, we support .xlsx files.",
    },
    {
      question: "How accurate is the extraction?",
      answer:
        "We achieve 95%+ accuracy on standard deal documents. Every extracted field includes a citation back to the source page and a confidence score for any inferred values. So you can verify exactly where the data came from. We always recommend reviewing before critical deal decisions.",
    },
    {
      question: "Is my data secure? What happens to my documents?",
      answer:
        "Your data security is our top priority. All uploads are encrypted in transit and at rest. Your documents are processed and then deleted from our servers after 30 days. We never share your documents with third parties, and all processing is confidential.",
    },
    {
      question: "How long does processing take?",
      answer:
        "Most documents (40-80 pages) are processed in 1-6 minutes. You'll see real-time progress updates while your document is being analyzed.",
    },
    {
      question: "What data do you extract from deal documents?",
      answer:
        "For PE deals: company overview, financials (revenue, EBITDA, margins, FCF), balance sheet, valuation multiples, capital structure, customer metrics, management team, risks, and strategic rationale. For real estate: NOI, cap rates, occupancy, rent rolls, lease terms, operating expenses, and market comps. All data is delivered in structured Excel format.",
    },
    {
      question: "Do you support real estate documents like rent rolls and offering memoranda?",
      answer:
        "Yes! LoomStack supports real estate document types including offering memoranda, rent rolls, operating statements, property appraisals, and market reports. Our RE workflows extract NOI, cap rates, occupancy, lease terms, and more, and can auto-populate your Excel underwriting templates.",
    },
    {
      question: "Do you support languages other than English?",
      answer:
        "Currently, we only support English-language documents. Support for other languages is on our roadmap.",
    },
    {
      question: "What if the extraction has errors?",
      answer:
        "If you find inaccuracies, please use the feedback form on the results page. We review all feedback and continuously improve our AI models. For critical errors, contact us at saranshbhardwaj@gmail.com and we'll re-process your document manually.",
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
            Everything you need to know about LoomStack
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
