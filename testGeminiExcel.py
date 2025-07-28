import google.generativeai as genai
import pandas as pd
import json
import re
import os
from openpyxl import Workbook
from openpyxl import load_workbook
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Alignment, Font # Added Font for potential header styling
from collections import defaultdict
from datetime import datetime
import logging

genai.configure(api_key="AIzaSyCK6TUjndLC631MFMhzceS3isC6vghgvIk")
model = genai.GenerativeModel("gemini-1.5-flash")

def classify_transactions(text):
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

    try:
        response = model.generate_content(prompt)
        print(f"[DEBUG] Raw Gemini response:\n{response.text}")

        # Strip Markdown formatting
        json_text = re.sub(r'```(?:json)?|```', '', response.text).strip()
        print(f"[DEBUG] Cleaned JSON text:\n{json_text}")

        data = json.loads(json_text)
        if not isinstance(data, list):
            raise ValueError("Response is not a JSON list")

        # Validate and clean
        required_fields = ["date", "description", "amount", "category"]
        for tx in data:
            if not isinstance(tx, dict):
                raise ValueError("Transaction is not a dictionary")
            for field in required_fields:
                if field not in tx or not tx[field] or str(tx[field]).strip().lower() == "missing":
                    # Ask the user to fill in missing fields
                    desc = ", ".join(f"{k}: {tx.get(k, '?')}" for k in required_fields if k != field)
                    user_input = input(f"Enter the missing value for '{field}' ({desc}): ")
                    tx[field] = user_input if field != "amount" else str(float(user_input))
            try:
                tx["amount"] = str(float(tx["amount"]))
            except (ValueError, TypeError):
                print(f"[DEBUG] Invalid amount in transaction: {tx}")
                tx["amount"] = "0.0"

        print(f"[DEBUG] Final parsed transactions:\n{data}")
        return data

    except json.JSONDecodeError as e:
        print(f"❌ JSON decode error: {e}")
        raise ValueError(f"Invalid JSON format in Gemini response: {e}")
    except ValueError as e:
        print(f"❌ Validation error: {e}")
        raise
    except Exception as e:
        print(f"❌ Error in classify_transactions: {e}")
        raise


CATEGORY_COLORS = {
    "Food": "FFE599",     # light yellow
    "Travel": "CFE2F3",   # light blue
    "Bills": "F4CCCC",    # light red
    "Fuel": "D9D2E9",     # light purple
    "Health": "D0E0E3",   # light aqua
    "Others": "EAD1DC",   # light pink
}

def parse_date(date_str):
    try:
        return datetime.strptime(date_str + " 2025", "%d %b %Y")
    except Exception:
        return datetime(1900, 1, 1)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

# Hexadecimal color codes for cell fills - ADJUSTED TO MATCH GEMINI'S OUTPUT CATEGORIES
COLOR_MAP = {
    "Food": "FFEB9C",        # Light yellow
    "Travel": "C6EFCE",      # Light green (mapped from "Transport")
    "Bills": "FFCDD2",       # Light red (mapped from "Shopping", "Utilities")
    "Fuel": "D9E1F2",        # Light blue
    "Health": "FCE4D6",      # Light orange
    "Others": "D9D2E9",      # Light purple (mapped from "Entertainment", "Other")
}

SUMMARY_HEADER_FILL_COLOR = "E2EFDA" # Light greenish-blue for summary header
TRANSACTION_HEADERS = ["Date", "Description", "Amount", "Category"]
SUMMARY_HEADERS = ["Category", "Total", "Percentage (%)"]
DEFAULT_FILL_COLOR = "FFFFFF" # White for unknown categories

def write_to_excel(data: list[dict], output_path: str) -> None:
    """
    Writes categorized transaction data to an Excel file with styling and a summary.

    Args:
        data (list[dict]): A list of dictionaries, where each dictionary
                           represents a transaction. Expected keys: "date" (str DD Mon),
                           "description" (str), "amount" (numeric or str convertible to float),
                           "category" (str).
        output_path (str): The file path where the Excel workbook will be saved.
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "Categorized Transactions"

    # --- Write Transaction Headers ---
    ws.append(TRANSACTION_HEADERS)
    # Optional: Apply bold font to headers
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center")

    category_totals = defaultdict(float)
    grand_total = 0.0

    # --- Sort Data by Date (CRITICAL FIX HERE) ---
    # The date format from classify_transactions is "DD Mon" (e.g., "12 Jul").
    # We append a default year (e.g., " 2025") to make it a full date string for parsing.
    try:
        # Use a lambda to parse dates for sorting
        data.sort(key=lambda x: datetime.strptime(x.get("date", "") + " 2025", "%d %b %Y"))
    except ValueError:
        logging.warning("Date sorting failed due to invalid date format in some entries. Data will not be sorted by date.")
    except TypeError:
        logging.warning("Date sorting failed due to non-string date values. Data will not be sorted by date.")


    # --- Process and Write Each Transaction Row ---
    for item in data:
        try:
            date = item["date"]
            description = item["description"]
            amount_raw = item["amount"]
            category = item["category"]
        except KeyError as e:
            logging.warning(f"Skipping row due to missing key '{e}': {item}")
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
                            f"as it could not be converted to a number. Item: {item}")
            continue

    # --- Write Summary Section ---
    ws.append([])
    summary_section_start_row = ws.max_row + 1

    ws.append(["Summary"])
    summary_title_cell = ws.cell(row=ws.max_row, column=1)
    summary_title_cell.font = Font(bold=True, size=14)
    summary_title_cell.alignment = Alignment(horizontal="center")

    ws.append(SUMMARY_HEADERS)
    for cell in ws[ws.max_row]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center")
        cell.fill = PatternFill(start_color=SUMMARY_HEADER_FILL_COLOR, end_color=SUMMARY_HEADER_FILL_COLOR, fill_type="solid")

    num_category_summary_rows = 0
    for category, total in category_totals.items():
        percent = (total / grand_total) * 100 if grand_total != 0 else 0
        ws.append([category, round(total, 2), round(percent, 2)])
        num_category_summary_rows += 1

    if num_category_summary_rows > 0:
        summary_data_min_row = summary_section_start_row + 2
        summary_data_max_row = summary_data_min_row + num_category_summary_rows - 1
        for row_idx in range(summary_data_min_row, summary_data_max_row + 1):
            for col_idx in range(1, len(SUMMARY_HEADERS) + 1):
                cell = ws.cell(row=row_idx, column=col_idx)
                cell.alignment = Alignment(horizontal="center")

    # --- Auto Adjust Column Width ---
    for col_idx, column_cells in enumerate(ws.iter_cols(), start=1):
        max_length = 0
        for cell in column_cells:
            cell_value_str = str(cell.value) if cell.value is not None else ""
            if len(cell_value_str) > max_length:
                max_length = len(cell_value_str)
        adjusted_width = max_length + 2
        ws.column_dimensions[column_cells[0].column_letter].width = adjusted_width

    # --- Save Workbook ---
    try:
        wb.save(output_path)
        logging.info(f"Successfully saved Excel to {output_path}")
    except Exception as e:
        logging.error(f"Failed to save Excel file to {output_path}: {e}")
