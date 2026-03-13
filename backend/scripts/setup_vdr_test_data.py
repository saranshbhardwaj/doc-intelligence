#!/usr/bin/env python3
"""
Set up VDR test data from MAUD contracts.

Creates:
- Base contracts (mixed formats: PDF, DOCX, TXT)
- Synthetic amendments
- Test documents (unclassified, service agreements)

Usage:
  python scripts/setup_vdr_test_data.py \
    --maud-dir "/path/to/maud/contracts" \
    --output-dir "/path/to/output"
"""

import os
import re
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict

# Optional: Only use these if installed
try:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.units import inch
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False

try:
    from docx import Document
    from docx.shared import Pt
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False


# ============================================================================
# Configuration
# ============================================================================

NUM_CONTRACTS = 12

# Create these amendments (indices into selected contracts)
AMENDMENTS_TO_CREATE = {
    0: [
        "amendment_1_coc_modification",      # Modify CoC clause
        "side_letter_restriction",            # Add assignment restriction
    ],
    3: [
        "amendment_1_supersedes",             # "AMENDED AND RESTATED"
    ],
    7: [
        "amendment_1_deletes_clause",         # Remove CoC clause
    ],
}

# Synthetic test documents
SYNTHETIC_DOCS = {
    "service_agreement.txt": """SERVICE AGREEMENT

This Service Agreement ("Agreement") is entered into as of the date hereof between SERVICE PROVIDER, INC. ("Provider") and CLIENT CORPORATION ("Client").

1. SERVICES
Provider agrees to provide consulting services as described in Schedule A.

2. TERM
This Agreement shall commence on the Effective Date and continue for a period of one (1) year.

3. CONFIDENTIALITY
Each party agrees to maintain the confidentiality of proprietary information.

4. ASSIGNMENT
Neither party may assign its rights or obligations under this Agreement without prior written consent of the other party.

5. GOVERNING LAW
This Agreement shall be governed by the laws of the State of Delaware.

EXECUTED as of the date first written above.
""",

    "financial_summary.txt": """FINANCIAL SUMMARY — FISCAL YEAR 2020

Company: Acme Corporation
Date: December 31, 2020

CONSOLIDATED BALANCE SHEET (in thousands)

ASSETS
Current Assets:
  Cash and Cash Equivalents          $15,234
  Accounts Receivable                $42,567
  Inventory                          $28,900
  Prepaid Expenses                    $3,421
  Total Current Assets               $90,122

Fixed Assets:
  Property and Equipment            $145,000
  Less: Accumulated Depreciation    ($45,000)
  Net Fixed Assets                  $100,000

TOTAL ASSETS                        $190,122

LIABILITIES AND EQUITY
Current Liabilities:
  Accounts Payable                   $12,345
  Short-term Debt                    $15,000
  Accrued Expenses                    $8,765
  Total Current Liabilities           $36,110

Long-term Debt                       $50,000

Shareholders' Equity:
  Common Stock                       $10,000
  Retained Earnings                  $84,012
  Total Equity                       $94,012

TOTAL LIABILITIES AND EQUITY        $190,122
""",

    "unknown_document.txt": """OPERATIONAL NOTICE

All staff are requested to attend the quarterly business review scheduled for March 15, 2024.

Key Topics:
- Q1 performance review
- 2024 strategic initiatives
- Team reorganization updates
- Budget allocation for new projects

Meeting Location: Conference Room A, Building 2
Time: 2:00 PM - 4:00 PM
Attendance: Mandatory

Please confirm your attendance by March 10.

For questions, contact the Operations team.
""",
}


# ============================================================================
# Helper Functions
# ============================================================================

def txt_to_pdf(txt_content: str, output_file: Path) -> bool:
    """Convert text content to PDF."""
    if not HAS_REPORTLAB:
        return False

    try:
        doc = SimpleDocTemplate(
            str(output_file),
            pagesize=letter,
            rightMargin=0.75*inch,
            leftMargin=0.75*inch,
            topMargin=0.75*inch,
            bottomMargin=0.75*inch,
        )

        styles = getSampleStyleSheet()
        body_style = ParagraphStyle(
            'CustomBody',
            parent=styles['Normal'],
            fontSize=9,
            leading=11,
            spaceAfter=6,
        )

        story = []
        paragraphs = txt_content.split('\n\n')

        for para_text in paragraphs:
            para_text = para_text.strip()
            if not para_text:
                continue
            para_text = para_text.replace('\n', ' ')
            try:
                para = Paragraph(para_text, body_style)
                story.append(para)
                story.append(Spacer(1, 0.05*inch))
            except Exception:
                continue

        doc.build(story)
        return True
    except Exception as e:
        print(f"      [ERROR] PDF conversion failed: {e}")
        return False


def txt_to_docx(txt_content: str, output_file: Path) -> bool:
    """Convert text content to DOCX."""
    if not HAS_DOCX:
        return False

    try:
        doc = Document()
        paragraphs = txt_content.split('\n\n')

        for para_text in paragraphs:
            para_text = para_text.strip()
            if not para_text:
                continue
            para = doc.add_paragraph(para_text)
            for run in para.runs:
                run.font.size = Pt(10)

        doc.save(str(output_file))
        return True
    except Exception as e:
        print(f"      [ERROR] DOCX conversion failed: {e}")
        return False


def create_amendment(contract_text: str, amendment_type: str) -> str:
    """Create a synthetic amendment based on type."""

    if amendment_type == "amendment_1_coc_modification":
        return f"""AMENDMENT NO. 1 TO AGREEMENT AND PLAN OF MERGER

EFFECTIVE DATE: {(datetime.now() + timedelta(days=30)).strftime('%B %d, %Y')}

WHEREAS, the parties to that certain Agreement and Plan of Merger dated January 14, 2021,
desire to amend such Agreement as follows:

AMENDMENT:
The parties hereby agree that any change of control provisions requiring Board consent are
hereby MODIFIED such that no consent shall be required for assignment or transfer of rights.

Any prior requirement for written consent in connection with change of control events is
hereby deleted and shall no longer apply.

The remaining terms and conditions of the original Agreement remain in full force and effect.

Executed as of the date hereof.
"""

    elif amendment_type == "side_letter_restriction":
        return f"""SIDE LETTER

DATE: {datetime.now().strftime('%B %d, %Y')}

RE: Restrictions on Assignment

Dear [Counterparty],

In addition to the existing terms of the Agreement and Plan of Merger dated January 14, 2021,
the parties agree to the following restrictions:

1. ASSIGNMENT RESTRICTIONS
   No party may assign, transfer, or delegate any rights or obligations under this Agreement
   without the prior written consent of the other party, which consent shall not be
   unreasonably withheld, conditioned, or delayed.

2. CHANGE OF CONTROL
   In the event of any change of control, material adverse change, or key personnel departure,
   the other party shall have the right to terminate this Agreement upon thirty (30) days'
   written notice.

3. NOTICE REQUIREMENTS
   All notices required under this Side Letter shall be in writing and delivered personally
   or via overnight courier.

This Side Letter shall be binding upon and inure to the benefit of the parties and their
respective successors and assigns.

Sincerely,

[Signature Block]
"""

    elif amendment_type == "amendment_1_supersedes":
        return f"""AMENDED AND RESTATED AGREEMENT AND PLAN OF MERGER

EFFECTIVE DATE: {datetime.now().strftime('%B %d, %Y')}

RECITALS:
WHEREAS, the parties entered into an Agreement and Plan of Merger dated January 14, 2021
("Original Agreement"); and

WHEREAS, the parties now desire to amend, restate, and supersede the Original Agreement
in its entirety as follows:

ARTICLE I: MERGER

1.1 The Merger
Subject to the terms and conditions of this Amended and Restated Agreement, and in accordance
with the applicable laws of the State of Delaware, at the Effective Time, Merger Sub shall
merge with and into the Company.

1.2 Effect of Merger
The Merger shall have the effects specified in the Delaware General Corporation Law.

1.3 Assignment Restrictions
Notwithstanding any prior version of this Agreement, all assignment restrictions previously
in effect are hereby CONFIRMED and shall remain binding.

The undersigned parties hereby acknowledge that this Amended and Restated Agreement supersedes
all prior agreements, understandings, and negotiations regarding the Merger.

Executed as of the date hereof.
"""

    elif amendment_type == "amendment_1_deletes_clause":
        return f"""AMENDMENT NO. 1 — DELETION OF CLAUSES

EFFECTIVE DATE: {datetime.now().strftime('%B %d, %Y')}

NOTICE OF DELETION:
The following clauses from the Agreement and Plan of Merger dated January 14, 2021, are
hereby DELETED and shall no longer be binding:

- All references to Change of Control requirements
- All sections requiring written consent for assignment
- All Board approval conditions

AMENDED LANGUAGE:
The Agreement is hereby amended to remove the above-referenced restrictions. All other
terms and conditions remain in full force and effect.

Except as expressly amended by this Amendment, all terms and conditions of the original
Agreement remain unchanged and in full force and effect.

Executed as of the date hereof.
"""

    else:
        return f"Unknown amendment type: {amendment_type}"


def save_document(content: str, base_name: str, output_subdir: Path,
                  formats: List[str] = None) -> List[Path]:
    """Save document in specified formats. Returns list of created files."""
    if formats is None:
        formats = ['txt', 'pdf', 'docx']

    created = []

    for fmt in formats:
        if fmt == 'txt':
            output_file = output_subdir / f"{base_name}.txt"
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(content)
            created.append(output_file)
            print(f"      [OK] {output_file.name}")

        elif fmt == 'pdf':
            output_file = output_subdir / f"{base_name}.pdf"
            if txt_to_pdf(content, output_file):
                created.append(output_file)
                print(f"      [OK] {output_file.name}")

        elif fmt == 'docx':
            output_file = output_subdir / f"{base_name}.docx"
            if txt_to_docx(content, output_file):
                created.append(output_file)
                print(f"      [OK] {output_file.name}")

    return created


# ============================================================================
# Main Setup
# ============================================================================

def main(maud_dir: Path, output_dir: Path):
    print("\n" + "="*70)
    print("[*] VDR TEST DATA SETUP")
    print("="*70)

    # Create output structure
    output_dir.mkdir(parents=True, exist_ok=True)
    contracts_dir = output_dir / "1_base_contracts"
    amendments_dir = output_dir / "2_amendments"
    synthetics_dir = output_dir / "3_test_documents"

    for d in [contracts_dir, amendments_dir, synthetics_dir]:
        d.mkdir(exist_ok=True)

    print(f"\n[INPUT]  {maud_dir}")
    print(f"[OUTPUT] {output_dir}")

    # ========================================================================
    # STEP 1: Select and copy base contracts
    # ========================================================================
    print(f"\n{'='*70}")
    print("STEP 1: Selecting base contracts from MAUD")
    print("="*70)

    txt_files = sorted(maud_dir.glob('contract_*.txt'))[:NUM_CONTRACTS]
    if not txt_files:
        print(f"[ERROR] No contracts found in {maud_dir}")
        return

    print(f"[OK] Selected {len(txt_files)} contracts\n")

    selected_contracts: Dict[int, str] = {}

    for i, txt_file in enumerate(txt_files, 1):
        print(f"[{i}/{len(txt_files)}] {txt_file.name}:")

        with open(txt_file, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

        idx = i - 1
        selected_contracts[idx] = content
        base_name = txt_file.stem  # contract_0, contract_1, etc.

        # Save in multiple formats
        formats = ['txt']
        if HAS_REPORTLAB and i % 3 != 0:  # PDF for ~2/3 of contracts
            formats.append('pdf')
        if HAS_DOCX and i % 2 == 0:      # DOCX for ~1/2 of contracts
            formats.append('docx')

        save_document(content, base_name, contracts_dir, formats=formats)

    # ========================================================================
    # STEP 2: Create synthetic amendments
    # ========================================================================
    print(f"\n{'='*70}")
    print("STEP 2: Creating synthetic amendments")
    print("="*70)

    total_amendments = 0
    for contract_idx, amendment_types in AMENDMENTS_TO_CREATE.items():
        if contract_idx not in selected_contracts:
            print(f"[WARN] Contract index {contract_idx} not in selected contracts, skipping")
            continue

        base_content = selected_contracts[contract_idx]
        contract_name = f"contract_{contract_idx}"

        print(f"\n[AMEND] {contract_name}:")
        for amendment_type in amendment_types:
            total_amendments += 1
            amendment_content = create_amendment(base_content, amendment_type)
            amendment_name = f"{contract_name}_{amendment_type}"

            # Amendments in TXT + DOCX
            save_document(amendment_content, amendment_name, amendments_dir,
                        formats=['txt', 'docx'])

    print(f"\n[OK] Created {total_amendments} amendments")

    # ========================================================================
    # STEP 3: Create synthetic test documents
    # ========================================================================
    print(f"\n{'='*70}")
    print("STEP 3: Creating synthetic test documents")
    print("="*70)

    for doc_name, doc_content in SYNTHETIC_DOCS.items():
        base_name = doc_name.replace('.txt', '')
        print(f"\n[DOC] {doc_name}:")

        # Mix formats for synthetics too
        formats = ['txt']
        if HAS_DOCX:
            formats.append('docx')
        if HAS_REPORTLAB:
            formats.append('pdf')

        save_document(doc_content, base_name, synthetics_dir, formats=formats)

    # ========================================================================
    # Summary
    # ========================================================================
    print(f"\n{'='*70}")
    print("[OK] VDR TEST DATA SETUP COMPLETE")
    print("="*70)

    total_files = sum(1 for _ in output_dir.rglob('*') if _.is_file())

    print(f"""
[SUMMARY]
   Base Contracts:     {len(list(contracts_dir.glob('*')))} files
   Amendments:         {len(list(amendments_dir.glob('*')))} files
   Test Documents:     {len(list(synthetics_dir.glob('*')))} files
   Total Files:        {total_files}

[OUTPUT LOCATION]
   {output_dir}

[NEXT STEPS]
   1. Navigate to VDR dashboard
   2. Create new deal room: "MAUD Test Acquisition"
   3. Upload documents from each folder:
      - 1_base_contracts/
      - 2_amendments/
      - 3_test_documents/
   4. Run analysis pipeline
   5. Run investigations

[DOCUMENT TYPES]
   - Base: Real merger agreements from MAUD
   - Amendments: Synthetic modifications (CoC, assignments)
   - Synthetics: Service agreements, financials, unclassified

[TESTS]
   * Document classification
   * Amendment detection
   * Change-of-control extraction
   * LLM augmentation
   * Coverage scoring
   * Audit trail
""")

    print(f"{'='*70}\n")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Set up VDR test data from MAUD contracts',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  python scripts/setup_vdr_test_data.py \\
    --maud-dir "/path/to/maud/contracts" \\
    --output-dir "/path/to/output"
        '''
    )

    parser.add_argument(
        '--maud-dir',
        type=Path,
        default=Path(r'C:\Users\sar13821\Downloads\PE\data\data\contracts'),
        help='Path to MAUD contracts directory'
    )

    parser.add_argument(
        '--output-dir',
        type=Path,
        default=Path(r'C:\Users\sar13821\Downloads\PE\VDR_TEST_DATA'),
        help='Output directory for test data'
    )

    args = parser.parse_args()

    # Verify input directory
    if not args.maud_dir.exists():
        print(f"❌ MAUD directory not found: {args.maud_dir}")
        exit(1)

    # Check dependencies
    if not HAS_REPORTLAB:
        print("[WARNING] reportlab not installed — install with: pip install reportlab")
    if not HAS_DOCX:
        print("[WARNING] python-docx not installed — install with: pip install python-docx")

    main(args.maud_dir, args.output_dir)
