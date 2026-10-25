import os, json, re
import google.generativeai as genai
from PIL import Image

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-1.5-flash")

PROMPT = """Ты нутрициолог. Посмотри на фото еды и верни СТРОГО JSON без markdown:
{
  "dish_name": "название блюда по-русски",
  "kcal_per_100g": число,
  "grams_per_plate": число,
  "confidence": "high|medium|low"
}
grams_per_plate — примерный вес одной стандартной порции/тарелки на фото в граммах.
Если на фото несколько блюд — верни массив объектов в поле "items".
"""

def analyze_food(image_path: str) -> dict:
    img = Image.open(image_path)
    resp = model.generate_content([PROMPT, img])
    text = re.sub(r"```json|```", "", resp.text).strip()
    return json.loads(text)
