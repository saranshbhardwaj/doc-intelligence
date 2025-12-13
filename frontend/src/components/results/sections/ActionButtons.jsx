// src/components/results/sections/ActionButtons.jsx
import { Download, Printer, FileSpreadsheet, FileText, FileDown, MessageSquare } from "lucide-react";
import { Button } from "../../ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
} from "../../ui/dropdown-menu";
import { exportToExcel } from "../../../utils/excelExport/index";
import { exportExtractionAsWord } from "../../../utils/exportExtraction";

export default function ActionButtons({ onFeedbackClick, data, metadata }) {
  const handleExport = async (format) => {
    try {
      if (format === 'excel') {
        await exportToExcel(data, metadata);
        console.log('✅ Exported as Excel');
      } else if (format === 'word') {
        await exportExtractionAsWord(data, metadata);
        console.log('✅ Exported as Word');
      } else if (format === 'pdf') {
        // PDF export via print dialog
        window.print();
        console.log('✅ Print dialog opened for PDF');
      }
    } catch (error) {
      console.error(`Failed to export as ${format}:`, error);
      alert(`Export failed: ${error.message || 'Please try again'}`);
    }
  };

  return (
    <div className="bg-card rounded-xl border border-border p-4 flex flex-wrap justify-between items-center gap-3">
      <div className="flex flex-wrap gap-3">
        {/* Export Dropdown Menu */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="default" size="default" className="font-semibold">
              <Download className="w-4 h-4 mr-2" />
              Export
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="w-56">
            <DropdownMenuItem onClick={() => handleExport('excel')}>
              <FileSpreadsheet className="w-4 h-4 mr-3 text-success" />
              <div className="flex flex-col">
                <span className="font-medium">Excel Workbook</span>
                <span className="text-xs text-muted-foreground">
                  Multi-sheet analysis (.xlsx)
                </span>
              </div>
            </DropdownMenuItem>

            <DropdownMenuItem onClick={() => handleExport('word')}>
              <FileDown className="w-4 h-4 mr-3 text-primary" />
              <div className="flex flex-col">
                <span className="font-medium">Word Document</span>
                <span className="text-xs text-muted-foreground">
                  Professional report (.docx)
                </span>
              </div>
            </DropdownMenuItem>

            <DropdownMenuSeparator />

            <DropdownMenuItem onClick={() => handleExport('pdf')}>
              <FileText className="w-4 h-4 mr-3 text-destructive" />
              <div className="flex flex-col">
                <span className="font-medium">PDF (Print)</span>
                <span className="text-xs text-muted-foreground">
                  Save as PDF via browser
                </span>
              </div>
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        {/* Print Button */}
        <Button
          variant="outline"
          size="default"
          onClick={() => window.print()}
          className="font-semibold"
        >
          <Printer className="w-4 h-4 mr-2" />
          Print
        </Button>
      </div>

      {/* Feedback Button */}
      <Button
        variant="outline"
        size="default"
        onClick={onFeedbackClick}
        className="font-semibold"
      >
        <MessageSquare className="w-4 h-4 mr-2" />
        Give Feedback
      </Button>
    </div>
  );
}
