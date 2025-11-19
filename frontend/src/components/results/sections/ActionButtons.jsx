// src/components/results/sections/ActionButtons.jsx
import { Download, Printer } from "lucide-react";
import { exportToExcel } from "../../../utils/excelExport/index";

export default function ActionButtons({ onFeedbackClick, data, metadata }) {
  const handleExportExcel = async () => {
    try {
      await exportToExcel(data, metadata);
    } catch (error) {
      console.error("Failed to export to Excel:", error);
      alert("Failed to export to Excel. Please try again.");
    }
  };

  const handlePrint = () => {
    window.print();
  };

  return (
    <div className="bg-card rounded-xl shadow-md p-4 flex flex-wrap justify-between items-center gap-3">
      <div className="flex flex-wrap gap-3">
        {/* Export to Excel */}
        <button
          onClick={handleExportExcel}
          className="flex items-center gap-2 px-4 py-2 bg-destructive text-foreground rounded-lg hover:bg-destructive/90 transition-colors font-semibold shadow-sm"
        >
          <Download className="w-4 h-4" />
          Export to Excel
        </button>

        {/* Print Report */}
        <button
          onClick={handlePrint}
          className="flex items-center gap-2 px-4 py-2 bg-primary text-foreground rounded-lg hover:bg-primary/90 transition-colors font-semibold shadow-sm"
        >
          <Printer className="w-4 h-4" />
          Print Report
        </button>

        {/* You can add Share button here if needed */}
      </div>

      {/* Feedback button */}
      <button
        onClick={onFeedbackClick}
        className="flex items-center gap-2 px-4 py-2 bg-muted text-foreground rounded-lg hover:bg-muted/90 transition-colors font-semibold shadow-sm"
      >
        <svg
          className="w-4 h-4"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M7 8h10M7 12h4m1 8l-4-4H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-3l-4 4z"
          />
        </svg>
        Give Feedback
      </button>
    </div>
  );
}
