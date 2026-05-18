// frontend/src/pages/TermsPage.jsx
import { useNavigate } from "react-router-dom";
import { ArrowLeft } from "lucide-react";

function Section({ title, children }) {
  return (
    <section>
      <h2 className="text-xl font-bold text-foreground mb-3">{title}</h2>
      <div className="text-muted-foreground leading-relaxed space-y-3">{children}</div>
    </section>
  );
}

export default function TermsPage() {
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
        <div>
          <h1 className="text-4xl font-bold text-foreground mb-2">Terms of Service</h1>
          <p className="text-sm text-muted-foreground">Last updated: April 13, 2026</p>
        </div>

        <Section title="Acceptance of Terms">
          <p>
            By accessing or using LatticeBlu, you agree to be bound by these Terms of
            Service. If you do not agree, do not use the service.
          </p>
        </Section>

        <Section title="Description of Service">
          <p>
            LatticeBlu is an AI-powered document intelligence platform that extracts
            structured data from real estate documents and populates Excel templates.
            The service is currently in closed beta and provided as-is.
          </p>
        </Section>

        <Section title="Acceptable Use">
          <p>You agree to use LatticeBlu only for lawful purposes. You may not:</p>
          <ul className="list-disc list-inside space-y-1">
            <li>Upload documents you do not have the right to process</li>
            <li>Attempt to reverse-engineer, scrape, or abuse the service</li>
            <li>Share your account credentials with others</li>
            <li>Use the service to process documents containing illegal content</li>
          </ul>
        </Section>

        <Section title="Your Content">
          <p>
            You retain ownership of all documents you upload. By uploading documents,
            you grant LatticeBlu a limited license to process them solely for the purpose
            of providing the service to you.
          </p>
          <p>
            You are responsible for ensuring you have the right to upload and process
            the documents you submit.
          </p>
        </Section>

        <Section title="No Warranties">
          <p>
            LatticeBlu is provided &quot;as is&quot; without warranties of any kind,
            express or implied. We do not warrant that the service will be uninterrupted,
            error-free, or that extracted data will be 100% accurate. Always review
            AI-extracted data before using it in financial decisions.
          </p>
        </Section>

        <Section title="Limitation of Liability">
          <p>
            To the maximum extent permitted by law, LatticeBlu and its operators shall
            not be liable for any indirect, incidental, special, or consequential
            damages arising from your use of the service, including but not limited
            to losses from reliance on extracted data.
          </p>
        </Section>

        <Section title="Beta Service">
          <p>
            LatticeBlu is currently in closed beta. Features may change, data may be
            reset, and the service may be interrupted without notice. We appreciate
            your feedback and patience during this phase.
          </p>
        </Section>

        <Section title="Termination">
          <p>
            We reserve the right to suspend or terminate access to the service at
            any time, for any reason, with or without notice.
          </p>
        </Section>

        <Section title="Governing Law">
          <p>
            These terms are governed by the laws of the State of Delaware, United
            States, without regard to its conflict of law provisions.
          </p>
        </Section>

        <Section title="Contact">
          <p>
            Questions about these terms? Contact us at{" "}
            <a href="mailto:saranshbhardwaj@gmail.com" className="text-primary hover:underline">
              saranshbhardwaj@gmail.com
            </a>
          </p>
        </Section>
      </main>

      <footer className="border-t border-border py-4 text-center text-sm text-muted-foreground">
        <p>&copy; 2026 LatticeBlu. All rights reserved.</p>
      </footer>
    </div>
  );
}
