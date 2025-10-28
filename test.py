import google.generativeai as genai

genai.configure(api_key="AIzaSyDyI7ihTGRkU8x5v3XoBtDv7nwzNW0vgGk")
model = genai.GenerativeModel("gemini-2.5-flash-preview-05-20")

prompt = "List 2 fake transactions in JSON format with date, description, amount, and category."
print("Sending test request...")
response = model.generate_content(prompt)
print("Response:", response.text)
