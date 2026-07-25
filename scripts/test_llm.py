import os
import litellm
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("OPENROUTER_API")
prompt = """OUTPUT FORMAT:
You MUST return ONLY a single valid JSON object inside a ```json ... ``` markdown code block.
Do NOT include any explanations, reasoning, or text outside the JSON block.
Ensure all quotes inside the text are properly escaped.

```json
{
  "x_post": "<x text here>",
  "instagram_post": "<instagram text here>",
  "linkedin_post": "<linkedin text here>"
}
```
"""

try:
    response = litellm.completion(
        model="openrouter/nvidia/nemotron-3-super-120b-a12b:free",
        messages=[{"role": "user", "content": prompt}],
        api_key=api_key
    )
    content = response.choices[0].message.content
    print("--- RAW CONTENT ---")
    print(content)
    print("-------------------")
except Exception as e:
    print(e)
