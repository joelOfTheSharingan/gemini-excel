import os
import uuid
import logging
import io
import json
from testGeminiExcel import classify_transactions, write_to_excel, COLOR_MAP

def find_next_missing_field(data):
    required_fields = ["date", "description", "amount", "category"]
    for i, tx in enumerate(data):
        for field in required_fields:
            if tx.get(field) is None or str(tx.get(field, '')).strip().lower() == "missing" or str(tx.get(field, '')).strip() == "":
                return i, field, tx
    return None, None, None

def process_transactions_data(text_content):
    """
    Processes transaction text content directly (no file I/O).
    
    Args:
        text_content (str): The text to be processed.
        
    Returns:
        dict: A response dictionary containing status, console output, and Excel data (if successful).
    """
    log_stream = io.StringIO()
    root_logger = logging.getLogger()
    if root_logger.handlers:
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(logging.StreamHandler(log_stream))

    if not text_content.strip():
        return {
            "status": "error",
            "error_message": "Uploaded text is empty.",
            "console_output": log_stream.getvalue()
        }

    try:
        logging.info("Starting transaction classification...")

        data, needs_initial_correction = classify_transactions(text_content)
        tx_index, field_name, current_tx = find_next_missing_field(data)

        if needs_initial_correction and tx_index is not None:
            return {
                "status": "waiting_for_input",
                "console_output": log_stream.getvalue(),
                "next_correction": {
                    "index": tx_index,
                    "field": field_name,
                    "description": current_tx.get('description', 'N/A'),
                    "current_value": current_tx.get(field_name)
                },
                "categories": list(COLOR_MAP.keys())
            }
        else:
            # Create an in-memory stream to hold the Excel data
            excel_file_stream = io.BytesIO()
            write_to_excel(data, excel_file_stream)
            excel_file_stream.seek(0) # Rewind the stream to the beginning

            return {
                "status": "success",
                "excel_data": excel_file_stream.getvalue(),
                "console_output": log_stream.getvalue()
            }

    except Exception as e:
        logging.error(f"Unhandled exception: {e}", exc_info=True)
        return {
            "status": "error",
            "error_message": f"Error processing text: {str(e)}",
            "console_output": log_stream.getvalue()
        }