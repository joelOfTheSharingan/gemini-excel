from flask import Flask, render_template, request, send_file
import io
import uuid
from PyPDF2 import PdfReader
from processor import process_transactions_data

app = Flask(__name__)

# Limit file size (10 MB)
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024


def pdf_to_text(pdf_file_stream):
    """Extract text from a PDF file object safely."""
    reader = PdfReader(pdf_file_stream)
    text = ""
    for page in reader.pages:
        # Handle pages where extract_text() returns None
        page_text = page.extract_text() or ""
        text += page_text + "\n"
    return text


@app.route('/')
def index():
    """Render the homepage."""
    return render_template("index.html")


@app.route('/upload', methods=['POST'])
def upload_pdf():
    """Handle PDF upload and processing."""
    file = request.files.get('file')

    # Validate file presence
    if not file or file.filename == '':
        return render_template("index.html", error_message="No file uploaded.")

    # Ensure it’s a PDF
    if not file.filename.lower().endswith('.pdf'):
        return render_template("index.html", error_message="Invalid file type. Please upload a PDF file.")

    # Convert PDF to text
    pdf_file_stream = io.BytesIO(file.read())
    try:
        text_content = pdf_to_text(pdf_file_stream)
    except Exception as e:
        return render_template("index.html", error_message=f"Failed to read PDF: {str(e)}")

    # Process the transactions using your Gemini-based function
    try:
        processing_result = process_transactions_data(text_content)
    except Exception as e:
        return render_template("index.html", error_message=f"Processing error: {str(e)}")

    # Handle result based on status
    if processing_result.get('status') == 'success' and 'excel_data' in processing_result:
        excel_data = processing_result['excel_data']
        output_filename = f"Categorized_Statement_{uuid.uuid4().hex}.xlsx"

        return send_file(
            io.BytesIO(excel_data),
            download_name=output_filename,
            as_attachment=True,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

    # Show an error on the page if unsuccessful
    return render_template("index.html", error_message=processing_result.get('error_message', 'Unknown error occurred during processing.'))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=False)
