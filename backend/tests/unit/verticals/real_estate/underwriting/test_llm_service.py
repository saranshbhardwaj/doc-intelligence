from app.verticals.real_estate.underwriting.extraction.rent_comp_repair import repair_om_rent_comp_rows


def test_repair_om_rent_comp_rows_splits_facility_rows_from_local_block():
    rent_comps = [
        {
            "facility": "KO Storage",
            "size": "5 x 10, 10 x 10, 10 x 15, 10 x 20",
            "asking_rent": None,
            "rent_per_sqft": None,
            "distance_mi": 1.13,
            "notes": "6565 E Virgin St, Tulsa, OK 74115; Year Built: 2001; Square Footage: 37,085",
        }
    ]
    source_context = """
[S1:p7] (Table Chunk)
KO Storage
6565 E Virgin St, Tulsa, OK 74115
Year Built: 2001
Square Footage: 37,085
Unit Type
Sq.Ft./Unit
Rent/Unit
Rent/Sq. Ft.
5 x 10
50
$75
$1.50
10 x 10
100
$79
$0.79
10 x 15
150
$74
$0.49
10 x 20
200
$99
$0.50
"""

    repaired = repair_om_rent_comp_rows(rent_comps, source_context)

    assert [row["size"] for row in repaired] == ["5 x 10", "10 x 10", "10 x 15", "10 x 20"]
    assert [row["asking_rent"] for row in repaired] == [75.0, 79.0, 74.0, 99.0]
    assert [row["rent_per_sqft"] for row in repaired] == [1.5, 0.79, 0.49, 0.5]
    assert all(row["distance_mi"] == 1.13 for row in repaired)


def test_repair_om_rent_comp_rows_assigns_blocks_by_facility_order_when_headers_are_grouped():
    rent_comps = [
        {
            "facility": "KO Storage",
            "size": "5 x 10, 10 x 10",
            "asking_rent": None,
            "rent_per_sqft": None,
            "distance_mi": 1.13,
            "notes": "KO metadata",
        },
        {
            "facility": "Best Local Self Storage",
            "size": "5 x 10, 10 x 10",
            "asking_rent": None,
            "rent_per_sqft": None,
            "distance_mi": 1.5,
            "notes": "Best Local metadata",
        },
    ]
    source_context = """
[S1:p9] (Table Chunk)
KO Storage
6565 E Virgin St, Tulsa, OK 74115
Year Built: 2001
Square Footage: 37,085
Best Local Self Storage
6143 E Admiral Pl, Tulsa, OK 74115
Year Built: 1989 / 1994
Square Footage: 10,854
5 x 10
50
$75
$1.50
10 x 10
100
$79
$0.79
5 x 10
50
$69
$1.38
10 x 10
100
$92
$0.92
"""

    repaired = repair_om_rent_comp_rows(rent_comps, source_context)

    assert [row["facility"] for row in repaired] == [
        "KO Storage",
        "KO Storage",
        "Best Local Self Storage",
        "Best Local Self Storage",
    ]
    assert [row["asking_rent"] for row in repaired] == [75.0, 79.0, 69.0, 92.0]
    assert [row["rent_per_sqft"] for row in repaired] == [1.5, 0.79, 1.38, 0.92]