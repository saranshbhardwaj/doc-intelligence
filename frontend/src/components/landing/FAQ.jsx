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
        "Yes! frearaAI supports real estate document types including offering memoranda, rent rolls, operating statements, property appraisals, and market reports. Our RE workflows extract NOI, cap rates, occupancy, lease terms, and more, and can auto-populate your Excel underwriting templates.",
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
    <div className="py-24 bg-background" id="faq">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Section header */}
        <div className="text-center mb-12">
          <h2 className="text-4xl sm:text-5xl font-bold text-foreground mb-4">
            Frequently Asked
            <span className="bg-gradient-to-r from-primary to-accent bg-clip-text text-transparent">
              {" "}Questions
            </span>
          </h2>
          <p className="text-xl text-muted-foreground">
            Everything you need to know about frearaAI
          </p>
        </div>

        {/* FAQ List */}
        <div className="space-y-3">
          {faqs.map((faq, index) => (
            <div
              key={index}
              className="glass-card rounded-2xl overflow-hidden hover:border-primary/40 transition-all duration-200"
            >
              <button
                onClick={() => toggleFAQ(index)}
                className="w-full px-6 py-5 flex items-center justify-between text-left hover:bg-muted/30 transition-colors"
              >
                <span className="text-base font-semibold text-foreground pr-8">
                  {faq.question}
                </span>
                {openIndex === index ? (
                  <ChevronUp className="w-5 h-5 text-primary flex-shrink-0" />
                ) : (
                  <ChevronDown className="w-5 h-5 text-muted-foreground flex-shrink-0" />
                )}
              </button>

              {openIndex === index && (
                <div className="px-6 pb-5 pt-2 border-t border-border/50">
                  <p className="text-muted-foreground leading-relaxed">
                    {faq.answer}
                  </p>
                </div>
              )}
            </div>
          ))}
        </div>

        {/* Contact CTA */}
        <div className="mt-12 text-center glass-card rounded-3xl p-8 border-primary/20">
          <h3 className="text-xl font-bold text-foreground mb-2">
            Still have questions?
          </h3>
          <p className="text-muted-foreground mb-6">
            Can't find the answer you're looking for? Reach out to our team.
          </p>
          <a
            href="mailto:saranshbhardwaj@gmail.com"
            className="inline-block px-8 py-3 bg-primary text-primary-foreground font-semibold rounded-full hover:bg-primary/90 hover:scale-105 transition-all duration-200 shadow-md shadow-primary/20"
          >
            Contact Us
          </a>
        </div>
      </div>
    </div>
  );
}
