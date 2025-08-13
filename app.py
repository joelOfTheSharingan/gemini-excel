from flask import Flask, render_template, request, send_file
from PyPDF2 import PdfReader
import uuid
import io

# Import the new, in-memory capable processor
from processor import process_transactions_data

app = Flask(__name__)

def pdf_to_text(pdf_file_stream):
    """Extracts text from a PDF file stream and returns it as a string."""
    try:
        reader = PdfReader(pdf_file_stream)
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        return text
    except Exception as e:
        print(f"❌ Error during PDF text extraction: {e}")
        return None

@app.route('/')
def index():
    return render_template("index.html")

@app.route('/upload', methods=['POST'])
def upload_pdf():
    if 'file' not in request.files:
        return "No file uploaded", 400

    file = request.files['file']
    if file.filename == '':
        return "No selected file", 400

    # Read the file into an in-memory stream (BytesIO)
    pdf_file_stream = io.BytesIO(file.read())
    
    try:
        text_content = pdf_to_text(pdf_file_stream)
        if not text_content:
            return "Failed to extract text from PDF.", 500

        # Pass the text content directly to the processor
        processing_result = process_transactions_data(text_content)
        
        if processing_result['status'] == 'success':
            excel_data = processing_result['excel_data']
            output_filename = f"Categorized_Statement_{uuid.uuid4().hex}.xlsx"
            
            # Use send_file to serve the in-memory data
            return send_file(
                io.BytesIO(excel_data),
                download_name=output_filename,
                as_attachment=True,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
        else:
            return render_template("index.html", error_message=processing_result.get('error_message'))

    except Exception as e:
        error_message = f"An error occurred during file processing: {str(e)}"
        return render_template("index.html", error_message=error_message)

if __name__ == "__main__":
    app.run(port=5001, debug=True)