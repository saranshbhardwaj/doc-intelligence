/**
 * Real Estate Dashboard
 * Main entry point for RE vertical
 */
import { useVertical } from '../../../core/hooks/useVertical';
import { Link } from 'react-router-dom';
import AppLayout from '../../../components/layout/AppLayout';

export default function REDashboard() {
  const { config } = useVertical();

  return (
    <AppLayout>
      <div className="max-w-7xl mx-auto px-6 py-8">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-semibold text-foreground">
            {config?.name} Dashboard
          </h1>
          <p className="text-muted-foreground mt-2">
            {config?.description}
          </p>
        </div>

        {/* Quick Actions */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-8">
          <Link
            to="/app/library"
            className="p-6 bg-card rounded-lg border border-border hover:border-primary/50 hover:bg-accent/5 transition-all"
          >
            <div className="flex items-center gap-4">
              <div className="p-3 bg-primary/10 rounded-lg">
                <svg className="w-6 h-6 text-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
                </svg>
              </div>
              <div>
                <h3 className="font-semibold text-foreground">
                  Document Library
                </h3>
                <p className="text-sm text-muted-foreground">
                  Manage your documents
                </p>
              </div>
            </div>
          </Link>

          <Link
            to="/app/chat"
            className="p-6 bg-card rounded-lg border border-border hover:border-primary/50 hover:bg-accent/5 transition-all"
          >
            <div className="flex items-center gap-4">
              <div className="p-3 bg-success/10 rounded-lg">
                <svg className="w-6 h-6 text-success" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                </svg>
              </div>
              <div>
                <h3 className="font-semibold text-foreground">
                  Chat Mode
                </h3>
                <p className="text-sm text-muted-foreground">
                  Ask questions about docs
                </p>
              </div>
            </div>
          </Link>

          <Link
            to="/app/re/templates"
            className="p-6 bg-card rounded-lg border border-border hover:border-primary/50 hover:bg-accent/5 transition-all"
          >
            <div className="flex items-center gap-4">
              <div className="p-3 bg-accent/20 rounded-lg">
                <svg className="w-6 h-6 text-accent-foreground" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
              </div>
              <div>
                <h3 className="font-semibold text-foreground">
                  Excel Templates
                </h3>
                <p className="text-sm text-muted-foreground">
                  Upload and manage templates
                </p>
              </div>
            </div>
          </Link>
        </div>

        {/* Info Cards */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="bg-card rounded-lg border border-border p-6">
            <h2 className="text-lg font-semibold text-foreground mb-4">
              About Real Estate Vertical
            </h2>
            <p className="text-muted-foreground mb-4 text-sm">
              The Real Estate vertical is designed to help you analyze property documents and automatically fill Excel templates with extracted data.
            </p>
            <div className="space-y-2.5">
              <div className="flex items-start gap-2">
                <svg className="w-5 h-5 text-success mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
                <span className="text-sm text-foreground">
                  Upload property documents to your library
                </span>
              </div>
              <div className="flex items-start gap-2">
                <svg className="w-5 h-5 text-success mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
                <span className="text-sm text-foreground">
                  Chat with your documents using AI
                </span>
              </div>
              <div className="flex items-start gap-2">
                <svg className="w-5 h-5 text-success mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
                <span className="text-sm text-foreground">
                  Automatically fill Excel templates with PDF data
                </span>
              </div>
            </div>
          </div>

          <div className="bg-card rounded-lg border border-border p-6">
            <h2 className="text-lg font-semibold text-foreground mb-4">
              Getting Started
            </h2>
            <ol className="space-y-4">
              <li className="flex items-start gap-3">
                <span className="flex-shrink-0 w-6 h-6 bg-primary text-primary-foreground rounded-full flex items-center justify-center text-sm font-semibold">
                  1
                </span>
                <div>
                  <h4 className="font-medium text-foreground">
                    Upload Documents
                  </h4>
                  <p className="text-sm text-muted-foreground mt-0.5">
                    Go to the Document Library and upload your property files
                  </p>
                </div>
              </li>
              <li className="flex items-start gap-3">
                <span className="flex-shrink-0 w-6 h-6 bg-primary text-primary-foreground rounded-full flex items-center justify-center text-sm font-semibold">
                  2
                </span>
                <div>
                  <h4 className="font-medium text-foreground">
                    Start Chatting
                  </h4>
                  <p className="text-sm text-muted-foreground mt-0.5">
                    Use Chat Mode to ask questions and analyze your documents
                  </p>
                </div>
              </li>
              <li className="flex items-start gap-3">
                <span className="flex-shrink-0 w-6 h-6 bg-primary text-primary-foreground rounded-full flex items-center justify-center text-sm font-semibold">
                  3
                </span>
                <div>
                  <h4 className="font-medium text-foreground">
                    Fill Templates
                  </h4>
                  <p className="text-sm text-muted-foreground mt-0.5">
                    Upload Excel templates and automatically fill them with PDF data
                  </p>
                </div>
              </li>
            </ol>
          </div>
        </div>
      </div>
    </AppLayout>
  );
}
