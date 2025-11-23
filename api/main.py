from dictionary import import_dictionary
from flask import Flask, request, jsonify, send_from_directory
from openai import OpenAI

# settings
API_KEY = "sk-hc-v1-getyourowndamnapikeyyousneakylittleapikeystealer"
MODEL = "google/gemini-2.5-flash"
SYSTEM_PROMPT = """
System:
Hello Gemini, you are now an AI model built into a system search bar. The user may ask you questions, or use you like a search engine.
You should try to make short and blunt responses while trying to give as much information as the user might need about their query.
You should go by the name FrameDock if asked, though, if they press you can mention you are Google's model. You dont have access to tools here.
Avoid emojis or anything OTHER THAN # ## ## *word* **word** for markdown, as they are NOT supported. Thank you.
User:
"""

data = import_dictionary()
client = OpenAI(api_key=API_KEY, base_url="https://ai.hackclub.com/proxy/v1")

app = Flask(__name__)

# documentation endpoint
@app.get("/docs")
def docs_index():
    return send_from_directory("docs", "index.html")

@app.get("/framedocklogo.png")
def docs_static():
    return send_from_directory("docs", "framedocklogo.png")

# dictionary endpoint
@app.get("/lookup/<word>")
def lookup(word):
    w = word.lower()
    if w in data:
        return jsonify({"word": w, "meanings": data[w]})
    return jsonify({"error": "not found"}), 404

# llm question endpoint (hackclub proxy ai proxy... proxy squared?)
@app.get("/ai/question/<path:query>")
def ask(query):
    r = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": query}
        ]
    )
    return jsonify({"answer": r.choices[0].message.content})

if __name__ == "__main__":
    app.run("0.0.0.0", 5000)
