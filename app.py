from flask import Flask, render_template, request, jsonify, send_from_directory, session
import os
import uuid
import logging
import io
import json

# Assuming testGeminiExcel.py is in the same directory
from testGeminiExcel import classify_transactions, write_to_excel, COLOR_MAP

app = Flask(__name__)
app.secret_key = 'your_super_secret_key_here_change_this_in_production'

UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'download')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Helper to capture log messages into a string stream for frontend display
class StringIOHandler(logging.Handler):
    def __init__(self, stream):
        super().__init__()
        self.stream = stream
        self.formatter = logging.Formatter('%(levelname)s: %(message)s')

    def emit(self, record):
        msg = self.format(record)
        self.stream.write(msg + '\n')

log_stream = io.StringIO()
root_logger = logging.getLogger()
if root_logger.handlers:
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
root_logger.setLevel(logging.INFO)
root_logger.addHandler(StringIOHandler(log_stream))
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
root_logger.addHandler(console_handler)

# Helper function to find the first missing field in the transactions data
def find_next_missing_field(data):
    required_fields = ["date", "description", "amount", "category"]
    for i, tx in enumerate(data):
        for field in required_fields:
            # Check for None, "Missing" as a string, or an empty string
            if tx.get(field) is None or str(tx.get(field, '')).strip().lower() == "missing" or str(tx.get(field, '')).strip() == "":
                logging.debug(f"Found missing field: Transaction {i+1}, Field '{field}'")
                return i, field, tx # Return index, field name, and the transaction
    logging.debug("No missing fields found.")
    return None, None, None # No missing fields

@app.route("/", methods=["GET", "POST"])
def index():
    """Handles the initial file upload and classification."""
    if request.method == "GET":
        return render_template("index.html", categories=list(COLOR_MAP.keys()))

    log_stream.seek(0)
    log_stream.truncate(0)
    
    file = request.files.get("file")
    if not file or not file.filename.endswith(".txt"):
        response_data = {
            "status": "error",
            "error_message": "Please upload a valid .txt file.",
            "console_output": log_stream.getvalue()
        }
        logging.info(f"Sending response: {json.dumps(response_data, indent=2)}")
        return jsonify(response_data)

    try:
        file_content = file.read()
        if len(file_content) > 5 * 1024 * 1024:
            response_data = {
                "status": "error",
                "error_message": "File is too large. Maximum size is 5MB.",
                "console_output": log_stream.getvalue()
            }
            logging.info(f"Sending response: {json.dumps(response_data, indent=2)}")
            return jsonify(response_data)
        elif not file_content.strip():
            response_data = {
                "status": "error",
                "error_message": "Uploaded file is empty.",
                "console_output": log_stream.getvalue()
            }
            logging.info(f"Sending response: {json.dumps(response_data, indent=2)}")
            return jsonify(response_data)
        else:
            text = file_content.decode("utf-8")
            logging.info("Starting transaction classification...")

            data, needs_initial_correction = classify_transactions(text)

            # Store the data in session for subsequent correction steps
            session['transactions_data'] = data

            tx_index, field_name, current_tx = find_next_missing_field(data)

            if needs_initial_correction and tx_index is not None:
                logging.warning(f"Missing data detected. Asking for correction for Transaction {tx_index + 1}, field: '{field_name}'.")
                response_data = {
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
                logging.info(f"Sending response: {json.dumps(response_data, indent=2)}")
                return jsonify(response_data)
            else:
                logging.info("No missing data detected. Proceeding to Excel generation.")
                output_filename = f"Categorized_Statement_{uuid.uuid4().hex}.xlsx"
                output_path = os.path.join(UPLOAD_FOLDER, output_filename)
                write_to_excel(data, output_path)

                if os.path.exists(output_path):
                    download_link = f"/download/{output_filename}"
                    logging.info(f"Excel file generated successfully: {output_filename}")
                    response_data = {
                        "status": "success",
                        "download_link": download_link,
                        "console_output": log_stream.getvalue()
                    }
                    logging.info(f"Sending response: {json.dumps(response_data, indent=2)}")
                    return jsonify(response_data)
                else:
                    logging.error("Excel file was not created.")
                    response_data = {
                        "status": "error",
                        "error_message": "File generation failed. Please try again.",
                        "console_output": log_stream.getvalue()
                    }
                    logging.info(f"Sending response: {json.dumps(response_data, indent=2)}")
                    return jsonify(response_data)

    except UnicodeDecodeError:
        logging.error("UnicodeDecodeError: Invalid file encoding.")
        response_data = {
            "status": "error",
            "error_message": "Invalid file encoding. Please upload a UTF-8 encoded .txt file.",
            "console_output": log_stream.getvalue()
        }
        logging.info(f"Sending response: {json.dumps(response_data, indent=2)}")
        return jsonify(response_data)
    except Exception as e:
        logging.error(f"Unhandled exception during file processing: {e}", exc_info=True)
        response_data = {
            "status": "error",
            "error_message": f"Error processing file: {str(e)}. Please ensure the file contains valid transaction data.",
            "console_output": log_stream.getvalue()
        }
        logging.info(f"Sending response: {json.dumps(response_data, indent=2)}")
        return jsonify(response_data)

@app.route("/submit_single_correction", methods=["POST"])
def submit_single_correction():
    """Handles a single value correction from the user via the console."""
    log_stream.seek(0)
    log_stream.truncate(0)

    try:
        data_from_frontend = request.get_json()
        corrected_value = data_from_frontend.get("value")
        tx_index = data_from_frontend.get("index")
        field_name = data_from_frontend.get("field")
        
        logging.info(f"Received correction for: Transaction {tx_index}, Field '{field_name}' = '{corrected_value}'")

        transactions_data = session.get('transactions_data')

        if transactions_data is None or tx_index is None or field_name is None:
            logging.error("Session data or correction context missing.")
            response_data = {
                "status": "error",
                "error_message": "Session data or correction context missing. Please re-upload.",
                "console_output": log_stream.getvalue()
            }
            logging.info(f"Sending response: {json.dumps(response_data, indent=2)}")
            return jsonify(response_data)

        if not (0 <= tx_index < len(transactions_data)):
            logging.error(f"Invalid transaction index: {tx_index}")
            response_data = {
                "status": "error",
                "error_message": "Invalid transaction index received.",
                "console_output": log_stream.getvalue()
            }
            logging.info(f"Sending response: {json.dumps(response_data, indent=2)}")
            return jsonify(response_data)

        # Apply the correction
        logging.info(f"Applying correction: Transaction {tx_index + 1}, Field '{field_name}' = '{corrected_value}'")
        transactions_data[tx_index][field_name] = corrected_value

        # Re-validate the corrected field if it's an amount
        if field_name == "amount":
            try:
                transactions_data[tx_index]["amount"] = str(float(corrected_value))
            except ValueError:
                transactions_data[tx_index]["amount"] = None
                logging.warning(f"Invalid amount entered: '{corrected_value}'. Please re-enter.")
                response_data = {
                    "status": "waiting_for_input",
                    "console_output": log_stream.getvalue(),
                    "next_correction": {
                        "index": tx_index,
                        "field": field_name,
                        "description": transactions_data[tx_index].get('description', 'N/A'),
                        "current_value": transactions_data[tx_index].get(field_name)
                    },
                    "categories": list(COLOR_MAP.keys())
                }
                logging.info(f"Sending response: {json.dumps(response_data, indent=2)}")
                return jsonify(response_data)

        # Find the next missing field in the updated data
        next_tx_index, next_field_name, next_tx = find_next_missing_field(transactions_data)
        if next_tx_index is not None:
            logging.warning(f"More missing data detected. Asking for correction for Transaction {next_tx_index + 1}, field: '{next_field_name}'.")
            response_data = {
                "status": "waiting_for_input",
                "console_output": log_stream.getvalue(),
                "next_correction": {
                    "index": next_tx_index,
                    "field": next_field_name,
                    "description": next_tx.get('description', 'N/A'),
                    "current_value": next_tx.get(next_field_name)
                },
                "categories": list(COLOR_MAP.keys())
            }
            logging.info(f"Sending response: {json.dumps(response_data, indent=2)}")
            return jsonify(response_data)
        else:
            # All corrections are done, proceed to Excel generation
            logging.info("All corrections applied. Proceeding to Excel generation.")
            output_filename = f"Categorized_Statement_{uuid.uuid4().hex}.xlsx"
            output_path = os.path.join(UPLOAD_FOLDER, output_filename)
            write_to_excel(transactions_data, output_path)
            session.pop('transactions_data', None) # Clear session data

            if os.path.exists(output_path):
                download_link = f"/download/{output_filename}"
                logging.info(f"Excel file generated successfully: {output_filename}")
                response_data = {
                    "status": "success",
                    "download_link": download_link,
                    "console_output": log_stream.getvalue()
                }
                logging.info(f"Sending response: {json.dumps(response_data, indent=2)}")
                return jsonify(response_data)
            else:
                logging.error("Excel file was not created.")
                response_data = {
                    "status": "error",
                    "error_message": "File generation failed. Please try again.",
                    "console_output": log_stream.getvalue()
                }
                logging.info(f"Sending response: {json.dumps(response_data, indent=2)}")
                return jsonify(response_data)

    except Exception as e:
        logging.error(f"Unhandled exception during correction submission: {e}", exc_info=True)
        response_data = {
            "status": "error",
            "error_message": f"An error occurred during correction: {str(e)}",
            "console_output": log_stream.getvalue()
        }
        logging.info(f"Sending response: {json.dumps(response_data, indent=2)}")
        return jsonify(response_data)

@app.route("/download/<filename>")
def download_file(filename):
    """Allows the user to download the generated Excel file."""
    try:
        return send_from_directory(UPLOAD_FOLDER, filename, as_attachment=True)
    except FileNotFoundError:
        return render_template("index.html", error_message="File not found. Please try uploading again.")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=True)
