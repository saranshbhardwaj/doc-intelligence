from pathlib import Path

import yaml
import pytest

from app.verticals.real_estate.template_filling.excel.schema_based.schema_loader import (
    SchemaLoader,
)


SCHEMA_PATH = (
    Path(__file__).parents[5]
    / "app"
    / "verticals"
    / "real_estate"
    / "template_filling"
    / "excel"
    / "schema_based"
    / "schemas"
    / "re_investment_v1.yaml"
)


def _schema_fields():
    schema = yaml.safe_load(SCHEMA_PATH.read_text())
    return schema["fields"]


def _schema_tables():
    schema = yaml.safe_load(SCHEMA_PATH.read_text())
    return schema.get("tables", [])


def _loaded_schema():
    return SchemaLoader(schemas_dir=str(SCHEMA_PATH.parent)).load_schema("re_investment_v1")


def _field(field_id):
    return next(field for field in _schema_fields() if field["id"] == field_id)


def _dashboard_fields():
    return [field for field in _schema_fields() if field.get("sheet") == "DASHBOARD"]


def _napkin_fields():
    return [field for field in _schema_fields() if field.get("sheet") == "Napkin"]


def _actuals_unit_mix_fields():
    return [field for field in _schema_fields() if field.get("sheet") == "Actuals&UnitMix"]


def _pnl_fields():
    return [field for field in _schema_fields() if field.get("sheet") == "P&L"]


def _capex_reserves_fields():
    return [field for field in _schema_fields() if field.get("sheet") == "CapEx&Reserves"]


def test_dashboard_only_extracts_om_fact_cells():
    dashboard_cells = {field["value_cell"]: field["id"] for field in _dashboard_fields()}

    assert dashboard_cells == {
        "C3": "property_name",
        "C4": "property_address",
        "C6": "storage_unit_count",
        "C8": "asking_price",
    }


def test_yaml_contract_metadata_uses_closed_enums():
    allowed_periods = {"current", "t12", "year1", "pro_forma", "stabilized", "static"}
    allowed_basis = {
        "om_operating_statement",
        "om_unit_mix",
        "om_property_summary",
        "om_market_summary",
        "om_rent_roll",
        "om_rent_comps",
        "om_capex_schedule",
    }
    allowed_fill_when = {
        "always",
        "current_operating_statement_present",
        "year1_operating_statement_present",
        "pro_forma_operating_statement_present",
        "t12_present",
        "unit_mix_present",
        "rent_roll_present",
        "rent_comps_present",
        "market_summary_present",
    }

    loaded_schema = _loaded_schema()
    targets = loaded_schema.fields + loaded_schema.tables

    assert targets
    for target in targets:
        assert target.get("source_period") in allowed_periods
        assert target.get("source_basis") in allowed_basis
        fill_when = target.get("fill_when")
        if isinstance(fill_when, str):
            fill_when = [fill_when]
        assert fill_when
        assert set(fill_when).issubset(allowed_fill_when)


def test_active_yaml_targets_declare_contract_metadata_explicitly():
    targets = _schema_fields() + _schema_tables()

    assert targets
    for target in targets:
        missing = [
            key
            for key in ("source_period", "source_basis", "fill_when", "requires_structure")
            if key not in target
        ]
        assert missing == [], f"{target['id']} missing {missing}"


def test_schema_loader_rejects_unknown_contract_metadata(tmp_path):
    schema = yaml.safe_load(SCHEMA_PATH.read_text())
    schema["fields"][0]["source_period"] = "broker-vibes"
    schema_path = tmp_path / "bad_schema.yaml"
    schema_path.write_text(yaml.safe_dump(schema), encoding="utf-8")

    loader = SchemaLoader(schemas_dir=str(tmp_path))

    with pytest.raises(ValueError, match="source_period"):
        loader.load_schema("bad_schema")


def test_schema_loader_rejects_missing_contract_metadata_for_operating_targets(tmp_path):
    schema = yaml.safe_load(SCHEMA_PATH.read_text())
    target = next(
        field
        for field in schema["fields"]
        if field["id"] == "actuals_unit_mix_expenses_re_tax"
    )
    for key in ("source_period", "source_basis", "fill_when", "requires_structure"):
        target.pop(key, None)
    schema_path = tmp_path / "missing_contract.yaml"
    schema_path.write_text(yaml.safe_dump(schema), encoding="utf-8")

    loader = SchemaLoader(schemas_dir=str(tmp_path))

    with pytest.raises(ValueError, match="missing contract metadata"):
        loader.load_schema("missing_contract")


def test_napkin_current_fields_are_period_specific():
    current_expense = _field("napkin_current_expense_per_unit")
    current_vacancy = _field("napkin_economic_vacancy_rate_current")

    assert current_expense["value_cell"] == "C10"
    assert "extraction_rule" in current_expense
    assert "current" in current_expense["extraction_rule"].lower()
    assert "storage" in current_expense["extraction_rule"].lower()
    assert "Expense per Unit" not in current_expense["pdf_aliases"]

    assert current_vacancy["value_cell"] == "C12"
    assert "extraction_rule" in current_vacancy
    assert "current" in current_vacancy["extraction_rule"].lower()
    assert "Physical Vacancy Current" not in current_vacancy["pdf_aliases"]
    assert "Rent Concessions" not in current_vacancy["pdf_aliases"]


def test_napkin_proforma_fields_are_stabilized_specific():
    proforma_fields = {
        field["id"]: field
        for field in _napkin_fields()
        if field["id"]
        in {
            "napkin_proforma_avg_effective_rent",
            "napkin_proforma_other_income_per_unit",
            "napkin_proforma_expense_per_unit",
            "napkin_stabilized_cap_rate",
            "napkin_proforma_economic_vacancy_rate",
        }
    }

    assert set(proforma_fields) == {
        "napkin_proforma_avg_effective_rent",
        "napkin_proforma_other_income_per_unit",
        "napkin_proforma_expense_per_unit",
        "napkin_stabilized_cap_rate",
        "napkin_proforma_economic_vacancy_rate",
    }
    assert proforma_fields["napkin_proforma_avg_effective_rent"]["value_cell"] == "G5"
    assert proforma_fields["napkin_proforma_other_income_per_unit"]["value_cell"] == "G6"
    assert proforma_fields["napkin_proforma_expense_per_unit"]["value_cell"] == "G10"
    assert proforma_fields["napkin_stabilized_cap_rate"]["value_cell"] == "G11"
    assert proforma_fields["napkin_proforma_economic_vacancy_rate"]["value_cell"] == "G12"

    for field in proforma_fields.values():
        assert "extraction_rule" in field
        rule = field["extraction_rule"].lower()
        assert "pro forma" in rule or "stabilized" in rule

    assert "Average Rent" not in proforma_fields["napkin_proforma_avg_effective_rent"]["pdf_aliases"]
    rent_rule = proforma_fields["napkin_proforma_avg_effective_rent"]["extraction_rule"].lower()
    assert "leave null" in rent_rule
    assert "do not use current" in rent_rule
    assert "unless" not in rent_rule
    assert "Expense per Unit" not in proforma_fields["napkin_proforma_expense_per_unit"]["pdf_aliases"]
    assert "Year 1 Vacancy Rate" not in proforma_fields["napkin_proforma_economic_vacancy_rate"]["pdf_aliases"]


def test_napkin_helpful_data_tracks_source_facts_not_analyst_ratings():
    napkin_cells = {field["value_cell"]: field["id"] for field in _napkin_fields()}

    assert napkin_cells["C30"] == "napkin_year_built"
    assert napkin_cells["C31"] == "napkin_storage_unit_count"
    assert napkin_cells["C32"] == "napkin_total_rentable_sqft"
    assert napkin_cells["C36"] == "napkin_population"
    assert napkin_cells["C37"] == "napkin_population_growth_rate"
    assert "C39" not in napkin_cells

    population = _field("napkin_population")
    assert "3-mile" in population["extraction_rule"].lower()


def test_napkin_excludes_multifamily_financing_and_cap_rate_sensitivity_inputs():
    napkin_fields = [field for field in _napkin_fields()]
    napkin_cells = {field["value_cell"] for field in napkin_fields}
    napkin_table_ids = {table["id"] for table in _schema_tables() if table.get("sheet") == "Napkin"}

    assert "N4" not in napkin_cells  # LTV
    assert "P4" not in napkin_cells  # Int Rate
    assert "napkin_market_metrics" not in napkin_table_ids


def test_napkin_excludes_new_development_retail_mixed_use_assumption_cells():
    napkin_fields = [field for field in _napkin_fields()]
    napkin_cells = {field["value_cell"] for field in napkin_fields}

    assert "L32" not in napkin_cells
    assert "L33" not in napkin_cells
    assert "L35" not in napkin_cells
    assert "L37" not in napkin_cells
    assert "L40" not in napkin_cells
    assert "O32" not in napkin_cells
    assert "O33" not in napkin_cells
    assert "Q32" not in napkin_cells
    assert "Q33" not in napkin_cells


def test_actuals_unit_mix_keeps_formula_percentages_out_and_maps_other_income_current_inputs():
    actuals_cells = {field["value_cell"]: field["id"] for field in _actuals_unit_mix_fields()}

    assert "D7" not in actuals_cells
    assert "D8" not in actuals_cells
    assert actuals_cells["H30"] == "actuals_unit_mix_current_insurance_policy"
    assert actuals_cells["H31"] == "actuals_unit_mix_current_admin_fee"
    assert actuals_cells["H32"] == "actuals_unit_mix_current_late_fee"
    assert actuals_cells["H33"] == "actuals_unit_mix_current_covered_parking_fee"
    assert actuals_cells["H34"] == "actuals_unit_mix_current_uncovered_parking_fee"
    assert actuals_cells["H35"] == "actuals_unit_mix_current_residential"
    assert actuals_cells["H36"] == "actuals_unit_mix_current_misc_fee"
    assert actuals_cells["H37"] == "actuals_unit_mix_current_other_misc_income"

    for cell in ("H30", "H31", "H32", "H33", "H34", "H35", "H36", "H37"):
        field = _field(actuals_cells[cell])
        assert "extraction_rule" in field
        assert "current" in field["extraction_rule"].lower()


def test_actuals_unit_mix_expense_lines_are_actual_current_only_and_exclude_capex_reserve():
    actuals_cells = {field["value_cell"]: field["id"] for field in _actuals_unit_mix_fields()}

    assert "C37" not in actuals_cells

    for row in range(19, 36):
        cell = f"C{row}"
        assert cell in actuals_cells
        field = _field(actuals_cells[cell])
        assert "extraction_rule" in field
        rule = field["extraction_rule"].lower()
        assert "actual" in rule or "current" in rule
        assert "year 1" in rule
        assert "pro forma" in rule


def test_actuals_unit_mix_unit_mix_table_is_storage_only_and_row_aligned():
    actuals_tables = {
        table["id"]: table for table in _schema_tables() if table.get("sheet") == "Actuals&UnitMix"
    }

    assert "actuals_unit_mix_storage_unit_mix" in actuals_tables
    assert "actuals_unit_mix_target_rent_analysis" not in actuals_tables
    assert "actuals_unit_mix_current_rent_analysis" not in actuals_tables

    table = actuals_tables["actuals_unit_mix_storage_unit_mix"]
    assert table["data_start_row"] == 5
    assert table["data_end_row"] == 19
    assert table["row_identifier_column"] == "G"
    assert "extraction_rule" in table
    rule = table["extraction_rule"].lower()
    assert "storage" in rule
    assert "exclude parking" in rule
    assert "exclude residential" in rule

    columns = {column["excel_column"]: column for column in table["columns"]}
    assert set(columns) == {"G", "H", "I", "K"}
    assert columns["G"]["header"] == "Type"
    assert columns["H"]["header"] == "# Units"
    assert columns["I"]["header"] == "SqFt"
    assert columns["K"]["header"] == "Current Rent Average"
    assert columns["K"]["data_type"] == "currency"
    # # Units must guard against being duplicated from SqFt — leave unmapped instead.
    assert columns["H"]["disallow_equal_to_column"] == "I"


def test_pnl_year1_expense_inputs_are_forward_basis_and_exclude_assumption_cells():
    pnl_cells = {field["value_cell"]: field["id"] for field in _pnl_fields()}

    assert pnl_cells["E31"] == "pnl_year1_white_label_expense"
    assert pnl_cells["E32"] == "pnl_year1_personnel_expense"
    assert pnl_cells["E33"] == "pnl_year1_advertising_expense"
    assert pnl_cells["E36"] == "pnl_year1_misc_2_expense"

    for cell in ("E31", "E32", "E33", "E36"):
        field = _field(pnl_cells[cell])
        assert "extraction_rule" in field
        rule = field["extraction_rule"].lower()
        assert "year 1" in rule
        assert "pro forma" in rule
        assert "do not use current" in rule

    assert "E46" not in pnl_cells
    assert "E47" not in pnl_cells
    assert "E48" not in pnl_cells


def test_capex_reserves_sheet_has_no_active_om_extraction_targets():
    capex_cells = {field["value_cell"] for field in _capex_reserves_fields()}
    capex_table_ids = {
        table["id"] for table in _schema_tables() if table.get("sheet") == "CapEx&Reserves"
    }

    assert capex_cells == set()
    assert capex_table_ids == set()


def test_derived_sample_and_financing_sheets_have_no_active_om_extraction_targets():
    excluded_sheets = {
        "Deal Sheet",
        "Returns",
        "Investor Sample",
        "Rent Turns",
        "Rent Roll",
        "1st MTG",
        "REFI-1st MTG",
        "2nd MTG",
        "Debt Stack",
        "Variables",
        "IRR-XIRR",
    }

    active_field_sheets = {
        field.get("sheet") for field in _schema_fields() if field.get("sheet") in excluded_sheets
    }
    active_table_sheets = {
        table.get("sheet") for table in _schema_tables() if table.get("sheet") in excluded_sheets
    }

    assert active_field_sheets == set()
    assert active_table_sheets == set()
