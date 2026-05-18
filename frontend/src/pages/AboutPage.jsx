// frontend/src/pages/AboutPage.jsx
import { useNavigate } from "react-router-dom";
import { ArrowLeft, Mail } from "lucide-react";

export default function AboutPage() {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-background">
      <div className="border-b border-border px-6 py-4 flex items-center gap-4">
        <button
          onClick={() => navigate("/")}
          className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to Home
        </button>
        <button
          onClick={() => navigate("/")}
          className="text-xl font-extrabold tracking-tight bg-gradient-to-r from-primary to-accent bg-clip-text text-transparent"
        >
          LatticeBlu
        </button>
      </div>

      <main className="max-w-2xl mx-auto px-6 py-10 space-y-10">
        <section>
          <h2 className="text-sm font-bold uppercase tracking-widest text-primary mb-4">The Problem</h2>
          <h1 className="text-3xl font-bold text-foreground mb-4">
            Every deal, the same manual work.
          </h1>
          <p className="text-lg text-muted-foreground leading-relaxed">
            Real estate analysts spend hours copying numbers from offering memorandums
            into Excel templates. Cap rates, NOI, occupancy, asking price. Pulled
            from 80-page PDFs, typed by hand, deal after deal. It takes hours every time.
          </p>
        </section>

        <section>
          <h2 className="text-sm font-bold uppercase tracking-widest text-primary mb-4">What We Built</h2>
          <p className="text-lg text-muted-foreground leading-relaxed mb-4">
            LatticeBlu reads your offering memorandum and fills your Excel template
            automatically. Upload the OM, select your template, and LatticeBlu extracts
            the key metrics: asking price, cap rate, NOI, occupancy, and debt service.
            It maps them directly into your cells.
          </p>
          <p className="text-lg text-muted-foreground leading-relaxed">
            You review the results, correct anything off, and download. What used to
            take 2 to 3 hours takes minutes. You can also chat with the document directly.
            Ask questions, pull specific figures, verify assumptions. All without leaving the app.
          </p>
        </section>

        <section>
          <h2 className="text-sm font-bold uppercase tracking-widest text-primary mb-4">Who We Are</h2>
          <p className="text-lg text-muted-foreground leading-relaxed mb-6">
            LatticeBlu is founder-led and built specifically for real estate professionals.
            We&apos;re in closed beta with a small group of RE analysts. If you have
            feedback, questions, or want to share what&apos;s not working, reach out directly.
          </p>
          <a
            href="mailto:saranshbhardwaj@gmail.com"
            className="inline-flex items-center gap-2 px-6 py-3 bg-primary text-primary-foreground font-semibold rounded-full hover:bg-primary/90 transition-colors shadow-md"
          >
            <Mail className="w-4 h-4" />
            saranshbhardwaj@gmail.com
          </a>
        </section>
      </main>

      <footer className="border-t border-border py-4 text-center text-sm text-muted-foreground">
        <p>&copy; 2026 LatticeBlu. All rights reserved.</p>
      </footer>
    </div>
  );
}
