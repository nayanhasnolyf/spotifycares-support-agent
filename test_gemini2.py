import google.genai as genai
client = genai.Client()
for i in range(20):
    try:
        client.models.generate_content(model='gemini-3.6-flash', contents='test')
    except Exception as e:
        print(f'details: {getattr(e, "details", None)}')
        print(f'message: {getattr(e, "message", None)}')
        break
