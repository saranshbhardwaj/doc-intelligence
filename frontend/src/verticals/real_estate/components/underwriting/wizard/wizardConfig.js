import { BarChart2, FileText, FolderOpen } from 'lucide-react';

export const DOC_SLOTS = [
  {
    key: 'om',
    icon: FileText,
    label: 'Offering Memorandum',
    required: true,
    hint: 'Purchase price, unit mix, cap rate, and business plan assumptions.',
  },
  {
    key: 't12',
    icon: BarChart2,
    label: 'T-12 / T-6 Statement',
    required: false,
    hint: 'Trailing income, expenses, and recent operating performance.',
  },
  {
    key: 'rent_roll',
    icon: FolderOpen,
    label: 'Rent Roll',
    required: false,
    hint: 'Occupancy, rents, lease terms, and rollover exposure.',
  },
];

export const TAB_CONFIG = [
  { id: 'acquisition', label: 'Acquisition', desc: 'Price, closing costs, and upfront capital.' },
  { id: 'operations', label: 'Operations', desc: 'Revenue assumptions and operating expense inputs.' },
  { id: 'market', label: 'Market', desc: 'Nearby facilities, population, and income context.' },
  { id: 'debtExit', label: 'Debt & Exit', desc: 'Financing, hold horizon, and exit assumptions.' },
  { id: 'criteria', label: 'Criteria', desc: 'Return hurdles and leverage limits.' },
];

export const VISIBLE_CITATION_FIELD_KEYS = [
  'purchase_price',
  'closing_cost_pct',
  'market_cap_rate_purchase',
  'capex_reserve_per_unit',
  'num_units',
  'rentable_sqft',
  'gross_potential_rent_annual',
  'avg_in_place_rent_per_unit_monthly',
  'avg_market_rent_per_unit_monthly',
  'other_income_annual',
  'vacancy_credit_loss_pct',
  'expense_ratio_current',
  'expense_ratio_pro_forma',
  'bad_debt_annual',
  'corrections_collections_annual',
  'rent_growth_pct',
  'property_tax_annual',
  'property_tax_growth_pct',
  'mil_rate',
  'insurance_annual',
  'mgmt_fee_pct',
  'payroll_annual',
  'repairs_maintenance_annual',
  'utilities_annual',
  'marketing_annual',
  'other_opex_annual',
  'opex_growth_pct',
  'nearby_storage_count_1mi',
  'nearby_storage_count_3mi',
  'nearby_storage_count_5mi',
  'population_3mi',
  'avg_household_income_3mi',
  'storage_sqft_per_capita_3mi',
  'interest_rate_pct',
  'loan_term_years',
  'amortization_years',
  'ltv_pct',
  'hold_period_years',
  'market_cap_rate_sale',
  'exit_cap_rate',
  'selling_cost_pct',
  'target_irr',
  'target_cash_on_cash',
  'target_equity_multiple',
  'max_ltv',
];

export function countVisibleCitations(fieldCitations) {
  if (!fieldCitations) return 0;

  return VISIBLE_CITATION_FIELD_KEYS.reduce((count, fieldKey) => {
    const citation = fieldCitations[fieldKey]
      ?? fieldCitations[`om.${fieldKey}`]
      ?? fieldCitations[`t12.${fieldKey}`]
      ?? fieldCitations[`rent_roll.${fieldKey}`]
      ?? null;

    return citation && !citation.is_default ? count + 1 : count;
  }, 0);
}

export const INITIAL_PROJECT_DATA = {
  name: '',
  address: '',
  asset_type: 'self_storage',
  nearby_storage_count_1mi: '',
  nearby_storage_count_3mi: '',
  nearby_storage_count_5mi: '',
  population_3mi: '',
  avg_household_income_3mi: '',
  storage_sqft_per_capita_3mi: '',
};

export const createDefaultInputs = () => ({
  acquisition: { purchase_price: '', closing_cost_pct: 2, market_cap_rate_purchase: '', capex_reserve_per_unit: 0 },
  operational: {
    gross_potential_rent_annual: '',
    avg_in_place_rent_per_unit_monthly: '',
    avg_market_rent_per_unit_monthly: '',
    vacancy_credit_loss_pct: 10,
    expense_ratio_current: '',
    expense_ratio_pro_forma: '',
    other_income_annual: 0,
    bad_debt_annual: '',
    corrections_collections_annual: '',
    rent_growth_pct: 3,
    property_tax_annual: 0,
    insurance_annual: 0,
    mgmt_fee_pct: 8,
    payroll_annual: 0,
    repairs_maintenance_annual: 0,
    utilities_annual: 0,
    marketing_annual: 0,
    other_opex_annual: 0,
    property_tax_growth_pct: '',
    mil_rate: '',
    opex_growth_pct: 2,
  },
  financing: { interest_rate_pct: 6.5, loan_term_years: 10, amortization_years: 25, ltv_pct: 70 },
  exit: { hold_period_years: 10, market_cap_rate_sale: '', exit_cap_rate: 6.5, selling_cost_pct: 3 },
  criteria: { target_irr: 15, target_cash_on_cash: 8, target_equity_multiple: 2.0, max_ltv: 80 },
  rent_comps: [],
});

export function computeTabProgress(inputs, projectData) {
  const has = (v) => v !== '' && v != null;
  return {
    acquisition: Math.round(
      [inputs.acquisition.purchase_price, inputs.acquisition.closing_cost_pct,
        inputs.acquisition.market_cap_rate_purchase, inputs.acquisition.capex_reserve_per_unit,
        projectData.num_units, projectData.rentable_sqft]
        .filter(has).length / 6 * 100
    ),
    operations: Math.round(
      [inputs.operational.gross_potential_rent_annual, inputs.operational.avg_in_place_rent_per_unit_monthly,
        inputs.operational.avg_market_rent_per_unit_monthly, inputs.operational.vacancy_credit_loss_pct,
        inputs.operational.expense_ratio_pro_forma, inputs.operational.rent_growth_pct,
        inputs.operational.property_tax_annual, inputs.operational.mgmt_fee_pct,
        inputs.operational.opex_growth_pct]
        .filter(has).length / 9 * 100
    ),
    market: Math.round(
      [projectData.nearby_storage_count_1mi, projectData.nearby_storage_count_3mi,
        projectData.nearby_storage_count_5mi, projectData.population_3mi,
        projectData.avg_household_income_3mi, projectData.storage_sqft_per_capita_3mi]
        .filter(has).length / 6 * 100
    ),
    debtExit: Math.round(
      [inputs.financing.interest_rate_pct, inputs.financing.loan_term_years,
        inputs.financing.amortization_years, inputs.financing.ltv_pct,
        inputs.exit.hold_period_years, inputs.exit.exit_cap_rate, inputs.exit.selling_cost_pct]
        .filter(has).length / 7 * 100
    ),
    criteria: Math.round(
      [inputs.criteria.target_irr, inputs.criteria.target_cash_on_cash,
        inputs.criteria.target_equity_multiple, inputs.criteria.max_ltv]
        .filter(has).length / 4 * 100
    ),
  };
}
