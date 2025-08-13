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
import io

genai.configure(api_key="AIzaSyBtDDwp31dKN7yDv-yRJOiONBtWXjw9XSU") 
model = genai.GenerativeModel("gemini-2.5-flash-preview-05-20")

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
    prompt = f"""
You are a financial statement parser.
Your task is to extract a clean list of financial transactions from the provided input text.
The output must be a valid JSON list of dictionaries. Each dictionary must represent a single transaction
and contain the following fields:
- "date": The date of the transaction. Format as "DD Mon" (e.g., "12 Jul", "04 Mar").
            If the date is missing or unclear, set this field to "Missing".
- "description": A concise summary of the transaction (e.g., "Uber ride", "Electricity bill", "Supermarket purchase").
            If the description is missing or unclear, set this field to "Missing".
- "amount": The numeric value of the transaction, without any currency symbols, commas, or other non-numeric characters.
            Ensure it can be parsed as a floating-point number.
            If the amount is missing or unclear, set this field to "Missing".
- "category": The classified category for the transaction. Choose one of the following exact categories:
  - "Food" (e.g., groceries, restaurants, snacks, cafes, dining)
  - "Travel" (e.g., taxis, Uber, buses, trains, flights, tolls, public transport)
  - "Bills" (e.g., electricity, water, rent, phone, internet, DTH, utilities, subscriptions)
  - "Fuel" (e.g., petrol, diesel, gasoline, car charging)
  - "Health" (e.g., medicine, hospitals, tests, clinics, pharmacy)
  - "Others" (Any transaction that does not clearly fit into the above categories)

### Output Format Strict Rules:
- Your response MUST be a pure JSON list. DO NOT include any explanatory text, markdown code blocks (e.g., ```json), or any other formatting outside the JSON array.
- Use the EXACT field names: "date", "description", "amount", "category".
- If any required field's value cannot be confidently extracted or is completely absent, set its value to the string "Missing".
- Ensure the JSON is well-formed and valid.

### Example Expected Output:
[
  {{
    "date": "12 Jul",
    "description": "Uber ride",
    "amount": "650.00",
    "category": "Travel"
  }},
  {{
    "date": "01 Aug",
    "description": "Electricity bill",
    "amount": "1250.75",
    "category": "Bills"
  }},
  {{
    "date": "Missing",
    "description": "Unknown transaction",
    "amount": "Missing",
    "category": "Others"
  }}
]

### Input Text:
{text}
"""
    needs_correction = False
    try:
        response = model.generate_content(prompt)
        logging.info(f"[DEBUG] Raw Gemini response:\n{response.text}")
        json_text = re.sub(r'```(?:json)?|```', '', response.text).strip()
        logging.info(f"[DEBUG] Cleaned JSON text for parsing:\n{json_text}")
        data = json.loads(json_text)
        if not isinstance(data, list):
            raise ValueError("Gemini response is not a JSON list. Expected a list of transactions.")
        required_fields = ["date", "description", "amount", "category"]
        for i, tx in enumerate(data):
            if not isinstance(tx, dict):
                logging.error(f"Transaction at index {i} is not a dictionary. Skipping it.")
                continue
            for field in required_fields:
                if field not in tx or not tx[field] or str(tx[field]).strip().lower() == "missing":
                    logging.warning(f"Missing or invalid '{field}' for transaction {i+1} ('{tx.get('description', 'N/A')}'). Marking for correction.")
                    tx[field] = None
                    needs_correction = True
            if tx.get("amount") is not None:
                try:
                    tx["amount"] = str(float(tx["amount"]))
                except (ValueError, TypeError):
                    logging.warning(f"Invalid amount format '{tx.get('amount')}' for transaction {i+1} ('{tx.get('description', 'N/A')}'). Marking for correction.")
                    tx["amount"] = None
                    needs_correction = True
        logging.info(f"[DEBUG] Final parsed transactions (with None for missing fields) before frontend correction:\n{data}")
        return data, needs_correction
    except json.JSONDecodeError as e:
        logging.error(f"JSON decode error in Gemini response: {e}. Raw response was: {response.text}")
        raise ValueError(f"Invalid JSON format received from the model. Please check the model's output: {e}")
    except ValueError as e:
        logging.error(f"Data validation error after parsing: {e}")
        raise
    except Exception as e:
        logging.error(f"An unexpected error occurred during transaction classification: {e}", exc_info=True)
        raise

def write_to_excel(data: list[dict], file_stream: io.BytesIO) -> None:
    """
    Writes the list of transactions to an Excel file in an in-memory stream.
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

    clean_data = []
    for item in data:
        if all(item.get(k) is not None for k in ["date", "description", "amount", "category"]):
            clean_data.append(item)
        else:
            logging.warning(f"Skipping incomplete transaction during Excel write due to missing data: {item}")

    try:
        current_year = datetime.now().year
        clean_data.sort(key=lambda x: datetime.strptime(f"{x.get('date')} {current_year}", "%d %b %Y"))
        logging.info("Transactions sorted by date for Excel output.")
    except (ValueError, TypeError) as e:
        logging.warning(f"Date sorting failed due to invalid date format in some entries ({e}). Data will be written unsorted.")

    for item in clean_data:
        try:
            date = item["date"]
            description = item["description"]
            amount_raw = item["amount"]
            category = item["category"]
        except KeyError as e:
            logging.error(f"Critical: Missing expected key '{e}' in transaction item during Excel write. This item should have been filtered: {item}")
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
                            f"during Excel total calculation as it could not be converted to a number. Item: {item}")
            continue

    ws.append([])
    summary_title_row_idx = ws.max_row + 1
    ws.append(["Summary"])
    ws.merge_cells(start_row=summary_title_row_idx, start_column=1, end_row=summary_title_row_idx, end_column=3)

    summary_title_cell = ws.cell(row=summary_title_row_idx, column=1)
    summary_title_cell.font = Font(bold=True, size=14)
    summary_title_cell.alignment = Alignment(horizontal="center")

    ws.append(SUMMARY_HEADERS)
    for cell in ws[ws.max_row]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center")
        cell.fill = PatternFill(
            start_color=SUMMARY_HEADER_FILL_COLOR,
            end_color=SUMMARY_HEADER_FILL_COLOR,
            fill_type="solid"
        )

    for category in sorted(category_totals.keys()):
        total = category_totals[category]
        percent = (total / grand_total) * 100 if grand_total != 0 else 0
        ws.append([category, round(total, 2), round(percent, 2)])

        row_idx = ws.max_row
        for col_idx in range(1, len(SUMMARY_HEADERS) + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            cell.alignment = Alignment(horizontal="center")

    for col_idx, column_cells in enumerate(ws.iter_cols(), start=1):
        max_length = 0
        for cell in column_cells:
            cell_value_str = str(cell.value) if cell.value is not None else ""
            if len(cell_value_str) > max_length:
                max_length = len(cell_value_str)
        adjusted_width = max_length + 2
        ws.column_dimensions[column_cells[0].column_letter].width = adjusted_width

    try:
        # Save the workbook to the in-memory stream
        wb.save(file_stream)
        logging.info("Successfully saved Excel to in-memory stream.")
    except Exception as e:
        logging.error(f"Failed to save Excel file to stream: {e}", exc_info=True)