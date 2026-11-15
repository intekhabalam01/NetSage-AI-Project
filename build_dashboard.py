import csv
from collections import Counter
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.chart import BarChart, DoughnutChart, Reference
from openpyxl.chart.label import DataLabelList
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo


CASES_FILE = "cases.csv"
REVIEW_LOG_FILE = "responsible_ai_log.csv"
OUTPUT_FILE = "NetSage_AI_Final_Dashboard.xlsx"

# Executive Palette
DARK_NAVY = "0F172A"       # Primary Title
SLATE_HEADER = "1E293B"    # Table Headers
TEXT_DARK = "334155"       # Subtitles / Body Text
BORDER_COLOR = "CBD5E1"    # Clean Light Slate Border

# Accent / Indicator Fills
BG_KPI = "F8FAFC"
ACCENT_BLUE = "3B82F6"
FILL_GREEN = "DCFCE7"
FILL_YELLOW = "FEF9C3"
FILL_RED = "FEE2E2"
FILL_SKY = "E0F2FE"
GREY_ROW = "F8FAFC"
WHITE = "FFFFFF"

THIN_BORDER = Side(style="thin", color=BORDER_COLOR)
BORDER = Border(left=THIN_BORDER, right=THIN_BORDER, top=THIN_BORDER, bottom=THIN_BORDER)

# Typography
TITLE_FONT = Font(name="Aptos", size=18, bold=True, color=WHITE)
SUBTITLE_FONT = Font(name="Aptos", size=10, italic=False, color="94A3B8")
SECTION_HEADER_FONT = Font(name="Aptos", size=11, bold=True, color=WHITE)
KPI_VALUE_FONT = Font(name="Aptos", size=20, bold=True, color=DARK_NAVY)
KPI_LABEL_FONT = Font(name="Aptos", size=9, bold=True, color="64748B")
BODY_FONT = Font(name="Aptos", size=10, color=TEXT_DARK)

NAVY_FILL = PatternFill("solid", fgColor=DARK_NAVY)
SLATE_FILL = PatternFill("solid", fgColor=SLATE_HEADER)
KPI_BG_FILL = PatternFill("solid", fgColor=BG_KPI)
SKY_FILL = PatternFill("solid", fgColor=FILL_SKY)
GREEN_FILL = PatternFill("solid", fgColor=FILL_GREEN)
YELLOW_FILL = PatternFill("solid", fgColor=FILL_YELLOW)
RED_FILL = PatternFill("solid", fgColor=FILL_RED)
WHITE_FILL = PatternFill("solid", fgColor=WHITE)
GREY_ROW_FILL = PatternFill("solid", fgColor=GREY_ROW)


def clean(value):
    return "" if value is None else str(value).strip()


def load_csv(filename):
    path = Path(filename)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {filename}")

    with path.open("r", newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        if not reader.fieldnames:
            raise ValueError(f"{filename} has no valid column headers.")

        headers = [clean(header) for header in reader.fieldnames]
        rows = []
        for row in reader:
            cleaned = {clean(key): clean(value) for key, value in row.items()}
            if any(cleaned.values()):
                rows.append(cleaned)

    return headers, rows


def require_columns(headers, required_columns, filename):
    missing = [column for column in required_columns if column not in headers]
    if missing:
        raise ValueError(f"{filename} is missing required columns: {', '.join(missing)}")


def style_cell(cell, fill=None, font=None, alignment=None):
    cell.border = BORDER
    if fill:
        cell.fill = fill
    if font:
        cell.font = font
    if alignment:
        cell.alignment = alignment


def auto_width(ws, max_width=42):
    for column_cells in ws.columns:
        letter = get_column_letter(column_cells[0].column)
        longest = 10
        for cell in column_cells:
            value = "" if cell.value is None else str(cell.value)
            longest = max(longest, min(len(value), max_width))
        ws.column_dimensions[letter].width = min(longest + 2, max_width)


def create_data_sheet(wb, sheet_name, title, headers, rows, table_name):
    ws = wb.create_sheet(sheet_name)
    ws.sheet_view.showGridLines = True

    last_column = get_column_letter(len(headers))

    ws.merge_cells(f"A1:{last_column}1")
    ws["A1"] = title
    style_cell(
        ws["A1"],
        fill=NAVY_FILL,
        font=TITLE_FONT,
        alignment=Alignment(horizontal="center", vertical="center")
    )
    ws.row_dimensions[1].height = 36

    for column_index, header in enumerate(headers, start=1):
        cell = ws.cell(row=2, column=column_index, value=header)
        style_cell(
            cell,
            fill=SLATE_FILL,
            font=SECTION_HEADER_FONT,
            alignment=Alignment(horizontal="center", vertical="center")
        )

    ws.row_dimensions[2].height = 28

    for row_index, row in enumerate(rows, start=3):
        for column_index, header in enumerate(headers, start=1):
            cell = ws.cell(row=row_index, column=column_index, value=row.get(header, ""))
            fill = GREY_ROW_FILL if row_index % 2 == 0 else WHITE_FILL
            style_cell(
                cell,
                fill=fill,
                font=BODY_FONT,
                alignment=Alignment(vertical="center", wrap_text=True)
            )
        ws.row_dimensions[row_index].height = 26

    final_row = max(3, len(rows) + 2)
    table = Table(displayName=table_name, ref=f"A2:{last_column}{final_row}")
    table.tableStyleInfo = TableStyleInfo(
        name="TableStyleLight1",
        showFirstColumn=False,
        showLastColumn=False,
        showRowStripes=True,
        showColumnStripes=False
    )
    ws.add_table(table)
    ws.freeze_panes = "A3"
    auto_width(ws)
    return ws


def create_kpi_card(ws, start_column, value, label, accent_fill=None):
    col1 = get_column_letter(start_column)
    col2 = get_column_letter(start_column + 1)

    val_range = f"{col1}4:{col2}4"
    lbl_range = f"{col1}5:{col2}5"

    ws.merge_cells(val_range)
    ws.merge_cells(lbl_range)

    value_cell = ws.cell(row=4, column=start_column, value=value)
    label_cell = ws.cell(row=5, column=start_column, value=label)

    card_fill = accent_fill if accent_fill else KPI_BG_FILL

    for row in ws[f"{col1}4:{col2}5"]:
        for cell in row:
            style_cell(cell, fill=card_fill)

    value_cell.font = KPI_VALUE_FONT
    value_cell.alignment = Alignment(horizontal="center", vertical="center")
    
    label_cell.font = KPI_LABEL_FONT
    label_cell.alignment = Alignment(horizontal="center", vertical="center")

    ws.row_dimensions[4].height = 28
    ws.row_dimensions[5].height = 18


def create_summary_table(ws, start_row, start_column, title, values):
    end_column = start_column + 1

    ws.merge_cells(start_row=start_row, start_column=start_column, end_row=start_row, end_column=end_column)
    title_cell = ws.cell(row=start_row, column=start_column, value=title)
    
    style_cell(
        title_cell,
        fill=SLATE_FILL,
        font=SECTION_HEADER_FONT,
        alignment=Alignment(horizontal="center", vertical="center")
    )
    ws.cell(row=start_row, column=end_column).fill = SLATE_FILL
    ws.cell(row=start_row, column=end_column).border = BORDER

    header_row = start_row + 1
    for idx, header in enumerate(["Metric", "Count"], start=start_column):
        cell = ws.cell(row=header_row, column=idx, value=header)
        style_cell(
            cell,
            fill=SKY_FILL,
            font=Font(name="Aptos", size=9, bold=True, color=DARK_NAVY),
            alignment=Alignment(horizontal="center", vertical="center")
        )

    for offset, (name, count) in enumerate(values, start=2):
        row = start_row + offset
        fill = GREY_ROW_FILL if row % 2 == 0 else WHITE_FILL

        n_cell = ws.cell(row=row, column=start_column, value=name)
        c_cell = ws.cell(row=row, column=end_column, value=count)

        style_cell(n_cell, fill=fill, font=BODY_FONT, alignment=Alignment(vertical="center"))
        style_cell(c_cell, fill=fill, font=BODY_FONT, alignment=Alignment(horizontal="center", vertical="center"))

    return header_row, start_row + len(values) + 1


def main():
    print("\nNETSAGE AI DASHBOARD BUILD STARTED\n")

    case_headers, cases = load_csv(CASES_FILE)
    review_headers, reviews = load_csv(REVIEW_LOG_FILE)

    require_columns(case_headers, ["case_id", "concept", "severity", "expected_fault"], CASES_FILE)
    require_columns(
        review_headers,
        ["case_id", "ai_root_cause", "ai_confidence", "rule_checker_status", "human_review", "review_notes"],
        REVIEW_LOG_FILE
    )

    total_cases = len(cases)
    total_reviews = len(reviews)

    issue_counts = Counter(row["concept"] for row in cases)
    severity_counts = Counter(row["severity"] for row in cases)
    review_counts = Counter(row["human_review"] for row in reviews)
    rule_counts = Counter(row["rule_checker_status"] for row in reviews)

    accepted = review_counts.get("Accepted", 0)
    edited = review_counts.get("Edited", 0)
    rejected = review_counts.get("Rejected", 0)
    corrected = edited + rejected

    agreement_rate = accepted / total_reviews if total_reviews else 0
    rule_pass_rate = rule_counts.get("PASS", 0) / total_reviews if total_reviews else 0

    corrected_case_ids = {
        row["case_id"] for row in reviews if row["human_review"] in {"Edited", "Rejected"}
    }

    wb = Workbook()
    wb.remove(wb.active)

    create_data_sheet(wb, "Cases", "Cases Dataset", case_headers, cases, "CasesTable")
    review_ws = create_data_sheet(wb, "Review Log", "Human Review Log", review_headers, reviews, "ReviewLogTable")

    status_col = get_column_letter(review_headers.index("human_review") + 1)
    review_ws.conditional_formatting.add(f"{status_col}3:{status_col}{len(reviews) + 2}", CellIsRule(operator="equal", formula=['"Accepted"'], fill=GREEN_FILL))
    review_ws.conditional_formatting.add(f"{status_col}3:{status_col}{len(reviews) + 2}", CellIsRule(operator="equal", formula=['"Edited"'], fill=YELLOW_FILL))
    review_ws.conditional_formatting.add(f"{status_col}3:{status_col}{len(reviews) + 2}", CellIsRule(operator="equal", formula=['"Rejected"'], fill=RED_FILL))

    correction_headers = [
        "Case ID", "Concept", "Severity", "Expected Fault",
        "AI Root Cause", "Human Decision", "Human Final Root Cause", "Reviewer Notes"
    ]
    review_lookup = {row["case_id"]: row for row in reviews}
    correction_rows = []

    for case in cases:
        case_id = case["case_id"]
        if case_id in corrected_case_ids:
            review = review_lookup[case_id]
            correction_rows.append({
                "Case ID": case_id,
                "Concept": case["concept"],
                "Severity": case["severity"],
                "Expected Fault": case["expected_fault"],
                "AI Root Cause": review["ai_root_cause"],
                "Human Decision": review["human_review"],
                "Human Final Root Cause": review.get("human_final_root_cause", ""),
                "Reviewer Notes": review["review_notes"]
            })

    corrections_ws = create_data_sheet(wb, "Human Corrections", "Audit Trail: Corrected Cases", correction_headers, correction_rows, "CorrectionsTable")
    dec_col = get_column_letter(correction_headers.index("Human Decision") + 1)
    corrections_ws.conditional_formatting.add(f"{dec_col}3:{dec_col}{len(correction_rows) + 2}", CellIsRule(operator="equal", formula=['"Edited"'], fill=YELLOW_FILL))
    corrections_ws.conditional_formatting.add(f"{dec_col}3:{dec_col}{len(correction_rows) + 2}", CellIsRule(operator="equal", formula=['"Rejected"'], fill=RED_FILL))

    # Dashboard Sheet
    ws = wb.create_sheet("Dashboard", 0)
    ws.sheet_view.showGridLines = True
    ws.freeze_panes = "A4"
    ws.sheet_view.zoomScale = 100

    for col in range(1, 13):
        ws.column_dimensions[get_column_letter(col)].width = 17

    # Center-aligned Header Title & Subtitle
    ws.merge_cells("A1:L1")
    ws["A1"] = "NetSage AI — Executive Network Diagnostics & Governance Dashboard"
    style_cell(ws["A1"], fill=NAVY_FILL, font=TITLE_FONT, alignment=Alignment(horizontal="center", vertical="center"))
    ws.row_dimensions[1].height = 36

    ws.merge_cells("A2:L2")
    ws["A2"] = f"Advisory Diagnostics Pipeline  |  Human-in-the-Loop Audit Enforced  |  Generated: {datetime.now().strftime('%d %b %Y')}"
    style_cell(ws["A2"], fill=SLATE_FILL, font=SUBTITLE_FONT, alignment=Alignment(horizontal="center", vertical="center"))
    ws.row_dimensions[2].height = 22

    # KPI Bar
    create_kpi_card(ws, 1, total_cases, "TOTAL CASES")
    create_kpi_card(ws, 3, accepted, "ACCEPTED", GREEN_FILL)
    create_kpi_card(ws, 5, edited, "EDITED", YELLOW_FILL)
    create_kpi_card(ws, 7, rejected, "REJECTED", RED_FILL)
    create_kpi_card(ws, 9, f"{agreement_rate:.1%}", "AGREEMENT RATE")
    create_kpi_card(ws, 11, f"{rule_pass_rate:.1%}", "RULE COMPLIANCE")

    severity_values = [("High", severity_counts.get("High", 0)), ("Medium", severity_counts.get("Medium", 0)), ("Low", severity_counts.get("Low", 0))]
    issue_values = sorted(issue_counts.items())
    review_values = [("Accepted", accepted), ("Edited", edited), ("Rejected", rejected)]
    rule_values = [("PASS", rule_counts.get("PASS", 0)), ("FAIL", rule_counts.get("FAIL", 0)), ("Human Corrected", corrected)]

    # Metrics Tables
    sev_h, sev_e = create_summary_table(ws, 7, 1, "Issue Severity", severity_values)
    iss_h, iss_e = create_summary_table(ws, 7, 4, "Issue Types", issue_values)
    rev_h, rev_e = create_summary_table(ws, 7, 7, "Human Review", review_values)
    rul_h, rul_e = create_summary_table(ws, 7, 10, "Rule Governance", rule_values)

    # 1. Severity Chart (Positioned at A14)
    sev_chart = DoughnutChart()
    sev_chart.title = "Severity Distribution"
    sev_chart.height = 7.0
    sev_chart.width = 10.5
    sev_chart.holeSize = 55
    sev_chart.add_data(Reference(ws, min_col=2, min_row=sev_h, max_row=sev_e), titles_from_data=True)
    sev_chart.set_categories(Reference(ws, min_col=1, min_row=sev_h + 1, max_row=sev_e))
    sev_chart.dLbls = DataLabelList()
    sev_chart.dLbls.showPercent = True
    sev_chart.legend.position = "b"
    ws.add_chart(sev_chart, "A14")

    # 2. Issue Type Bar Chart (Right-shifted to H14 to eliminate overlap)
    iss_chart = BarChart()
    iss_chart.type = "bar"
    iss_chart.title = "Troubleshooting Cases by Concept"
    iss_chart.height = 7.0
    iss_chart.width = 14.5
    iss_chart.add_data(Reference(ws, min_col=5, min_row=iss_h, max_row=iss_e), titles_from_data=True)
    iss_chart.set_categories(Reference(ws, min_col=4, min_row=iss_h + 1, max_row=iss_e))
    iss_chart.legend = None
    ws.add_chart(iss_chart, "H14")

    # 3. Review Outcome Chart (Positioned at A30)
    rev_chart = DoughnutChart()
    rev_chart.title = "Human-in-the-Loop Review Outcomes"
    rev_chart.height = 7.0
    rev_chart.width = 10.5
    rev_chart.holeSize = 55
    rev_chart.add_data(Reference(ws, min_col=8, min_row=rev_h, max_row=rev_e), titles_from_data=True)
    rev_chart.set_categories(Reference(ws, min_col=7, min_row=rev_h + 1, max_row=rev_e))
    rev_chart.dLbls = DataLabelList()
    rev_chart.dLbls.showPercent = True
    rev_chart.legend.position = "b"
    ws.add_chart(rev_chart, "A30")

    # Governance Audit Panel (Shifted to H30 to match top chart)
    ws.merge_cells("H30:L39")
    ws["H30"] = (
        "Responsible AI & Human-in-the-Loop Governance Audit\n\n"
        f"• Human Interventions: {corrected} / {total_reviews} cases require manual correction.\n"
        f"• Diagnostic Reliability: {agreement_rate:.1%} initial agreement rate.\n"
        f"• Validation Integrity: {rule_pass_rate:.1%} pass rate under deterministic rule checker.\n\n"
        "All overrides are recorded in the 'Human Corrections' sheet to refine AI prompts "
        "and maintain network safety."
    )
    style_cell(
        ws["H30"],
        fill=KPI_BG_FILL,
        font=Font(name="Aptos", size=10, bold=False, color=TEXT_DARK),
        alignment=Alignment(vertical="center", horizontal="left", wrap_text=True)
    )
    for r in ws["H30:L39"]:
        for cell in r:
            cell.fill = KPI_BG_FILL
            cell.border = BORDER

    # Clean Footer
    ws.merge_cells("A43:L43")
    ws["A43"] = "NetSage AI Diagnostics • Cisco Packet Tracer Automated Audit Dashboard"
    style_cell(ws["A43"], fill=SLATE_FILL, font=Font(name="Aptos", size=9, color=WHITE), alignment=Alignment(horizontal="center", vertical="center"))
    ws.row_dimensions[43].height = 22

    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True

    wb.save(OUTPUT_FILE)
    print("\nDASHBOARD SUCCESSFULLY UPDATED AND SAVED")


if __name__ == "__main__":
    main()