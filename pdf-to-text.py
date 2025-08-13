import PyPDF2

def pdf_to_text(pdf_path, txt_path):
    try:
        # Open the PDF file
        with open(pdf_path, 'rb') as pdf_file:
            reader = PyPDF2.PdfReader(pdf_file)
            text = ""

            # Loop through all pages and extract text
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"

        # Save the text to a file
        with open(txt_path, 'w', encoding='utf-8') as txt_file:
            txt_file.write(text)

        print(f"✅ Text extracted successfully to {txt_path}")

    except Exception as e:
        print(f"❌ Error: {e}")

# Example usage
pdf_to_text("input.pdf", "output.txt")
