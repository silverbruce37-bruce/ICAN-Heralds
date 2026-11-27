import json
import os
import requests

PROJECT_DIR = "/Users/worker64/Desktop/Desktop - W1 - Mac Studio(64gb)/ICAN-Heralds"
DAILY_FILE = f"{PROJECT_DIR}/data/daily-2026-05-01.json"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

with open(DAILY_FILE, "r") as f:
    daily_data = json.load(f)

prompt = f"You are an educational content designer for ICAN Academy. Based on this daily news JSON, generate background knowledge layers for each article. {json.dumps(daily_data)} Return ONLY valid JSON with 4 layers per article (cover, featured, news_1-4), depth 1-4, where depth 4 is an article-specific debate layer with debate_en and debate_kr."

url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent?key={GEMINI_API_KEY}"
payload = {"contents": [{"parts": [{"text": prompt}]}]}

res = requests.post(url, json=payload)
print(f"Status: {res.status_code}")
print(f"Response: {res.text[:2000]}")
