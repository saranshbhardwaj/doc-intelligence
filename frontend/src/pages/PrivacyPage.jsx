// frontend/src/pages/PrivacyPage.jsx
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

export default function PrivacyPage() {
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
          <h1 className="text-4xl font-bold text-foreground mb-2">Privacy Policy</h1>
          <p className="text-sm text-muted-foreground">Last updated: April 13, 2026</p>
        </div>

        <Section title="What We Collect">
          <p>
            We collect the information you provide when creating an account: your name,
            email address, and organization. We also collect the documents you upload
            for processing (PDFs, Excel files) and the data extracted from them.
          </p>
          <p>
            We collect standard server logs including IP addresses, browser type, and
            pages visited, used solely for security and performance monitoring.
          </p>
        </Section>

        <Section title="How Your Documents Are Stored">
          <p>
            Documents you upload are stored on Cloudflare R2, an encrypted
            cloud storage service. All files are encrypted at rest and in transit
            using industry-standard TLS encryption.
          </p>
          <p>
            When you delete a document, it is permanently deleted from our storage
            immediately. You can delete your documents at any time from within the app.
          </p>
        </Section>

        <Section title="We Don't Train AI on Your Documents">
          <p className="font-semibold text-foreground">
            Your uploaded documents are never used to train, fine-tune, or improve
            any AI model. Ours or anyone else&apos;s.
          </p>
          <p>
            Documents are processed to extract data on your behalf and for no other
            purpose. We do not sell, license, or share your document content with
            any third party.
          </p>
        </Section>

        <Section title="Third-Party Services">
          <p>
            LatticeBlu uses the following third-party services to operate:
          </p>
          <ul className="list-disc list-inside space-y-1">
            <li>Anthropic (AI inference for document analysis, documents sent for processing only)</li>
            <li>Cloudflare R2 (encrypted document storage)</li>
            <li>WorkOS (authentication and user management)</li>
          </ul>
          <p>
            Each provider has its own privacy policy. Documents sent to Anthropic
            for inference are governed by Anthropic&apos;s data processing agreement,
            which prohibits use of customer data for training.
          </p>
        </Section>

        <Section title="Your Rights">
          <p>
            You may request access to, correction of, or deletion of your personal
            data at any time. To exercise these rights, email us at{" "}
            <a href="mailto:saranshbhardwaj@gmail.com" className="text-primary hover:underline">
              saranshbhardwaj@gmail.com
            </a>.
          </p>
          <p>
            We will respond to data requests within 3 business days.
          </p>
        </Section>

        <Section title="Cookies">
          <p>
            We use only essential session cookies required for authentication. We do
            not use advertising cookies or third-party tracking.
          </p>
        </Section>

        <Section title="Changes to This Policy">
          <p>
            We may update this policy as the product evolves. Significant changes will
            be communicated via email. Continued use of LatticeBlu after changes
            constitutes acceptance of the updated policy.
          </p>
        </Section>

        <Section title="Contact">
          <p>
            For privacy questions or data requests, contact:{" "}
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
