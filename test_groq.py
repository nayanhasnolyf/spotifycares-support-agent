import os
import httpx
response = httpx.post(
    'https://api.groq.com/openai/v1/chat/completions',
    headers={'Authorization': f"Bearer {os.environ.get('GROQ_API_KEY')}"},
    json={'model': 'openai/gpt-oss-20b', 'messages': [{'role': 'user', 'content': 'test'}]}
)
print(response.status_code, response.text)
