import litellm
from src.config import load_config

config = load_config()
api_key = config.get("OPENROUTER_API")

prompt = "Convert this to JSON with keys 'x', 'ig', 'li':\nX: Hello\nIG: World\nLI: Test"
system_prompt = (
    "You are a strict JSON data generator. You MUST output ONLY valid JSON. "
    "Do not include any conversational text, explanations, or reasoning."
)

response = litellm.completion(
    model="openrouter/google/gemma-4-26b-a4b-it:free",
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt}
    ],
    api_key=api_key,
    max_tokens=500,
    response_format={"type": "json_object"}
)
print("OUTPUT:")
print(response.choices[0].message.content)
