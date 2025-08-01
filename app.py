from flask import Flask, render_template, request, jsonify, send_from_directory
import os
import uuid
import logging
import io

from testGeminiExcel import classify_transactions, write_to_excel, COLOR_MAP # Import COLOR_MAP for frontend validation

app = Flask(__name__) # CORRECTED LINE HERE

# Directory to save generated Excel files
UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'download')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# --- Custom Log Handler to capture output ---
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
# --- End Custom Log Handler ---


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "GET":
        return render_template("index.html", download_link="", error_message="", console_output="", categories=list(COLOR_MAP.keys()))

    # Clear the log stream for each new POST request
    log_stream.seek(0)
    log_stream.truncate(0)

    file = request.files.get("file")
    if not file or not file.filename.endswith(".txt"):
        return jsonify({
            "status": "error",
            "error_message": "Please upload a valid .txt file.",
            "console_output": log_stream.getvalue()
        })

    try:
        file_content = file.read()
        if len(file_content) > 5 * 1024 * 1024:
            return jsonify({
                "status": "error",
                "error_message": "File is too large. Maximum size is 5MB.",
                "console_output": log_stream.getvalue()
            })
        elif not file_content.strip():
            return jsonify({
                "status": "error",
                "error_message": "Uploaded file is empty.",
                "console_output": log_stream.getvalue()
            })
        else:
            text = file_content.decode("utf-8")
            logging.info("Starting transaction classification...")
            
            data, needs_correction = classify_transactions(text) # Get data and correction flag

            if needs_correction:
                logging.warning("Missing data detected. Sending data for user correction.")
                return jsonify({
                    "status": "needs_correction",
                    "data": data, # Send the data (with None for missing fields)
                    "console_output": log_stream.getvalue(),
                    "categories": list(COLOR_MAP.keys()) # Send categories for dropdown
                })
            else:
                logging.info("No missing data. Proceeding to Excel generation.")
                output_filename = f"Categorized_Statement_{uuid.uuid4().hex}.xlsx"
                output_path = os.path.join(UPLOAD_FOLDER, output_filename)
                write_to_excel(data, output_path)

                if os.path.exists(output_path):
                    download_link = f"/download/{output_filename}"
                    logging.info(f"Excel file generated successfully: {output_filename}")
                    return jsonify({
                        "status": "success",
                        "download_link": download_link,
                        "console_output": log_stream.getvalue()
                    })
                else:
                    logging.error("Excel file was not created.")
                    return jsonify({
                        "status": "error",
                        "error_message": "File generation failed. Please try again.",
                        "console_output": log_stream.getvalue()
                    })

    except UnicodeDecodeError:
        logging.error("UnicodeDecodeError: Invalid file encoding.")
        return jsonify({
            "status": "error",
            "error_message": "Invalid file encoding. Please upload a UTF-8 encoded .txt file.",
            "console_output": log_stream.getvalue()
        })
    except Exception as e:
        logging.error(f"Unhandled exception during file processing: {e}", exc_info=True)
        return jsonify({
            "status": "error",
            "error_message": f"Error processing file: {str(e)}. Please ensure the file contains valid transaction data.",
            "console_output": log_stream.getvalue()
        })

@app.route("/submit_corrections", methods=["POST"])
def submit_corrections():
    # Clear the log stream for this request
    log_stream.seek(0)
    log_stream.truncate(0)

    try:
        corrected_data = request.json.get("corrected_data")
        logging.info(f"Received corrections from frontend. Processing {len(corrected_data)} transactions.")

        output_filename = f"Categorized_Statement_{uuid.uuid4().hex}.xlsx"
        output_path = os.path.join(UPLOAD_FOLDER, output_filename)
        write_to_excel(corrected_data, output_path)

        if os.path.exists(output_path):
            download_link = f"/download/{output_filename}"
            logging.info(f"Excel file generated successfully after corrections: {output_filename}")
            return jsonify({
                "status": "success",
                "download_link": download_link,
                "console_output": log_stream.getvalue()
            })
        else:
            logging.error("Excel file was not created after corrections.")
            return jsonify({
                "status": "error",
                "error_message": "File generation failed after corrections. Please try again.",
                "console_output": log_stream.getvalue()
            })

    except Exception as e:
        logging.error(f"Error during correction submission: {e}", exc_info=True)
        return jsonify({
            "status": "error",
            "error_message": f"Error submitting corrections: {str(e)}",
            "console_output": log_stream.getvalue()
        })


@app.route("/download/<filename>")
def download_file(filename):
    try:
        return send_from_directory(UPLOAD_FOLDER, filename, as_attachment=True)
    except FileNotFoundError:
        logging.error(f"Download file not found: {filename}")
        return render_template("index.html", error_message="File not found. Please try uploading again.")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=True)
