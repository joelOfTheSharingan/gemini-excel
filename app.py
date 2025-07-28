from flask import Flask, render_template, request, send_from_directory
import os
import uuid
from testGeminiExcel import classify_transactions, write_to_excel

app = Flask(__name__)
UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'download')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.route("/", methods=["GET", "POST"])
def index():
    file_uploaded = False
    download_ready = False
    error_message = None
    output_filename = f"Categorized_Statement_{uuid.uuid4().hex}.xlsx"

    if request.method == "POST":
        file = request.files.get("file")
        if file and file.filename.endswith(".txt"):
            try:
                # Validate file size (max 5MB)
                file_content = file.read()
                if len(file_content) > 5 * 1024 * 1024:
                    error_message = "File is too large. Maximum size is 5MB."
                elif len(file_content.strip()) == 0:
                    error_message = "Uploaded file is empty."
                else:
                    text = file_content.decode("utf-8")
                    data = classify_transactions(text)
                    if not data:
                        error_message = "No valid transactions extracted. Check file format or content."
                    else:
                        output_path = os.path.join(UPLOAD_FOLDER, output_filename)
                        write_to_excel(data, output_path)
                        file_uploaded = True
                        download_ready = os.path.exists(output_path)
            except UnicodeDecodeError:
                error_message = "Invalid file encoding. Please upload a UTF-8 encoded .txt file."
            except Exception as e:
                error_message = f"Error processing file: {str(e)}. Please ensure the file contains valid transaction data."
        else:
            error_message = "Please upload a valid .txt file."

    return render_template(
        "index.html",
        file_uploaded=file_uploaded,
        download_ready=download_ready,
        error_message=error_message,
        output_filename=output_filename
    )

@app.route("/download/<filename>")
def download_file(filename):
    try:
        return send_from_directory(UPLOAD_FOLDER, filename, as_attachment=True)
    except FileNotFoundError:
        return render_template("index.html", error_message="File not found. Please try uploading again.")

if __name__ == "__main__":
    app.run(debug=True)





