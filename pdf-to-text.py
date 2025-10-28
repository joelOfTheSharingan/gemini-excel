import PyPDF2

def check_pdf_password():
    pdf_path = "/Users/kids/Downloads/input.pdf"
    password = input("Enter password: ").strip()

    try:
        with open(pdf_path, "rb") as file:
            reader = PyPDF2.PdfReader(file)
            if reader.is_encrypted:
                if reader.decrypt(password):
                    print("✅ Password is correct!")
                else:
                    print("❌ Wrong password.")
            else:
                print("This PDF is not locked.")
    except FileNotFoundError:
        print("❌ File not found.")
    except Exception as e:
        print(f"⚠️ Error: {e}")

if __name__ == "__main__":
    check_pdf_password()
