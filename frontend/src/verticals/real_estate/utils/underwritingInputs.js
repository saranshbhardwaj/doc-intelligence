/**
 * Percentage fields are stored as decimals in the backend (0.065 = 6.5%)
 * and shown as human-readable numbers in the UI (6.5).
 * All conversions are centralised here — add new pct fields to PCT_FIELDS only.
 */

const PCT_FIELDS = {
  acquisition: ['closing_cost_pct', 'market_cap_rate_purchase'],
  operational: ['vacancy_credit_loss_pct', 'expense_ratio_t12', 'expense_ratio_current', 'expense_ratio_year1', 'expense_ratio_pro_forma', 'rent_growth_pct', 'mgmt_fee_pct', 'property_tax_growth_pct', 'property_tax_assessment_ratio', 'opex_growth_pct'],
  financing:   ['interest_rate_pct', 'ltv_pct'],
  exit:        ['market_cap_rate_sale', 'exit_cap_rate', 'selling_cost_pct'],
  criteria:    ['target_irr', 'target_cash_on_cash', 'max_ltv'],
};

function convertSection(section, fields, factor) {
  if (!section) return section;
  const out = { ...section };
  for (const f of fields) {
    if (out[f] != null && out[f] !== '') {
      out[f] = out[f] * factor;
    }
  }
  return out;
}

/** Backend decimal inputs → UI human-readable (0.065 → 6.5) */
export function fromApiInputs(inp) {
  if (!inp) return inp;
  return {
    ...inp,
    acquisition: convertSection(inp.acquisition, PCT_FIELDS.acquisition, 100),
    operational:  convertSection(inp.operational,  PCT_FIELDS.operational,  100),
    financing:    convertSection(inp.financing,    PCT_FIELDS.financing,    100),
    exit:         convertSection(inp.exit,         PCT_FIELDS.exit,         100),
    criteria:     convertSection(inp.criteria,     PCT_FIELDS.criteria,     100),
  };
}

/** UI human-readable inputs → backend decimal (6.5 → 0.065) */
export function toApiInputs(inp) {
  if (!inp) return inp;
  return {
    ...inp,
    acquisition: convertSection(inp.acquisition, PCT_FIELDS.acquisition, 0.01),
    operational:  convertSection(inp.operational,  PCT_FIELDS.operational,  0.01),
    financing:    convertSection(inp.financing,    PCT_FIELDS.financing,    0.01),
    exit:         convertSection(inp.exit,         PCT_FIELDS.exit,         0.01),
    criteria:     convertSection(inp.criteria,     PCT_FIELDS.criteria,     0.01),
  };
}
