import google.genai as genai
client = genai.Client()
for i in range(20):
    try:
        client.models.generate_content(model='gemini-2.5-flash', contents='test')
        print(f'{i} success')
    except Exception as e:
        print(f'Exception type: {type(e)}')
        print(f'code: {getattr(e, "code", getattr(e, "status_code", None))}')
        print(dir(e))
        break
