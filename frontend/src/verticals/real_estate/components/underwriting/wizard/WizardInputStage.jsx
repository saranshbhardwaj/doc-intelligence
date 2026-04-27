import {
  ArrowRight,
  BarChart2,
  ChevronDown,
  ChevronRight,
  Loader2,
  Plus,
  Sparkles,
  Trash2,
  TrendingUp,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { TAB_CONFIG } from './wizardConfig';
import {
  FieldGroup,
  NumericField,
  OperationsWarnings,
  ValueAddEvidence,
} from './WizardFields';

export default function WizardInputStage({
  activeTab,
  setActiveTab,
  tabProgress,
  inputs,
  projectData,
  currentRun,
  runIdFromUrl,
  citationCount,
  extractionDone,
  anyDocSelected,
  getCitation,
  handleOpenSource,
  patchAcq,
  patchOp,
  patchProject,
  patchFin,
  patchExit,
  patchCrit,
  addRentComp,
  patchRentComp,
  removeRentComp,
  rentCompsCitation,
  showValueAdd,
  setShowValueAdd,
  handleSaveAndCalculate,
  isSubmitting,
  navigateToResults,
}) {
  const activeTabIndex = TAB_CONFIG.findIndex((tab) => tab.id === activeTab);

  const renderActiveTabPanel = () => {
    switch (activeTab) {
      case 'acquisition':
        return (
          <div className="fields-grid">
            <NumericField label="Purchase Price" value={inputs.acquisition.purchase_price} onChange={(v) => patchAcq('purchase_price', v)} placeholder="5,000,000" prefix="$" citation={getCitation('purchase_price')} onOpenSource={handleOpenSource} />
            <NumericField label="Closing Cost" value={inputs.acquisition.closing_cost_pct} onChange={(v) => patchAcq('closing_cost_pct', v)} placeholder="2" suffix="%" citation={getCitation('closing_cost_pct')} onOpenSource={handleOpenSource} />
            <NumericField label="Market Cap Rate Purchase" value={inputs.acquisition.market_cap_rate_purchase} onChange={(v) => patchAcq('market_cap_rate_purchase', v)} placeholder="6.0" suffix="%" citation={getCitation('market_cap_rate_purchase')} onOpenSource={handleOpenSource} />
            <NumericField label="CapEx Reserve / Unit" value={inputs.acquisition.capex_reserve_per_unit} onChange={(v) => patchAcq('capex_reserve_per_unit', v)} placeholder="0" prefix="$" suffix="/unit" citation={getCitation('capex_reserve_per_unit')} onOpenSource={handleOpenSource} />
            <FieldGroup label="Property" />
            <NumericField
              label="Total Units"
              value={projectData.num_units ?? ''}
              onChange={(v) => patchProject('num_units', v === '' ? '' : parseInt(v, 10) || '')}
              citation={getCitation('num_units')}
              onOpenSource={handleOpenSource}
            />
            <NumericField
              label="Rentable Sq Ft"
              value={projectData.rentable_sqft ?? ''}
              onChange={(v) => patchProject('rentable_sqft', v)}
              suffix="sqft"
              citation={getCitation('rentable_sqft')}
              onOpenSource={handleOpenSource}
            />
          </div>
        );
      case 'operations':
        return (
          <div className="fields-grid">
            <FieldGroup label="Revenue" />
            <NumericField label="Gross Potential Rent (Annual)" value={inputs.operational.gross_potential_rent_annual} onChange={(v) => patchOp('gross_potential_rent_annual', v)} placeholder="600,000" prefix="$" citation={getCitation('gross_potential_rent_annual')} onOpenSource={handleOpenSource} />
            <NumericField label="Avg Current Rent / Door / Mo" value={inputs.operational.avg_in_place_rent_per_unit_monthly} onChange={(v) => patchOp('avg_in_place_rent_per_unit_monthly', v)} placeholder="115" prefix="$" citation={getCitation('avg_in_place_rent_per_unit_monthly')} onOpenSource={handleOpenSource} />
            <NumericField label="Avg Market Rent / Door / Mo" value={inputs.operational.avg_market_rent_per_unit_monthly} onChange={(v) => patchOp('avg_market_rent_per_unit_monthly', v)} placeholder="132" prefix="$" citation={getCitation('avg_market_rent_per_unit_monthly')} onOpenSource={handleOpenSource} />
            <NumericField label="Other Income (Annual)" value={inputs.operational.other_income_annual} onChange={(v) => patchOp('other_income_annual', v)} placeholder="0" prefix="$" citation={getCitation('other_income_annual')} onOpenSource={handleOpenSource} />
            <NumericField label="Vacancy & Credit Loss" value={inputs.operational.vacancy_credit_loss_pct} onChange={(v) => patchOp('vacancy_credit_loss_pct', v)} placeholder="10" suffix="%" citation={getCitation('vacancy_credit_loss_pct')} onOpenSource={handleOpenSource} />
            <NumericField label="Current Expense Ratio" value={inputs.operational.expense_ratio_current} onChange={(v) => patchOp('expense_ratio_current', v)} placeholder="41" suffix="%" citation={getCitation('expense_ratio_current')} onOpenSource={handleOpenSource} />
            <NumericField label="Pro Forma Expense Ratio" value={inputs.operational.expense_ratio_pro_forma} onChange={(v) => patchOp('expense_ratio_pro_forma', v)} placeholder="34" suffix="%" citation={getCitation('expense_ratio_pro_forma')} onOpenSource={handleOpenSource} />
            <NumericField label="Bad Debt (Annual)" value={inputs.operational.bad_debt_annual} onChange={(v) => patchOp('bad_debt_annual', v)} placeholder="0" prefix="$" citation={getCitation('bad_debt_annual')} onOpenSource={handleOpenSource} />
            <NumericField label="Corrections / Collections" value={inputs.operational.corrections_collections_annual} onChange={(v) => patchOp('corrections_collections_annual', v)} placeholder="0" prefix="$" citation={getCitation('corrections_collections_annual')} onOpenSource={handleOpenSource} />
            <NumericField label="Rent Growth" value={inputs.operational.rent_growth_pct} onChange={(v) => patchOp('rent_growth_pct', v)} placeholder="3" suffix="%" citation={getCitation('rent_growth_pct')} onOpenSource={handleOpenSource} />
            <FieldGroup label="Operating Expenses" />
            <NumericField label="Property Tax (Annual)" value={inputs.operational.property_tax_annual} onChange={(v) => patchOp('property_tax_annual', v)} placeholder="0" prefix="$" citation={getCitation('property_tax_annual')} onOpenSource={handleOpenSource} />
            <NumericField label="Property Tax Growth" value={inputs.operational.property_tax_growth_pct} onChange={(v) => patchOp('property_tax_growth_pct', v)} placeholder="4" suffix="%" citation={getCitation('property_tax_growth_pct')} onOpenSource={handleOpenSource} />
            <NumericField label="Mil Rate" value={inputs.operational.mil_rate} onChange={(v) => patchOp('mil_rate', v)} placeholder="28.5" suffix="mills" citation={getCitation('mil_rate')} onOpenSource={handleOpenSource} />
            <NumericField label="Insurance (Annual)" value={inputs.operational.insurance_annual} onChange={(v) => patchOp('insurance_annual', v)} placeholder="0" prefix="$" citation={getCitation('insurance_annual')} onOpenSource={handleOpenSource} />
            <NumericField label="Mgmt Fee" value={inputs.operational.mgmt_fee_pct} onChange={(v) => patchOp('mgmt_fee_pct', v)} placeholder="8" suffix="%" citation={getCitation('mgmt_fee_pct')} onOpenSource={handleOpenSource} />
            <NumericField label="Payroll (Annual)" value={inputs.operational.payroll_annual} onChange={(v) => patchOp('payroll_annual', v)} placeholder="0" prefix="$" citation={getCitation('payroll_annual')} onOpenSource={handleOpenSource} />
            <NumericField label="Repairs & Maintenance" value={inputs.operational.repairs_maintenance_annual} onChange={(v) => patchOp('repairs_maintenance_annual', v)} placeholder="0" prefix="$" citation={getCitation('repairs_maintenance_annual')} onOpenSource={handleOpenSource} />
            <NumericField label="Utilities (Annual)" value={inputs.operational.utilities_annual} onChange={(v) => patchOp('utilities_annual', v)} placeholder="0" prefix="$" citation={getCitation('utilities_annual')} onOpenSource={handleOpenSource} />
            <NumericField label="Marketing (Annual)" value={inputs.operational.marketing_annual} onChange={(v) => patchOp('marketing_annual', v)} placeholder="0" prefix="$" citation={getCitation('marketing_annual')} onOpenSource={handleOpenSource} />
            <NumericField label="Other OpEx (Annual)" value={inputs.operational.other_opex_annual} onChange={(v) => patchOp('other_opex_annual', v)} placeholder="0" prefix="$" citation={getCitation('other_opex_annual')} onOpenSource={handleOpenSource} />
            <NumericField label="OpEx Growth" value={inputs.operational.opex_growth_pct} onChange={(v) => patchOp('opex_growth_pct', v)} placeholder="2" suffix="%" citation={getCitation('opex_growth_pct')} onOpenSource={handleOpenSource} />

            <div className="col-span-full">
              <button
                type="button"
                onClick={() => setShowValueAdd((v) => !v)}
                className="flex w-full items-center gap-2 rounded-xl border border-border/60 bg-muted/40 px-3 py-2 text-left text-xs font-semibold uppercase tracking-[0.15em] text-muted-foreground transition-colors hover:bg-muted/70"
              >
                {showValueAdd ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
                Value-Add Evidence
                {getCitation('physical_occupancy_pct') || getCitation('below_market_tenant_pct') ? (
                  <span className="ml-auto flex items-center gap-1 text-uw-citation normal-case tracking-normal">
                    <Sparkles className="h-3 w-3" />
                    AI extracted
                  </span>
                ) : null}
              </button>
            </div>

            {showValueAdd ? (
              <ValueAddEvidence
                omData={currentRun?.result_artifact?.om_data ?? {}}
                getCitation={getCitation}
                onOpenSource={handleOpenSource}
              />
            ) : null}

            <OperationsWarnings inputs={inputs} currentRun={currentRun} />
          </div>
        );
      case 'market':
        return (
          <div className="fields-grid">
            <FieldGroup label="Nearby Facilities" />
            <NumericField label="Nearby Storage Facilities (1 mi)" value={projectData.nearby_storage_count_1mi} onChange={(v) => patchProject('nearby_storage_count_1mi', v)} citation={getCitation('nearby_storage_count_1mi')} onOpenSource={handleOpenSource} />
            <NumericField label="Nearby Storage Facilities (3 mi)" value={projectData.nearby_storage_count_3mi} onChange={(v) => patchProject('nearby_storage_count_3mi', v)} citation={getCitation('nearby_storage_count_3mi')} onOpenSource={handleOpenSource} />
            <NumericField label="Nearby Storage Facilities (5 mi)" value={projectData.nearby_storage_count_5mi} onChange={(v) => patchProject('nearby_storage_count_5mi', v)} citation={getCitation('nearby_storage_count_5mi')} onOpenSource={handleOpenSource} />
            <FieldGroup label="Demographics" />
            <NumericField label="Population (3 mi)" value={projectData.population_3mi} onChange={(v) => patchProject('population_3mi', v)} citation={getCitation('population_3mi')} onOpenSource={handleOpenSource} />
            <NumericField label="Avg Household Income (3 mi)" value={projectData.avg_household_income_3mi} onChange={(v) => patchProject('avg_household_income_3mi', v)} prefix="$" citation={getCitation('avg_household_income_3mi')} onOpenSource={handleOpenSource} />
            <NumericField label="Storage Sq Ft / Capita" value={projectData.storage_sqft_per_capita_3mi} onChange={(v) => patchProject('storage_sqft_per_capita_3mi', v)} suffix="sqft" citation={getCitation('storage_sqft_per_capita_3mi')} onOpenSource={handleOpenSource} />
            <FieldGroup label="Tight Comp Set" />
            <div className={`xl:col-span-2 rounded-2xl border p-4 ${rentCompsCitation ? 'border-green-500/40 bg-green-500/5' : 'border-border/60 bg-background/60'}`}>
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-sm font-semibold text-foreground">Nearby rent comps</p>
                    {rentCompsCitation ? <Sparkles className="h-3.5 w-3.5 text-uw-citation" /> : null}
                    {rentCompsCitation ? <span className="text-[11px] font-medium uppercase tracking-[0.16em] text-uw-citation">AI extracted</span> : null}
                  </div>
                  <p className="mt-1 text-sm text-muted-foreground">Add your tight comp set manually, or review rows extracted from OM competitive-set tables.</p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  {rentCompsCitation ? (
                    <Button type="button" variant="ghost" size="sm" className="h-8 rounded-full px-3 text-[11px] font-semibold text-uw-citation hover:bg-background/70" onClick={() => handleOpenSource(rentCompsCitation)}>
                      Source
                    </Button>
                  ) : null}
                  <Button type="button" variant="outline" size="sm" className="gap-2" onClick={addRentComp}>
                    <Plus className="h-4 w-4" />
                    Add comp
                  </Button>
                </div>
              </div>

              {(inputs.rent_comps || []).length > 0 ? (
                <div className="mt-4 overflow-x-auto">
                  <table className="w-full min-w-[1120px] text-sm">
                    <colgroup>
                      <col className="w-[180px]" />
                      <col className="w-[180px]" />
                      <col className="w-[120px]" />
                      <col className="w-[120px]" />
                      <col className="w-[120px]" />
                      <col className="w-[320px]" />
                      <col className="w-[72px]" />
                    </colgroup>
                    <thead>
                      <tr className="border-b border-border/70 text-left text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                        <th className="pb-3">Facility</th>
                        <th className="pb-3">Size</th>
                        <th className="pb-3 text-right">Rent/Unit</th>
                        <th className="pb-3 text-right">Rent/Sq Ft</th>
                        <th className="pb-3 text-right">Distance</th>
                        <th className="pb-3">Notes</th>
                        <th className="pb-3 text-right">Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(inputs.rent_comps || []).map((row, index) => (
                        <tr key={`rent-comp-${index}`} className="border-b border-border/50 align-top last:border-b-0">
                          <td className="py-3 pr-3">
                            <Input value={row.facility ?? ''} onChange={(e) => patchRentComp(index, 'facility', e.target.value)} className="h-9" />
                          </td>
                          <td className="py-3 pr-3">
                            <Input value={row.size ?? ''} onChange={(e) => patchRentComp(index, 'size', e.target.value)} className="h-9" />
                          </td>
                          <td className="py-3 pr-3">
                            <Input type="number" value={row.asking_rent ?? ''} onChange={(e) => patchRentComp(index, 'asking_rent', e.target.value === '' ? '' : parseFloat(e.target.value) || '')} className="h-9 text-right" />
                          </td>
                          <td className="py-3 pr-3">
                            <Input type="number" value={row.rent_per_sqft ?? ''} onChange={(e) => patchRentComp(index, 'rent_per_sqft', e.target.value === '' ? '' : parseFloat(e.target.value) || '')} className="h-9 text-right" />
                          </td>
                          <td className="py-3 pr-3">
                            <Input type="number" value={row.distance_mi ?? ''} onChange={(e) => patchRentComp(index, 'distance_mi', e.target.value === '' ? '' : parseFloat(e.target.value) || '')} className="h-9 text-right" />
                          </td>
                          <td className="py-3 pr-3 align-top">
                            <Textarea value={row.notes ?? ''} onChange={(e) => patchRentComp(index, 'notes', e.target.value)} className="min-h-[92px] min-w-[320px] resize-y leading-5" />
                          </td>
                          <td className="py-3 text-right">
                            <Button type="button" variant="ghost" size="icon" onClick={() => removeRentComp(index)} title="Remove comp">
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="mt-4 rounded-2xl border border-dashed border-border/70 bg-background/40 p-4 text-sm text-muted-foreground">
                  No rent comps yet. Add a tight comp set manually or run OM extraction on a package with a competitive-set table.
                </div>
              )}
            </div>
          </div>
        );
      case 'debtExit':
        return (
          <div className="fields-grid">
            <FieldGroup label="Debt" />
            <NumericField label="Interest Rate" value={inputs.financing.interest_rate_pct} onChange={(v) => patchFin('interest_rate_pct', v)} suffix="%" citation={getCitation('interest_rate_pct')} onOpenSource={handleOpenSource} />
            <NumericField label="Loan Term" value={inputs.financing.loan_term_years} onChange={(v) => patchFin('loan_term_years', v)} suffix="yrs" citation={getCitation('loan_term_years')} onOpenSource={handleOpenSource} />
            <NumericField label="Amortization" value={inputs.financing.amortization_years} onChange={(v) => patchFin('amortization_years', v)} suffix="yrs" citation={getCitation('amortization_years')} onOpenSource={handleOpenSource} />
            <NumericField label="LTV" value={inputs.financing.ltv_pct} onChange={(v) => patchFin('ltv_pct', v)} suffix="%" citation={getCitation('ltv_pct')} onOpenSource={handleOpenSource} />
            <div className="xl:col-span-2 rounded-2xl border border-border/60 bg-background/60 p-3 text-sm text-muted-foreground">
              Debt sizing is derived from purchase price and LTV in the current model. Loan amount is not edited separately.
            </div>
            <FieldGroup label="Exit" />
            <NumericField label="Hold Period" value={inputs.exit.hold_period_years} onChange={(v) => patchExit('hold_period_years', v)} suffix="yrs" citation={getCitation('hold_period_years')} onOpenSource={handleOpenSource} />
            <NumericField label="Market Cap Rate Sale" value={inputs.exit.market_cap_rate_sale} onChange={(v) => patchExit('market_cap_rate_sale', v)} suffix="%" citation={getCitation('market_cap_rate_sale')} onOpenSource={handleOpenSource} />
            <NumericField label="Exit Cap Rate" value={inputs.exit.exit_cap_rate} onChange={(v) => patchExit('exit_cap_rate', v)} suffix="%" citation={getCitation('exit_cap_rate')} onOpenSource={handleOpenSource} />
            <NumericField label="Selling Cost" value={inputs.exit.selling_cost_pct} onChange={(v) => patchExit('selling_cost_pct', v)} suffix="%" citation={getCitation('selling_cost_pct')} onOpenSource={handleOpenSource} />
          </div>
        );
      case 'criteria':
        return (
          <div className="fields-grid">
            <FieldGroup label="Return Thresholds" />
            <NumericField label="Target IRR" value={inputs.criteria.target_irr} onChange={(v) => patchCrit('target_irr', v)} suffix="%" citation={getCitation('target_irr')} onOpenSource={handleOpenSource} />
            <NumericField label="Target Cash-on-Cash" value={inputs.criteria.target_cash_on_cash} onChange={(v) => patchCrit('target_cash_on_cash', v)} suffix="%" citation={getCitation('target_cash_on_cash')} onOpenSource={handleOpenSource} />
            <NumericField label="Target Equity Multiple" value={inputs.criteria.target_equity_multiple} onChange={(v) => patchCrit('target_equity_multiple', v)} suffix="×" citation={getCitation('target_equity_multiple')} onOpenSource={handleOpenSource} />
            <NumericField label="Max LTV" value={inputs.criteria.max_ltv} onChange={(v) => patchCrit('max_ltv', v)} suffix="%" citation={getCitation('max_ltv')} onOpenSource={handleOpenSource} />
          </div>
        );
      default:
        return null;
    }
  };

  return (
    <>
      <section className="uw-wizard-stage">
        <div className="uw-wizard-stage-head">
          <div className="uw-wizard-stage-scroll">
            <div className="uw-wizard-stage-tabs" role="tablist" aria-label="Underwriting sections">
              {TAB_CONFIG.map((tab) => {
                const pct = tabProgress[tab.id] ?? 0;
                const isActive = tab.id === activeTab;

                return (
                  <button
                    key={tab.id}
                    type="button"
                    role="tab"
                    aria-selected={isActive}
                    className={`uw-wizard-stage-tab${isActive ? ' is-active' : ''}`}
                    onClick={() => setActiveTab(tab.id)}
                  >
                    <span className="uw-wizard-stage-label">{tab.label}</span>
                    <span className="uw-wizard-stage-desc">{tab.desc}</span>
                    <div className="uw-wizard-stage-meter" aria-hidden="true">
                      <div
                        className="uw-wizard-stage-meter-fill"
                        data-complete={pct === 100 ? 'true' : undefined}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          <div className="uw-wizard-stage-meta">
            <div className="uw-wizard-confidence">
              <span className="uw-wizard-confidence-label">AI confidence</span>
              {[
                ['hsl(var(--uw-success))', '≥90%'],
                ['hsl(var(--uw-risk))', '70–89%'],
                ['hsl(var(--uw-danger))', '<70%'],
              ].map(([color, label]) => (
                <span key={label} className="uw-wizard-confidence-band">
                  <span style={{ background: color }} className="uw-wizard-confidence-band-dot" />
                  {label}
                </span>
              ))}
            </div>
            <span className="uw-wizard-stage-status">
              {citationCount > 0 ? `${citationCount} fields cited` : 'Manual draft'}
              {' · '}
              {extractionDone ? 'AI extracted' : anyDocSelected ? 'Docs attached' : 'Awaiting docs'}
            </span>
          </div>
        </div>

        <div className="uw-wizard-stage-body animate-fade-in">
          <div className="uw-wizard-stage-copy">
            <p className="uw-wizard-stage-kicker">Current section</p>
            <h2 className="uw-wizard-stage-title">{TAB_CONFIG[activeTabIndex]?.label}</h2>
            <p className="uw-wizard-stage-summary">{TAB_CONFIG[activeTabIndex]?.desc}</p>
          </div>

          {renderActiveTabPanel()}
        </div>
      </section>

      <div className="underwriting-action-bar mt-6">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-end gap-4">
            {TAB_CONFIG.map((t) => {
              const pct = tabProgress[t.id] ?? 0;
              return (
                <div
                  key={t.id}
                  className="flex cursor-pointer flex-col gap-1"
                  onClick={() => setActiveTab(t.id)}
                >
                  <span className={`text-[10px] font-semibold ${t.id === activeTab ? 'text-foreground' : 'text-muted-foreground/60'}`}>
                    {t.label}
                  </span>
                  <div className="uw-tab-progress-bar">
                    <div
                      className="uw-tab-progress-fill"
                      data-complete={pct === 100 ? 'true' : undefined}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
          <div className="flex flex-col gap-2 sm:flex-row">
            {(currentRun?.status === 'completed' || runIdFromUrl) ? (
              <Button variant="outline" onClick={navigateToResults} className="gap-2">
                <BarChart2 className="h-4 w-4" />
                View results
              </Button>
            ) : (
              <Button
                variant="outline"
                onClick={() => {
                  const idx = TAB_CONFIG.findIndex((t) => t.id === activeTab);
                  if (idx < TAB_CONFIG.length - 1) setActiveTab(TAB_CONFIG[idx + 1].id);
                }}
                disabled={activeTab === TAB_CONFIG[TAB_CONFIG.length - 1].id}
              >
                Next section
                <ArrowRight className="ml-1.5 h-4 w-4" />
              </Button>
            )}
            <Button onClick={handleSaveAndCalculate} disabled={isSubmitting || !projectData.name.trim()} className="gap-2">
              {isSubmitting ? <><Loader2 className="h-4 w-4 animate-spin" />Saving...</> : <><TrendingUp className="h-4 w-4" />Save & calculate</>}
            </Button>
          </div>
        </div>
      </div>
    </>
  );
}
