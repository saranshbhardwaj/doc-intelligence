// src/components/results/sections/ActionButtons.jsx
import { Download, Share2, Printer } from "lucide-react";
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

  // const handleShare = () => {
  //   console.log("Share");
  //   // TODO: Implement
  // };

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl shadow-md p-4 flex flex-wrap justify-between items-center gap-3">
      <div className="flex flex-wrap gap-3">
        {/* Export to Excel - Work in Progress (keep code but disable) */}
        <div className="relative group">
          <button
            onClick={handleExportExcel}
            className="flex items-center gap-2 px-4 py-2 bg-gray-400 dark:bg-gray-600 text-gray-200 dark:text-gray-400 rounded-lg font-semibold shadow-sm opacity-60"
          >
            <Download className="w-4 h-4" />
            Export to Excel
          </button>
          {/* Tooltip */}
          {/* <div className="absolute bottom-full left-1/2 transform -translate-x-1/2 mb-2 px-3 py-2 bg-gray-900 dark:bg-gray-700 text-white text-sm rounded-lg opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none whitespace-nowrap z-10">
            🚧 Work in Progress
            <div className="absolute top-full left-1/2 transform -translate-x-1/2 border-4 border-transparent border-t-gray-900 dark:border-t-gray-700"></div>
          </div> */}
        </div>

        <button
          onClick={handlePrint}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors font-semibold shadow-sm"
        >
          <Printer className="w-4 h-4" />
          Print Report
        </button>
        {/* <button
          onClick={handleShare}
          className="flex items-center gap-2 px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors font-semibold shadow-sm"
        >
          <Share2 className="w-4 h-4" />
          Share
        </button> */}
      </div>
      <button
        onClick={onFeedbackClick}
        className="flex items-center gap-2 px-4 py-2 bg-gray-600 dark:bg-gray-700 text-white rounded-lg hover:bg-gray-700 dark:hover:bg-gray-600 transition-colors font-semibold shadow-sm"
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
