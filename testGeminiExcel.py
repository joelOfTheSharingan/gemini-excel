import google.generativeai as genai
import pandas as pd
import json
import re
import os
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Alignment, Font
from collections import defaultdict
from datetime import datetime
import logging

# Configure the Gemini API (API key is a placeholder)
genai.configure(api_key="AIzaSyCK6TUjndLC631MFMhzceS3isC6vghgvIk")
model = genai.GenerativeModel("gemini-1.5-flash")

# Setup logging to capture output
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

COLOR_MAP = {
    "Food": "FFEB9C",
    "Travel": "C6EFCE",
    "Bills": "FFCDD2",
    "Fuel": "D9E1F2",
    "Health": "FCE4D6",
    "Others": "D9D2E9",
}

SUMMARY_HEADER_FILL_COLOR = "E2EFDA"
TRANSACTION_HEADERS = ["Date", "Description", "Amount", "Category"]
SUMMARY_HEADERS = ["Category", "Total", "Percentage (%)"]
DEFAULT_FILL_COLOR = "FFFFFF"

def classify_transactions(text):
    """
    Uses the Gemini API to parse transaction text and classify transactions into categories.
    Returns a list of transaction dictionaries and a boolean indicating if manual correction is needed.
    """
    prompt = f"""
You are a financial statement parser.
You must extract a clean list of transactions from the input text, returning a valid JSON list of dictionaries, where each dictionary contains:
- "date": (e.g., "12 Jul", "4 Mar") — if missing, use "Missing"
- "description": a short summary of the transaction (e.g., "Uber ride", "Electricity bill")
- "amount": only the numeric part, without the currency symbol
- "category": one of these categories:
  - "Food"
  - "Travel"
  - "Bills"
  - "Fuel"
  - "Health"
  - "Others"

Categories must be inferred based on the description:
- "Food" → groceries, restaurants, snacks, cafes
- "Travel" → taxis, Uber, buses, trains, flights, tolls
- "Bills" → electricity, water, rent, phone, internet, DTH
- "Fuel" → petrol, diesel, gasoline
- "Health" → medicine, hospitals, tests, clinics
- "Others" → everything else

### Your output format:
Only return a JSON list like this:
[
  {{
    "date": "12 Jul",
    "description": "Uber ride",
    "amount": "650",
    "category": "Travel"
  }},
  ...
]

### Rules:
- Use the exact field names: "date", "description", "amount", "category"
- No extra text before or after the JSON list
- Do not return Markdown formatting (no ```json blocks)
- If any field is missing, fill it with "Missing"
- Be very careful to produce valid JSON

### Input:
{text}
"""
    needs_correction = False
    try:
        response = model.generate_content(prompt)
        logging.info(f"[DEBUG] Raw Gemini response:\n{response.text}")

        # Clean the response to ensure it's valid JSON
        json_text = re.sub(r'```(?:json)?|```', '', response.text).strip()
        logging.info(f"[DEBUG] Cleaned JSON text:\n{json_text}")

        data = json.loads(json_text)
        if not isinstance(data, list):
            raise ValueError("Response is not a JSON list")

        required_fields = ["date", "description", "amount", "category"]
        for i, tx in enumerate(data):
            if not isinstance(tx, dict):
                raise ValueError("Transaction is not a dictionary")
            for field in required_fields:
                if field not in tx or not tx[field] or str(tx[field]).strip().lower() == "missing":
                    logging.warning(f"Missing or invalid '{field}' for transaction {i+1}. Marking for correction.")
                    tx[field] = None # Use None to signal missing data
                    needs_correction = True

            # Validate the amount field
            try:
                if tx.get("amount") is not None:
                    tx["amount"] = str(float(tx["amount"]))
            except (ValueError, TypeError):
                if tx["amount"] is not None:
                    logging.warning(f"Invalid amount '{tx.get('amount')}' for transaction {i+1}. Marking for correction.")
                    tx["amount"] = None
                    needs_correction = True

        logging.info(f"[DEBUG] Final parsed transactions before frontend correction:\n{data}")
        return data, needs_correction

    except json.JSONDecodeError as e:
        logging.error(f"JSON decode error: {e}")
        raise ValueError(f"Invalid JSON format in Gemini response: {e}")
    except ValueError as e:
        logging.error(f"Validation error: {e}")
        raise
    except Exception as e:
        logging.error(f"Error in classify_transactions: {e}")
        raise

def write_to_excel(data: list[dict], output_path: str) -> None:
    """
    Writes the list of transactions to an Excel file with colored rows and a summary.
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "Categorized Transactions"

    ws.append(TRANSACTION_HEADERS)
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center")

    category_totals = defaultdict(float)
    grand_total = 0.0

    try:
        clean_data = [item for item in data if all(item[k] is not None for k in ["date", "description", "amount", "category"])]
        clean_data.sort(key=lambda x: datetime.strptime(x.get("date", "") + " 2025", "%d %b %Y"))
        if len(clean_data) < len(data):
             logging.warning(f"Skipped {len(data) - len(clean_data)} incomplete transactions during Excel write.")
        data = clean_data

    except (ValueError, TypeError):
        logging.warning("Date sorting failed due to invalid date format in some entries. Data will not be sorted by date.")

    for item in data:
        try:
            date = item["date"]
            description = item["description"]
            amount_raw = item["amount"]
            category = item["category"]
        except KeyError as e:
            logging.warning(f"Skipping row due to missing key '{e}' after correction attempts: {item}")
            continue

        row_to_write = [date, description, amount_raw, category]
        ws.append(row_to_write)

        fill_color = COLOR_MAP.get(category, DEFAULT_FILL_COLOR)
        current_row_index = ws.max_row
        for col_index in range(1, len(TRANSACTION_HEADERS) + 1):
            cell = ws.cell(row=current_row_index, column=col_index)
            cell.fill = PatternFill(start_color=fill_color, end_color=fill_color, fill_type="solid")
            cell.alignment = Alignment(horizontal="center")

        try:
            amount = float(amount_raw)
            category_totals[category] += amount
            grand_total += amount
        except (ValueError, TypeError):
            logging.warning(f"Skipping amount '{amount_raw}' for category '{category}' "
                            f"as it could not be converted to a number during Excel write. Item: {item}")
            continue

    ws.append([])

    # Track the row where the summary section begins
    summary_section_start_row = ws.max_row + 1

    # Add "Summary" title row
    ws.append(["Summary"])
    summary_row_idx = ws.max_row

    # Merge cells A:D in "Summary" row
    ws.merge_cells(start_row=summary_row_idx, start_column=1, end_row=summary_row_idx, end_column=3)

    # Format merged cell
    summary_title_cell = ws.cell(row=summary_row_idx, column=1)
    summary_title_cell.font = Font(bold=True, size=14)
    summary_title_cell.alignment = Alignment(horizontal="center")

    # Add headers
    ws.append(SUMMARY_HEADERS)
    for cell in ws[ws.max_row]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center")
        cell.fill = PatternFill(
            start_color=SUMMARY_HEADER_FILL_COLOR,
            end_color=SUMMARY_HEADER_FILL_COLOR,
            fill_type="solid"
        )

    num_category_summary_rows = 0
    for category, total in category_totals.items():
        percent = (total / grand_total) * 100 if grand_total != 0 else 0
        ws.append([category, round(total, 2), round(percent, 2)])

        row_idx = ws.max_row  # Get the current row index just appended
        for col_idx in range(1, len(SUMMARY_HEADERS) + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            cell.alignment = Alignment(horizontal="center")  # ✅ Ensure it's centered

        num_category_summary_rows += 1


    for col_idx, column_cells in enumerate(ws.iter_cols(), start=1):
        max_length = 0
        for cell in column_cells:
            cell_value_str = str(cell.value) if cell.value is not None else ""
            if len(cell_value_str) > max_length:
                max_length = len(cell_value_str)
        adjusted_width = max_length + 2
        ws.column_dimensions[column_cells[0].column_letter].width = adjusted_width

    try:
        wb.save(output_path)
        logging.info(f"Successfully saved Excel to {output_path}")
    except Exception as e:
        logging.error(f"Failed to save Excel file to {output_path}: {e}")
