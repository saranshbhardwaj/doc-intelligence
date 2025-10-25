// src/components/results/sections/TransactionOverview.jsx
import { FileText } from "lucide-react";
import Section from "../Section";
import DataField from "../DataField";
import { safeText } from "../../../utils/formatters";

export default function TransactionOverview({ data }) {
  const tx = data.transaction_details || {};

  if (!tx || !Object.values(tx).some((v) => v != null)) {
    return null;
  }

  return (
    <Section title="Transaction Overview" icon={FileText} highlight={true}>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-4">
        {tx.asking_price && (
          <DataField
            label="Asking Price"
            value={tx.asking_price}
            format="currency"
            highlight={true}
          />
        )}
        {tx.deal_type && (
          <DataField label="Deal Type" value={tx.deal_type} highlight={true} />
        )}
        {tx.implied_valuation_hint && (
          <DataField
            label="Valuation Hint"
            value={tx.implied_valuation_hint}
            highlight={true}
          />
        )}
      </div>
      <div className="space-y-4">
        {tx.seller_motivation && (
          <div className="bg-white p-4 rounded-lg border border-gray-200">
            <h4 className="text-sm font-semibold text-gray-700 mb-2">
              Seller Motivation
            </h4>
            <p className="text-gray-600">{safeText(tx.seller_motivation)}</p>
          </div>
        )}
        {tx.assets_for_sale && (
          <div className="bg-white p-4 rounded-lg border border-gray-200">
            <h4 className="text-sm font-semibold text-gray-700 mb-2">
              Assets for Sale
            </h4>
            <p className="text-gray-600">{safeText(tx.assets_for_sale)}</p>
          </div>
        )}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {tx.post_sale_involvement && (
            <div className="bg-white p-4 rounded-lg border border-gray-200">
              <h4 className="text-sm font-semibold text-gray-700 mb-2">
                Post-Sale Involvement
              </h4>
              <p className="text-gray-600">
                {safeText(tx.post_sale_involvement)}
              </p>
            </div>
          )}
          {tx.auction_deadline && (
            <div className="bg-white p-4 rounded-lg border border-gray-200">
              <h4 className="text-sm font-semibold text-gray-700 mb-2">
                Auction Deadline
              </h4>
              <p className="text-gray-600">{safeText(tx.auction_deadline)}</p>
            </div>
          )}
        </div>
      </div>
    </Section>
  );
}
