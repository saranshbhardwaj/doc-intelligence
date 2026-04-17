// src/components/landing/FAQ.jsx
import { useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";

export default function FAQ() {
  const [openIndex, setOpenIndex] = useState(null);

  const faqs = [
    {
      question: "What document types does Basilfy support?",
      answer:
        "Basilfy supports offering memoranda, rent rolls, operating statements, and property appraisals in PDF and Word (.docx) format. For template fill, we support .xlsx Excel files.",
    },
    {
      question: "How does template fill work?",
      answer:
        "Upload your PDF and pick your Excel template. Basilfy goes through the document and fills in the cells: cap rate, NOI, occupancy, asking price, debt service. You review each value with its source citation, fix anything off, and download.",
    },
    {
      question: "How accurate is the extraction?",
      answer:
        "We achieve 95%+ accuracy on standard deal documents. Every extracted field includes a citation back to the source page and a confidence score. We always recommend reviewing before using in deal decisions.",
    },
    {
      question: "Is my data secure? Are my documents used for AI training?",
      answer:
        "All uploads are encrypted in transit and at rest. Your documents are never used to train any AI model. Not ours, not anyone else's. When you delete a document, it's gone immediately.",
    },
    {
      question: "How long does processing take?",
      answer:
        "Most documents (40-80 pages) are processed in 1-6 minutes. You'll see real-time progress updates while your document is being analyzed.",
    },
    {
      question: "What Excel templates are supported?",
      answer:
        "Any standard .xlsx template works. You define which cells map to which fields (cap rate, NOI, etc.) in the template schema, and Basilfy fills them automatically. Contact us to help set up your template.",
    },
    {
      question: "What if the extraction has errors?",
      answer:
        "Every extracted value shows its source citation so you can verify it. You can override any value before filling. If you find persistent inaccuracies, use the feedback form or contact us at saranshbhardwaj@gmail.com and we'll improve the extraction for your document type.",
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
            Everything you need to know about Basilfy
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
