# Underwriting Wizard UI Enhancement — Design Spec
**Date:** 2026-04-22
**Scope:** `UnderwritingWizard.jsx` visual layer only — no logic, state, or API changes.
**Reference:** `CRE Underwriting v2.html` prototype (Claude Design handoff)

---

## Overview

Enhance the visual design of the Underwriting Wizard (Inputs screen) to match the Claude Design prototype. Three areas of change: tab bar, left rail, and numeric field inputs. All functionality, state management, and API calls are preserved exactly.

---

## Section 1 — Tab Bar

### Goal
Replace the horizontal-scrolling tab bar with a 5-column grid where all tabs are always visible. Each tab shows a bold label and a description line. Active tab gets a white card background + shadow. Add a confidence legend and a tab progress row in the action bar.

### CSS additions to `index.css`

```css
/* 5-column tab grid */
.uw-tabs-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 4px;
  padding: 5px;
  border-radius: 18px;
  border: 1px solid hsl(var(--border) / 0.55);
  background: hsl(var(--card) / 0.72);
}

/* Individual tab button */
.uw-tab-btn {
  border: none;
  background: transparent;
  cursor: pointer;
  border-radius: 13px;
  padding: 10px 12px;
  text-align: left;
  color: hsl(var(--muted-foreground));
  transition: all 0.15s;
}
.uw-tab-btn:hover {
  background: hsl(var(--muted) / 0.6);
}
.uw-tab-btn[data-state="active"] {
  background: linear-gradient(180deg, hsl(var(--card)), hsl(var(--muted)));
  box-shadow: inset 0 1px 0 hsl(0 0% 100% / 0.7), 0 4px 12px -6px hsl(var(--foreground) / 0.18);
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

/* Tab progress bar (action bar) */
.uw-tab-progress-bar {
  height: 3px;
  border-radius: 2px;
  background: hsl(var(--muted));
  overflow: hidden;
}
.uw-tab-progress-fill {
  height: 100%;
  border-radius: 2px;
  background: hsl(var(--primary));
  transition: width 0.3s;
}
```

### JSX changes in `UnderwritingWizard.jsx`

- Replace `<TabsList className="underwriting-tabs inline-flex ...">` with `<TabsList className="uw-tabs-grid w-full">`.
- Replace `<TabsTrigger ... className="underwriting-tab-trigger min-w-[220px] ...">` with `<TabsTrigger className="uw-tab-btn" ...>`.
- Each trigger renders: `<span className="uw-tab-label">{tab.label}</span>` + `<span className="uw-tab-desc">{tab.desc}</span>`.
- Remove `overflow-x-auto pb-1` wrapper div (no longer needed).
- Add confidence legend row below the tab grid:
  ```jsx
  <div className="flex items-center gap-3 px-1 py-2 text-[10px] text-muted-foreground">
    <span>AI confidence:</span>
    {[['var(--success)', '≥90%'], ['var(--warning)', '70–89%'], ['var(--destructive)', '<70%']].map(([c, l]) => (
      <span key={l} className="flex items-center gap-1">
        <span style={{ background: `hsl(${c})` }} className="inline-block h-1.5 w-1.5 rounded-full" />
        {l}
      </span>
    ))}
    <span className="ml-auto font-semibold text-uw-citation">
      {citationCount > 0 ? `${citationCount} fields cited · AI extracted` : ''}
    </span>
  </div>
  ```
- In the action bar, replace the tab-name/description text block with a mini progress row (5 bars, one per tab, clicking jumps to that tab). Tab completion % = non-empty fields / total fields in that tab (computed client-side, approximate).

---

## Section 2 — Left Rail

### Goal
Move the collapse toggle into the rail header. Add an AI stats footer. Compact doc cards slightly.

### CSS additions to `index.css`

```css
/* Rail container */
.doc-rail {
  display: flex;
  flex-direction: column;
  border-right: 1px solid hsl(var(--border));
  background: hsl(var(--card));
  overflow: hidden;
  transition: width 0.2s, min-width 0.2s;
}

/* Rail header */
.doc-rail-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  border-bottom: 1px solid hsl(var(--border));
  flex-shrink: 0;
}

/* AI stats footer */
.doc-rail-footer {
  display: flex;
  gap: 16px;
  padding: 10px 14px;
  border-top: 1px solid hsl(var(--border));
  flex-shrink: 0;
}
.doc-rail-stat-val {
  font-size: 16px;
  font-weight: 700;
  font-family: var(--font-display);
  letter-spacing: -0.02em;
  line-height: 1;
}
.doc-rail-stat-label {
  font-size: 9px;
  color: hsl(var(--muted-foreground));
  letter-spacing: 0.04em;
  text-transform: uppercase;
  margin-top: 1px;
}
```

### JSX changes in `WorkflowRail`

- Add a proper header row at the top of the rail `<div>`:
  ```jsx
  <div className="doc-rail-header">
    <span className="text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
      Source Docs
    </span>
    <button onClick={() => setLeftCollapsed(v => !v)} className="...chevron button...">
      <ChevronLeft/Right />
    </button>
  </div>
  ```
- Remove the floating absolute-positioned collapse toggle from the parent layout.
- Doc cards: reduce padding from `p-3.5` to `p-3`. Replace the "Attached" full pill with a small checkmark icon (`CheckCircle2` h-3.5 w-3.5 text-success).
- Add AI stats footer at the bottom (only when `!leftCollapsed`):
  ```jsx
  <div className="doc-rail-footer">
    <div>
      <div className="doc-rail-stat-val text-primary">{citationCount}</div>
      <div className="doc-rail-stat-label">Cited fields</div>
    </div>
    <div>
      <div className="doc-rail-stat-val text-uw-citation">
        {Object.values(selectedDocs).filter(Boolean).length}/3
      </div>
      <div className="doc-rail-stat-label">Docs attached</div>
    </div>
    {extractionDone && (
      <div>
        <div className="doc-rail-stat-val text-success">Ready</div>
        <div className="doc-rail-stat-label">Extraction</div>
      </div>
    )}
  </div>
  ```
- When collapsed: rail shows only stacked document icons (one per slot) with active indicator on left edge.

---

## Section 3 — NumericField Prefix/Suffix Affixes

### Goal
Prefix (e.g. `$`) and suffix (e.g. `%`, `yrs`) render inside a shared border wrapper, visually connected to the input. Cited state applies to the wrapper, not just the input element.

### CSS additions to `index.css`

```css
/* Connected field row */
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
  background: hsl(var(--muted) / 0.6);
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
  font-family: var(--font-mono, monospace);
  color: hsl(var(--foreground));
  background: transparent;
  min-width: 0;
}
/* Remove browser number spinners */
.uw-field-input::-webkit-inner-spin-button { -webkit-appearance: none; }
.uw-field-input[type=number] { -moz-appearance: textfield; }
```

### JSX changes in `NumericField`

Replace current implementation:
```jsx
// BEFORE
<div className="flex w-full items-center gap-2">
  <Input type="number" value={...} className={`h-10 bg-background/80 ${citation ? 'border-green-500/60 ...' : '...'}`} />
  {suffix ? <span className="min-w-[42px] ...">{suffix}</span> : null}
</div>

// AFTER
<div className="uw-field-row" data-cited={!!citation}>
  {prefix ? <span className="uw-field-affix uw-field-affix-prefix">{prefix}</span> : null}
  <input
    type="number"
    className="uw-field-input"
    value={value ?? ''}
    onChange={...}
    onWheel={e => e.currentTarget.blur()}
    placeholder={placeholder}
  />
  {suffix ? <span className="uw-field-affix uw-field-affix-suffix">{suffix}</span> : null}
</div>
```

Note: `NumericField` currently receives `suffix` but not `prefix`. Add `prefix` prop to the component signature. Update all call sites that need a `$` prefix (purchase price, gross rent, etc.) to pass `prefix="$"` and remove the `suffix="$"` workaround where applicable.

---

## Files Changed

| File | Change |
|------|--------|
| `frontend/src/index.css` | Add CSS classes for all three sections |
| `frontend/src/verticals/real_estate/pages/UnderwritingWizard.jsx` | Update JSX for tabs, rail, fields |

No other files touched. No logic, state, routing, or API changes.

---

## Constraints

- Use only `index.css` CSS variables and `tailwind.config.js` tokens — no raw hex or hardcoded colors.
- No new npm packages.
- All existing functionality (extraction, citation flow, collapse, save & calculate) preserved.
- Mobile layout unchanged — rail stays `hidden lg:flex`.
