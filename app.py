from flask import Flask, render_template, request, send_file
from PyPDF2 import PdfReader
import uuid
import io
import os

from processor import process_transactions_data  # Import the in-memory capable processor

app = Flask(__name__)

def pdf_to_text(pdf_stream):
    """Extracts and returns all text from a PDF file stream."""
    try:
        reader = PdfReader(pdf_stream)
        return "\n".join(
            filter(None, (page.extract_text() for page in reader.pages))
        )
    except Exception as e:
        print(f"[ERROR] PDF text extraction failed: {e}")
        return None


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload_pdf():
    file = request.files.get("file")
    
    if not file or file.filename.strip() == "":
        return "No file uploaded", 400

    pdf_stream = io.BytesIO(file.read())
    text_content = pdf_to_text(pdf_stream)

    if not text_content:
        return "Failed to extract text from PDF.", 500

    try:
        result = process_transactions_data(text_content)
        
        if result.get("status") != "success":
            return render_template("index.html", error_message=result.get("error_message", "Processing failed."))

        excel_data = result["excel_data"]
        filename = f"Categorized_Statement_{uuid.uuid4().hex}.xlsx"

        return send_file(
            io.BytesIO(excel_data),
            download_name=filename,
            as_attachment=True,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    except Exception as e:
        return render_template("index.html", error_message=f"Processing error: {e}")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

