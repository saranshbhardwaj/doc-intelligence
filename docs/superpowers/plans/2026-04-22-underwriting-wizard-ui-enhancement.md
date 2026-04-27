# Underwriting Wizard UI Enhancement — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enhance the visual layer of `UnderwritingWizard.jsx` to match the Claude Design prototype — 5-column tab grid, compact left rail with collapse toggle in header and AI stats footer, and connected prefix/suffix field inputs.

**Architecture:** All changes are CSS + JSX presentation layer only. No state, logic, routing, or API changes. New CSS classes are added to `index.css` inside the existing `@layer components` block. `UnderwritingWizard.jsx` JSX is restructured in-place.

**Tech Stack:** React, Tailwind CSS, `index.css` CSS variables (`--uw-*`, `--success`, `--warning`, `--uw-citation`, `--uw-risk`, `--uw-danger`), lucide-react icons.

---

## File Map

| File | Change |
|------|--------|
| `frontend/src/index.css` | Add `.uw-tabs-grid`, `.uw-tab-btn`, `.uw-tab-desc`, `.uw-tab-progress-bar`, `.uw-tab-progress-fill`, `.doc-rail-header`, `.doc-rail-footer`, `.doc-rail-stat-val`, `.doc-rail-stat-label`, `.uw-field-row`, `.uw-field-affix`, `.uw-field-affix-prefix`, `.uw-field-affix-suffix`, `.uw-field-input` |
| `frontend/src/verticals/real_estate/pages/UnderwritingWizard.jsx` | Tab bar JSX, confidence legend, action bar progress row, `WorkflowRail` header/footer, collapse toggle move, `DocCard` compact, `NumericField` prefix/suffix |

---

## Task 1: Tab bar CSS

**Files:**
- Modify: `frontend/src/index.css` (inside the existing `@layer components { }` block, after `.underwriting-action-bar`)

- [ ] **Step 1: Add tab grid CSS**

Find the closing brace of `.underwriting-action-bar` (around line 1101) and insert the following immediately after it, still inside `@layer components`:

```css
  /* ── Underwriting tab grid ───────────────────────────────── */
  .uw-tabs-grid {
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 4px;
    padding: 5px;
    border-radius: 18px;
    border: 1px solid hsl(var(--shell-border) / 0.55);
    background: hsl(var(--card) / 0.72);
  }

  .uw-tab-btn {
    border: none;
    background: transparent;
    cursor: pointer;
    border-radius: 13px;
    padding: 10px 12px;
    text-align: left;
    color: hsl(var(--muted-foreground));
    transition: all 0.15s;
    font-family: inherit;
    width: 100%;
  }
  .uw-tab-btn:hover {
    background: hsl(var(--muted) / 0.6);
  }
  .uw-tab-btn[data-state="active"] {
    background: linear-gradient(180deg, hsl(var(--card)), hsl(var(--surface-soft)));
    box-shadow:
      inset 0 1px 0 hsl(var(--border) / 0.22),
      0 4px 12px -6px hsl(var(--foreground) / 0.18);
    color: hsl(var(--foreground));
  }
  .uw-tab-label {
    display: block;
    font-size: 13px;
    font-weight: 600;
    line-height: 1.2;
  }
  .uw-tab-desc {
    display: block;
    font-size: 10px;
    color: hsl(var(--muted-foreground) / 0.7);
    margin-top: 2px;
    line-height: 1.35;
    font-weight: 400;
  }
  .uw-tab-btn[data-state="active"] .uw-tab-desc {
    color: hsl(var(--muted-foreground));
  }

  /* ── Tab progress bars (action bar) ─────────────────────── */
  .uw-tab-progress-bar {
    height: 3px;
    border-radius: 2px;
    background: hsl(var(--muted));
    overflow: hidden;
    width: 48px;
  }
  .uw-tab-progress-fill {
    height: 100%;
    border-radius: 2px;
    background: hsl(var(--primary));
    transition: width 0.3s;
  }
  .uw-tab-progress-fill[data-complete="true"] {
    background: hsl(var(--uw-success));
  }
```

- [ ] **Step 2: Commit CSS only**

```bash
git add frontend/src/index.css
git commit -m "style: add uw-tabs-grid and tab progress bar CSS classes"
```

---

## Task 2: Tab bar JSX

**Files:**
- Modify: `frontend/src/verticals/real_estate/pages/UnderwritingWizard.jsx`

- [ ] **Step 1: Add tab completion helper above `FieldGroup`**

Insert this function directly above the `FieldGroup` function definition (around line 188):

```jsx
function computeTabProgress(inputs, projectData) {
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
```

- [ ] **Step 2: Compute tab progress inside the component**

Inside `UnderwritingWizard`, just before the `inputTabs` const (around line 643), add:

```jsx
const tabProgress = computeTabProgress(inputs, projectData);
```

- [ ] **Step 3: Replace the TabsList block**

Find this block (around line 651–666):
```jsx
        <div className="overflow-x-auto pb-1">
          <TabsList className="underwriting-tabs inline-flex h-auto min-w-max flex-nowrap gap-2">
            {TAB_CONFIG.map((tab) => (
              <TabsTrigger
                key={tab.id}
                value={tab.id}
                className="underwriting-tab-trigger min-w-[220px] shrink-0 flex flex-col items-start text-left gap-1 px-3 py-2"
              >
                <span className="text-sm font-semibold">{tab.label}</span>
                <span className="block text-xs leading-5 text-muted-foreground whitespace-normal break-words line-clamp-2">
                  {tab.desc}
                </span>
              </TabsTrigger>
            ))}
          </TabsList>
        </div>
```

Replace with:
```jsx
        <TabsList className="uw-tabs-grid h-auto p-0 rounded-none border-none bg-transparent">
          {TAB_CONFIG.map((tab) => (
            <TabsTrigger
              key={tab.id}
              value={tab.id}
              className="uw-tab-btn"
            >
              <span className="uw-tab-label">{tab.label}</span>
              <span className="uw-tab-desc">{tab.desc}</span>
            </TabsTrigger>
          ))}
        </TabsList>
        {/* Confidence legend */}
        <div className="flex items-center gap-3 px-1 pt-2 pb-1 text-[10px] text-muted-foreground">
          <span>AI confidence:</span>
          {[
            ['hsl(var(--uw-success))', '≥90%'],
            ['hsl(var(--uw-risk))', '70–89%'],
            ['hsl(var(--uw-danger))', '<70%'],
          ].map(([color, label]) => (
            <span key={label} className="flex items-center gap-1">
              <span style={{ background: color }} className="inline-block h-1.5 w-1.5 rounded-full" />
              {label}
            </span>
          ))}
          {citationCount > 0 && (
            <span className="ml-auto font-semibold text-uw-citation">
              {citationCount} fields cited · AI extracted
            </span>
          )}
        </div>
```

- [ ] **Step 4: Replace action bar text block with tab progress row**

Inside the action bar (`<div className="underwriting-action-bar mt-6">`), find the `<div className="min-w-0">` block (around line 965–972):
```jsx
          <div className="min-w-0">
            <p className="text-sm font-semibold text-foreground">
              {TAB_CONFIG.find((tab) => tab.id === activeTab)?.label}
            </p>
            <p className="text-sm text-muted-foreground">
              {extractionDone
                ? 'AI-drafted values are highlighted so you can review them quickly before calculation.'
                : 'You can enter assumptions manually now and enrich them with AI extraction later.'}
            </p>
          </div>
```

Replace with:
```jsx
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
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/verticals/real_estate/pages/UnderwritingWizard.jsx
git commit -m "feat: replace scrollable tabs with 5-column grid, add confidence legend and action bar progress"
```

---

## Task 3: Left rail CSS

**Files:**
- Modify: `frontend/src/index.css` (inside `@layer components`, after the tab CSS from Task 1)

- [ ] **Step 1: Add doc rail CSS**

Append after the tab progress CSS added in Task 1:

```css
  /* ── Doc rail ────────────────────────────────────────────── */
  .doc-rail-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 14px;
    border-bottom: 1px solid hsl(var(--border) / 0.6);
    flex-shrink: 0;
  }
  .doc-rail-footer {
    display: flex;
    gap: 16px;
    padding: 10px 14px;
    border-top: 1px solid hsl(var(--border) / 0.6);
    flex-shrink: 0;
  }
  .doc-rail-stat-val {
    font-size: 16px;
    font-weight: 700;
    font-family: "Space Grotesk", "Instrument Sans", ui-sans-serif, sans-serif;
    letter-spacing: -0.02em;
    line-height: 1;
  }
  .doc-rail-stat-label {
    font-size: 9px;
    color: hsl(var(--muted-foreground));
    letter-spacing: 0.04em;
    text-transform: uppercase;
    margin-top: 2px;
  }
```

- [ ] **Step 2: Commit CSS**

```bash
git add frontend/src/index.css
git commit -m "style: add doc-rail header/footer CSS classes"
```

---

## Task 4: Left rail JSX restructure

**Files:**
- Modify: `frontend/src/verticals/real_estate/pages/UnderwritingWizard.jsx`

- [ ] **Step 1: Add `leftCollapsed` and `setLeftCollapsed` to `WorkflowRail` props**

Find the `WorkflowRail` function signature (around line 268):
```jsx
function WorkflowRail({
  selectedDocs,
  anyDocSelected,
  hasOmForExtraction,
  extraction,
  extractionDone,
  handleRunExtraction,
  isExtracting,
  projectName,
  currentRun,
  setDocPickerOpen,
  setSelectedDocs,
  citationCount,
}) {
```

Replace with:
```jsx
function WorkflowRail({
  selectedDocs,
  anyDocSelected,
  hasOmForExtraction,
  extraction,
  extractionDone,
  handleRunExtraction,
  isExtracting,
  projectName,
  currentRun,
  setDocPickerOpen,
  setSelectedDocs,
  citationCount,
  leftCollapsed,
  setLeftCollapsed,
}) {
```

- [ ] **Step 2: Replace `WorkflowRail` return with restructured JSX**

Replace the entire `return (...)` of `WorkflowRail` (lines 282–353) with:

```jsx
  const attachedCount = Object.values(selectedDocs).filter(Boolean).length;

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* Rail header with collapse toggle */}
      <div className="doc-rail-header">
        {!leftCollapsed && (
          <span className="text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
            Source Docs
          </span>
        )}
        <button
          onClick={() => setLeftCollapsed((v) => !v)}
          className="ml-auto flex h-7 w-7 items-center justify-center rounded-lg border border-border/50 bg-card text-muted-foreground shadow-sm transition-colors hover:bg-muted hover:text-foreground"
          title={leftCollapsed ? 'Expand panel' : 'Collapse panel'}
        >
          {leftCollapsed ? <ChevronRight className="h-3.5 w-3.5" /> : <ChevronLeft className="h-3.5 w-3.5" />}
        </button>
      </div>

      {leftCollapsed ? (
        /* Collapsed: icon-only stacked view */
        <div className="flex flex-col items-center py-2">
          {DOC_SLOTS.map((slot) => {
            const Icon = slot.icon;
            const attached = Boolean(selectedDocs[slot.key]);
            return (
              <button
                key={slot.key}
                onClick={() => setDocPickerOpen(slot.key)}
                title={slot.label}
                className={`flex h-10 w-full items-center justify-center border-l-2 transition-colors ${
                  attached
                    ? 'border-l-primary bg-primary/5 text-primary'
                    : 'border-l-transparent text-muted-foreground hover:bg-muted/50'
                }`}
              >
                <Icon className="h-4 w-4" />
              </button>
            );
          })}
        </div>
      ) : (
        /* Expanded: full rail */
        <>
          <div className="flex-1 overflow-y-auto">
            <UnderwritingSection
              eyebrow="Workflow"
              title="Source documents"
              description="Attach the materials you trust, then let AI draft the model inputs before you review them."
              className="rounded-none border-x-0 border-t-0 shadow-none"
            >
              <div className="space-y-2.5">
                {DOC_SLOTS.map((slot) => (
                  <DocCard
                    key={slot.key}
                    slot={slot}
                    selected={selectedDocs[slot.key]}
                    onOpen={() => setDocPickerOpen(slot.key)}
                    onRemove={() => setSelectedDocs((prev) => ({ ...prev, [slot.key]: null }))}
                    extracting={extraction.isProcessing}
                  />
                ))}
              </div>

              {extraction.isProcessing ? (
                <div className="underwriting-panel mt-3 border-primary/20 bg-primary/5 p-3">
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex items-center gap-2 text-sm font-medium text-primary">
                      <Loader2 className="h-4 w-4 animate-spin" />
                      {extraction.message || 'Extracting data'}
                    </div>
                    <span className="text-sm font-semibold text-primary">{extraction.progress || 0}%</span>
                  </div>
                  <Progress value={extraction.progress || 0} className="mt-2.5 h-1.5" />
                </div>
              ) : null}

              <div className="mt-3 rounded-2xl border border-border/60 bg-background/55 p-3.5">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">AI drafting</p>
                    <p className="mt-1 text-sm font-semibold text-foreground">
                      {extractionDone ? 'Inputs are ready for review' : 'Populate the model from source docs'}
                    </p>
                    <p className="mt-1 text-xs leading-5 text-muted-foreground">
                      {extractionDone
                        ? `${citationCount} field${citationCount === 1 ? '' : 's'} now carry source-backed citations.`
                        : 'Run extraction after selecting an OM and naming the deal.'}
                    </p>
                  </div>
                  {extractionDone
                    ? <CheckCircle2 className="mt-1 h-5 w-5 shrink-0 text-uw-success" />
                    : <Sparkles className="mt-1 h-5 w-5 shrink-0 text-primary" />}
                </div>

                <Button
                  onClick={handleRunExtraction}
                  disabled={isExtracting || !hasOmForExtraction || !projectName.trim()}
                  className="mt-3 w-full gap-2"
                  variant={extractionDone ? 'outline' : 'default'}
                >
                  <Sparkles className="h-4 w-4" />
                  {extractionDone ? 'Re-run extraction' : 'Extract with AI'}
                </Button>
              </div>
            </UnderwritingSection>

            {currentRun?.discrepancies?.length ? (
              <div className="space-y-2.5 px-4 pb-4">
                {currentRun.discrepancies.map((disc) => (
                  <DiscrepancyBanner key={disc.field} discrepancy={disc} />
                ))}
              </div>
            ) : null}
          </div>

          {/* AI stats footer */}
          <div className="doc-rail-footer">
            <div>
              <div className="doc-rail-stat-val text-primary">{citationCount}</div>
              <div className="doc-rail-stat-label">Cited fields</div>
            </div>
            <div>
              <div className="doc-rail-stat-val text-uw-citation">{attachedCount}/3</div>
              <div className="doc-rail-stat-label">Docs attached</div>
            </div>
            {extractionDone && (
              <div>
                <div className="doc-rail-stat-val text-uw-success">Ready</div>
                <div className="doc-rail-stat-label">Extraction</div>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
```

- [ ] **Step 3: Pass `leftCollapsed` and `setLeftCollapsed` to `WorkflowRail`**

Find the `<WorkflowRail` usage (around line 1077) and add the two new props:
```jsx
                    <WorkflowRail
                      selectedDocs={selectedDocs}
                      anyDocSelected={anyDocSelected}
                      hasOmForExtraction={hasOmForExtraction}
                      extraction={extraction}
                      extractionDone={extractionDone}
                      handleRunExtraction={handleRunExtraction}
                      isExtracting={isExtracting}
                      projectName={projectData.name}
                      currentRun={currentRun}
                      citationCount={citationCount}
                      setDocPickerOpen={setDocPickerOpen}
                      setSelectedDocs={setSelectedDocs}
                      leftCollapsed={leftCollapsed}
                      setLeftCollapsed={setLeftCollapsed}
                    />
```

- [ ] **Step 4: Remove the floating absolute collapse toggle from the parent layout**

Find and delete these lines (around line 1093–1102):
```jsx
                  {/* Collapse toggle button — floats on the left edge */}
                  <div className="absolute left-0 top-0 z-10 hidden lg:block" style={{ transform: leftCollapsed ? 'none' : 'translateX(320px)' }}>
                    <button
                      onClick={() => setLeftCollapsed((v) => !v)}
                      className="flex h-8 w-6 items-center justify-center rounded-r-lg border border-l-0 bg-card text-muted-foreground shadow-sm transition-colors hover:bg-muted hover:text-foreground"
                      title={leftCollapsed ? 'Expand panel' : 'Collapse panel'}
                    >
                      {leftCollapsed ? <ChevronRight className="h-3.5 w-3.5" /> : <ChevronLeft className="h-3.5 w-3.5" />}
                    </button>
                  </div>
```

- [ ] **Step 5: Update the rail width classes to include a collapsed icon-width state**

Find (around line 1076):
```jsx
                  <div className={`hidden lg:flex flex-shrink-0 flex-col overflow-hidden transition-all duration-300 ${leftCollapsed ? 'w-0' : 'w-[320px] xl:w-[340px]'}`}>
```

Replace with:
```jsx
                  <div className={`hidden lg:flex flex-shrink-0 flex-col overflow-hidden border-r border-border/60 bg-card transition-all duration-300 ${leftCollapsed ? 'w-[52px]' : 'w-[300px] xl:w-[320px]'}`}>
```

- [ ] **Step 6: Update `DocCard` padding from `p-3.5` to `p-3` and replace "Attached" pill with checkmark icon**

Find the `DocCard` function (around line 221). Change the top-level div:
```jsx
    <div className="underwriting-panel p-3.5">
```
to:
```jsx
    <div className="underwriting-panel p-3">
```

Then find the "Attached" badge line inside `DocCard`:
```jsx
            {selected ? <UnderwritingStatusBadge tone="success">Attached</UnderwritingStatusBadge> : null}
```
Replace with:
```jsx
            {selected ? <CheckCircle2 className="h-3.5 w-3.5 text-uw-success" /> : null}
```

- [ ] **Step 7: Commit**

```bash
git add frontend/src/index.css frontend/src/verticals/real_estate/pages/UnderwritingWizard.jsx
git commit -m "feat: restructure left rail — collapse toggle in header, AI stats footer, compact doc cards"
```

---

## Task 5: NumericField prefix/suffix CSS

**Files:**
- Modify: `frontend/src/index.css` (inside `@layer components`, after the doc rail CSS)

- [ ] **Step 1: Add connected field row CSS**

Append after the doc rail CSS added in Task 3:

```css
  /* ── Connected field row (prefix/suffix affixes) ─────────── */
  .uw-field-row {
    display: flex;
    align-items: center;
    border-radius: 10px;
    border: 1px solid hsl(var(--border) / 0.7);
    background: hsl(var(--background) / 0.8);
    overflow: hidden;
    transition: border-color 0.15s, box-shadow 0.15s;
  }
  .uw-field-row:focus-within {
    border-color: hsl(var(--primary));
    box-shadow: 0 0 0 3px hsl(var(--primary) / 0.12);
  }
  .uw-field-row[data-cited="true"] {
    border-color: hsl(var(--uw-citation) / 0.45);
    background: hsl(var(--uw-citation-soft));
    box-shadow: inset 3px 0 0 hsl(var(--uw-citation));
  }
  .uw-field-affix {
    padding: 0 10px;
    font-size: 12px;
    color: hsl(var(--muted-foreground));
    background: hsl(var(--muted) / 0.55);
    white-space: nowrap;
    height: 36px;
    display: flex;
    align-items: center;
    flex-shrink: 0;
  }
  .uw-field-affix-prefix {
    border-right: 1px solid hsl(var(--border) / 0.6);
  }
  .uw-field-affix-suffix {
    border-left: 1px solid hsl(var(--border) / 0.6);
  }
  .uw-field-input {
    flex: 1;
    border: none;
    outline: none;
    padding: 0 10px;
    height: 36px;
    font-size: 13px;
    font-family: "DM Mono", "Geist Mono", ui-monospace, monospace;
    color: hsl(var(--foreground));
    background: transparent;
    min-width: 0;
  }
  .uw-field-input::-webkit-inner-spin-button,
  .uw-field-input::-webkit-outer-spin-button {
    -webkit-appearance: none;
    margin: 0;
  }
  .uw-field-input[type="number"] {
    -moz-appearance: textfield;
  }
```

- [ ] **Step 2: Commit CSS**

```bash
git add frontend/src/index.css
git commit -m "style: add uw-field-row connected prefix/suffix field CSS"
```

---

## Task 6: NumericField component + call site prefix/suffix update

**Files:**
- Modify: `frontend/src/verticals/real_estate/pages/UnderwritingWizard.jsx`

- [ ] **Step 1: Rewrite the `NumericField` component**

Find the `NumericField` function (around line 198):
```jsx
function NumericField({ label, value, onChange, suffix, citation, onOpenSource, wide = false }) {
  return (
    <div className={wide ? 'xl:col-span-2' : ''}>
      <AIPrefilledField label={label} citation={citation} onOpenSource={onOpenSource}>
        <div className="flex w-full items-center gap-2">
          <Input
            type="number"
            value={value ?? ''}
            onChange={(e) => onChange(e.target.value === '' ? '' : parseFloat(e.target.value) || '')}
            onWheel={(e) => e.currentTarget.blur()}
            className={`h-10 bg-background/80 ${citation ? 'border-green-500/60 bg-green-500/5 focus-visible:ring-green-500/30' : 'border-border/70'}`}
          />
          {suffix ? (
            <span className="min-w-[42px] text-right text-xs font-semibold text-muted-foreground">
              {suffix}
            </span>
          ) : null}
        </div>
      </AIPrefilledField>
    </div>
  );
}
```

Replace with:
```jsx
function NumericField({ label, value, onChange, prefix, suffix, citation, onOpenSource, wide = false, placeholder }) {
  return (
    <div className={wide ? 'xl:col-span-2' : ''}>
      <AIPrefilledField label={label} citation={citation} onOpenSource={onOpenSource}>
        <div className="uw-field-row" data-cited={citation ? 'true' : undefined}>
          {prefix ? <span className="uw-field-affix uw-field-affix-prefix">{prefix}</span> : null}
          <input
            type="number"
            className="uw-field-input"
            value={value ?? ''}
            placeholder={placeholder}
            onChange={(e) => onChange(e.target.value === '' ? '' : parseFloat(e.target.value) || '')}
            onWheel={(e) => e.currentTarget.blur()}
          />
          {suffix ? <span className="uw-field-affix uw-field-affix-suffix">{suffix}</span> : null}
        </div>
      </AIPrefilledField>
    </div>
  );
}
```

- [ ] **Step 2: Update all dollar-amount call sites to use `prefix="$"` instead of `suffix="$"`**

These are all lines where `suffix="$"` is a dollar sign that belongs on the left. Make each replacement below. Use find-and-replace or edit them individually — each is a distinct field label so they are unambiguous.

| Label | Old | New |
|-------|-----|-----|
| Purchase Price | `suffix="$"` | `prefix="$"` |
| Gross Potential Rent (Annual) | `suffix="$"` | `prefix="$"` |
| Avg Current Rent / Door / Mo | `suffix="$"` | `prefix="$"` |
| Avg Market Rent / Door / Mo | `suffix="$"` | `prefix="$"` |
| Other Income (Annual) | `suffix="$"` | `prefix="$"` |
| Bad Debt (Annual) | `suffix="$"` | `prefix="$"` |
| Corrections / Collections | `suffix="$"` | `prefix="$"` |
| Property Tax (Annual) | `suffix="$"` | `prefix="$"` |
| Insurance (Annual) | `suffix="$"` | `prefix="$"` |
| Payroll (Annual) | `suffix="$"` | `prefix="$"` |
| Repairs & Maintenance | `suffix="$"` | `prefix="$"` |
| Utilities (Annual) | `suffix="$"` | `prefix="$"` |
| Marketing (Annual) | `suffix="$"` | `prefix="$"` |
| Other OpEx (Annual) | `suffix="$"` | `prefix="$"` |
| Avg Household Income (3 mi) | `suffix="$"` | `prefix="$"` |

- [ ] **Step 3: Fix CapEx Reserve / Unit to split into prefix + suffix**

Find:
```jsx
<NumericField label="CapEx Reserve / Unit" value={inputs.acquisition.capex_reserve_per_unit} onChange={(v) => patchAcq('capex_reserve_per_unit', v)} placeholder="0" suffix="$/unit" citation={getCitation('capex_reserve_per_unit')} onOpenSource={onOpenSource} />
```

Replace with:
```jsx
<NumericField label="CapEx Reserve / Unit" value={inputs.acquisition.capex_reserve_per_unit} onChange={(v) => patchAcq('capex_reserve_per_unit', v)} placeholder="0" prefix="$" suffix="/unit" citation={getCitation('capex_reserve_per_unit')} onOpenSource={onOpenSource} />
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/verticals/real_estate/pages/UnderwritingWizard.jsx
git commit -m "feat: NumericField connected prefix/suffix affixes with cited state on wrapper"
```

---

## Self-Review Notes

- **Spec coverage:** All three areas covered — tab grid ✓, confidence legend ✓, action bar progress ✓, rail header toggle ✓, rail footer stats ✓, collapsed icon view ✓, NumericField prefix/suffix ✓.
- **Token correctness:** `--uw-success`, `--uw-risk`, `--uw-danger`, `--uw-citation`, `--uw-citation-soft`, `--shell-border`, `--surface-soft` all confirmed present in `index.css`. Tailwind: `text-uw-citation`, `text-uw-success`, `text-primary` all confirmed in `tailwind.config.js`.
- **No floating toggle conflict:** Task 4 Step 4 explicitly removes the old floating toggle before the new in-header one is added in Step 2.
- **`Input` component removed from `NumericField`:** Replaced with a plain `<input>` styled via `uw-field-input`. The shadcn `Input` import is still used elsewhere in the file (rent comps table), so no import removal needed.
- **`computeTabProgress` is a pure function:** No hooks, no side effects — safe to define outside the component.
- **Collapsed rail width:** Changed from `w-0` (hidden) to `w-[52px]` (icon strip). The `overflow-hidden` on the wrapper clips the full-width content when collapsed.
