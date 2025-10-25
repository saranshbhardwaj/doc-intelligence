// src/components/results/ResultsView.jsx
import { useState } from "react";
import Modal from "../common/Modal";
import FeedbackForm from "../feedback/FeedbackForm";

// Import all section components
import ActionButtons from "./sections/ActionButtons";
import CompanyHeader from "./sections/CompanyHeader";
import KeyMetricsDashboard from "./sections/KeyMetricsDashboard";
import TransactionOverview from "./sections/TransactionOverview";
import CompanyInformation from "./sections/CompanyInformation";
import GrowthAnalysis from "./sections/GrowthAnalysis";
import FinancialPerformance from "./sections/FinancialPerformance";
import BalanceSheet from "./sections/BalanceSheet";
import FinancialRatios from "./sections/FinancialRatios";
import ValuationMultiples from "./sections/ValuationMultiples";
import CapitalStructure from "./sections/CapitalStructure";
import OperatingMetrics from "./sections/OperatingMetrics";
import CustomerMetrics from "./sections/CustomerMetrics";
import MarketAnalysis from "./sections/MarketAnalysis";
import InvestmentThesis from "./sections/InvestmentThesis";
import StrategicRationale from "./sections/StrategicRationale";
import DerivedMetrics from "./sections/DerivedMetrics";
import KeyRisks from "./sections/KeyRisks";
import ManagementTeam from "./sections/ManagementTeam";
import ExtractionNotes from "./sections/ExtractionNotes";
import FeedbackBanner from "./sections/FeedbackBanner";

export default function ResultsView({ result }) {
  const [showFeedback, setShowFeedback] = useState(false);

  if (!result || !result.data) {
    return null;
  }
  const data = result.data;

  return (
    <div
      className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100
    dark:from-gray-900 dark:to-gray-800 py-8 px-4 transition-colors duration-200"
    >
      <div className="max-w-7xl mx-auto space-y-6">
        <ActionButtons
          onFeedbackClick={() => setShowFeedback(true)}
          data={data}
          metadata={result.metadata}
        />

        <CompanyHeader data={data} metadata={result.metadata} />

        <KeyMetricsDashboard data={data} />

        <TransactionOverview data={data} />

        <CompanyInformation data={data} />

        <GrowthAnalysis data={data} />

        <FinancialPerformance data={data} />

        <BalanceSheet data={data} />

        <FinancialRatios data={data} />

        <ValuationMultiples data={data} />

        <CapitalStructure data={data} />

        <OperatingMetrics data={data} />

        <CustomerMetrics data={data} />

        <MarketAnalysis data={data} />

        <InvestmentThesis data={data} />

        <StrategicRationale data={data} />

        <DerivedMetrics data={data} />

        <KeyRisks data={data} />

        <ManagementTeam data={data} />

        <ExtractionNotes data={data} />

        <FeedbackBanner onFeedbackClick={() => setShowFeedback(true)} />

        {/* Footer */}
        <div className="bg-white rounded-xl shadow-md p-6 text-center text-sm text-gray-600">
          <p>
            This is a confidential document prepared for private equity
            evaluation purposes.
          </p>
          <p className="mt-2">
            Generated using AI-powered extraction from CIM documents.
          </p>
        </div>
      </div>

      {/* Feedback Modal */}
      <Modal
        isOpen={showFeedback}
        onClose={() => setShowFeedback(false)}
        title="📝 Help Us Improve"
      >
        <FeedbackForm
          requestId={result.metadata.request_id}
          onClose={() => setShowFeedback(false)}
        />
      </Modal>
    </div>
  );
}
