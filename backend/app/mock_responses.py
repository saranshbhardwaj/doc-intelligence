# backend/app/mock_responses.py
from datetime import datetime
from app.models import (
    ExtractionResponse, ExtractedData, CompanyInfo, Financials, BalanceSheet,
    FinancialRatios, KeyRisk, ManagementMember, TransactionDetails,
    ExtractionMetadata, RateLimitInfo
)
import uuid
import time

def generate_mock_response(filename: str) -> ExtractionResponse:
    """Return a fake but realistic ExtractionResponse for testing."""
    start = time.time()
    request_id = str(uuid.uuid4())

    data = ExtractedData(
        company_info=CompanyInfo(
            company_name="Acme Analytics LLC",
            industry="Data Services",
            founded_year=2016,
            employees=120,
            headquarters="Austin, TX",
        ),
        financials=Financials(
            revenue_by_year={"2022": 18000000, "2023": 22500000},
            ebitda_by_year={"2023": 4800000},
        ),
        balance_sheet=BalanceSheet(total_assets=7500000, total_liabilities=3200000),
        financial_ratios=FinancialRatios(current_ratio=2.3, debt_to_equity=0.42),
        key_risks=[
            KeyRisk(
                risk="Dependence on one major data supplier",
                severity="High",
                description="A single vendor provides 70% of input data"
            )
        ],
        management_team=[
            ManagementMember(name="Jane Doe", title="CEO", background="Ex-Google"),
            ManagementMember(name="John Smith", title="CFO", background="10 years in fintech")
        ],
        transaction_details=TransactionDetails(
            seller_motivation="Founder succession planning",
            auction_deadline="2025-12-01"
        ),
        customers={"Top 3": ["Alpha Corp", "Beta Systems", "Delta Partners"]},
        market={"growth_rate": "18%", "segment": "AI data analytics"}
    )

    metadata = ExtractionMetadata(
        request_id=request_id,
        filename=filename,
        pages=12,
        characters_extracted=5000,
        processing_time_seconds=time.time() - start,
        timestamp=datetime.now()
    )

    rate_limit = RateLimitInfo(
        remaining_uploads=2,
        reset_in_hours=24,
        limit_per_window=3
    )

    return ExtractionResponse(
        success=True,
        data=data,
        metadata=metadata,
        rate_limit=rate_limit,
        from_cache=False
    )
