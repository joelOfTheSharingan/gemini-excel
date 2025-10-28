import os
import uuid
import logging
import io
import json
import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted
from testGeminiExcel import classify_transactions, write_to_excel, COLOR_MAP

# -------------------------------
# Gemini API Configuration
# -------------------------------
genai.configure(api_key="AIzaSyDyI7ihTGRkU8x5v3XoBtDv7nwzNW0vgGk")
model = genai.GenerativeModel("gemini-2.0-flash")


# -------------------------------
# Helper: find missing field
# -------------------------------
def find_next_missing_field(data):
    """Return the first transaction missing any required field."""
    required_fields = ["date", "description", "amount", "category"]
    for i, tx in enumerate(data):
        for field in required_fields:
            value = str(tx.get(field, "")).strip().lower()
            if value in ("", "missing", "none"):
                return i, field, tx
    return None, None, None


# -------------------------------
# Core: Process PDF text content
# -------------------------------
def process_transactions_data(text_content):
    """Extracts structured transaction data from text using Gemini and returns Excel bytes."""
    try:
        print("⚙️ Sending request to Gemini API...")

        prompt = (
            "Extract structured transaction data from the following text. "
            "Output **only** valid JSON as a list of objects with fields: "
            "date, description, amount, and category. Do not include explanations or markdown.\n\n"
            f"{text_content}"
        )

        response = model.generate_content(prompt)
        print("✅ Gemini API responded.")

        # Get response text safely
        response_text = getattr(response, "text", "")
        if not response_text.strip():
            raise ValueError("Empty response received from Gemini API.")

        # Extract the JSON part if Gemini adds extra commentary
        json_start = response_text.find("[")
        json_end = response_text.rfind("]") + 1
        if json_start == -1 or json_end == 0:
            raise ValueError("No valid JSON array found in Gemini response.")

        cleaned_json = response_text[json_start:json_end]
        data = json.loads(cleaned_json)

        # Ensure data is a list of dicts
        if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
            raise TypeError(f"Expected list of dictionaries, got: {type(data)} with elements of {[type(i) for i in data]}")

        # Classify and write Excel
        classified_data = classify_transactions(data)
        # If classify_transactions returns a tuple, unpack it
        if isinstance(classified_data, tuple):
            classified_data, _ = classified_data

        # Ensure classification didn’t double-wrap
        if isinstance(classified_data, list) and isinstance(classified_data[0], list):
            classified_data = classified_data[0]

        excel_data = write_to_excel(classified_data, COLOR_MAP)

        return {
            "status": "success",
            "excel_data": excel_data,
            "data": classified_data
        }

    except ResourceExhausted:
        print("❌ Gemini quota exceeded.")
        return {
            "status": "error",
            "error_message": "Gemini quota exceeded. Please check your API limits."
        }

    except Exception as e:
        logging.exception("⚠️ Unexpected error while processing transactions:")
        return {
            "status": "error",
            "error_message": str(e)
        }
