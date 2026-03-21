import { FileText } from "lucide-react";

export default function AmendmentChainTree({ docId, docNameMap, amendmentLink, parentDoc }) {
  return (
    <div className="bg-muted/30 rounded-lg p-3">
      <h4 className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-2">
        Amendment Chain
      </h4>
      <div className="text-xs space-y-1">
        <div className="flex items-center gap-1.5">
          <span className="text-muted-foreground">└─</span>
          <FileText className="w-3 h-3 text-muted-foreground" />
          <span className="font-medium">{parentDoc || "Parent document"}</span>
          <span className="text-muted-foreground">(Original)</span>
        </div>
        <div className="flex items-center gap-1.5 pl-5">
          <span className="text-muted-foreground">├─</span>
          <FileText className="w-3 h-3 text-primary" />
          <span className="font-medium text-primary">{docNameMap[docId] || "This document"}</span>
          <span className="text-muted-foreground">
            ({amendmentLink?.amendment_type || "modifies"}, {Math.round((amendmentLink?.confidence || 0) * 100)}%)
          </span>
        </div>
      </div>
    </div>
  );
}
