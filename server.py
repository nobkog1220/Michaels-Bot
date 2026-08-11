from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import anthropic
import os
from dotenv import load_dotenv
import json
from pathlib import Path
from datetime import datetime
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import threading
# Load environment variables (your API key from .env)
load_dotenv()
print(f"DEBUG — ADMIN_PASSWORD from env: '{os.getenv('ADMIN_PASSWORD')}'")
# Set up the Flask app
app = Flask(__name__)
CORS(app)  # Allow requests from your HTML file later
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["100 per hour", "20 per minute"],
)
print(f"DEBUG — Limiter enabled: {limiter.enabled}")
@app.errorhandler(429)
def ratelimit_handler(e):
    return jsonify({"reply": "You're sending messages too quickly. Please slow down and try again in a minute."}), 429
# Set up Anthropic client
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "changeme")


def load_system_prompt():
    """Load all .md files from the knowledge/ folder and combine them."""
    folder = "knowledge"
    parts = []
    for filename in sorted(os.listdir(folder)):
        if filename.endswith(".md"):
            path = os.path.join(folder, filename)
            with open(path, "r", encoding="utf-8") as f:
                parts.append(f.read())
    return "\n\n".join(parts)


# Load once at server startup, reuse for every request
SYSTEM_PROMPT = load_system_prompt()
LOGS_DIR = Path(os.getenv("LOGS_DIR", "conversation_logs"))
LOGS_DIR.mkdir(exist_ok=True, parents=True)
import smtplib
from email.message import EmailMessage

def send_notification(session_id=None, first_message=None, first_reply=None):
    """Send an email alert when a new bot session starts."""
    gmail_address = os.environ.get("GMAIL_ADDRESS")
    gmail_password = os.environ.get("GMAIL_APP_PASSWORD")
    notify_email = os.environ.get("NOTIFY_EMAIL")

    if not all([gmail_address, gmail_password, notify_email]):
        print("Notification skipped: missing email env vars")
        return

    msg = EmailMessage()
    msg["Subject"] = "New Michael's Bot Session"
    msg["From"] = gmail_address
    msg["To"] = notify_email
    msg.set_content(
        f"A new chat session started.\n"
        f"Session ID: {session_id}\n\n"
        f"Customer: {first_message}\n"
        f"Bot: {first_reply}"
    )

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as smtp:
            smtp.login(gmail_address, gmail_password)
            smtp.send_message(msg)
    except Exception as e:
        print(f"Failed to send notification email: {e}")

def log_conversation(session_id, conversation, latest_reply):
    """Save or update a conversation log file."""
    log_file = LOGS_DIR / f"{session_id}.json"

    # If file exists, load it; otherwise start fresh
    if log_file.exists():
        with open(log_file, "r", encoding="utf-8") as f:
            log_data = json.load(f)
    else:
        log_data = {
            "session_id": session_id,
            "started_at": datetime.now().isoformat(),
            "messages": []
        }
        first_message = conversation[0]["content"] if conversation else ""
        threading.Thread(
            target=send_notification,
            args=(session_id, first_message, latest_reply)
        ).start()

    # Update with the latest exchange
    log_data["last_updated"] = datetime.now().isoformat()
    log_data["messages"] = conversation + [{"role": "assistant", "content": latest_reply}]

    # Save back to file
    with open(log_file, "w", encoding="utf-8") as f:
        json.dump(log_data, f, indent=2, ensure_ascii=False)
@app.route("/chat", methods=["POST"])
@limiter.limit("35 per hour")
@limiter.limit("10 per minute")


def chat():
    """Handle a chat message from the browser."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"reply": "Something went wrong. Please try again."}), 400

        conversation = data.get("conversation", [])
        if not conversation:
            return jsonify({"reply": "I didn't catch your message. Could you try again?"}), 400

        response = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=1000,
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"}
                }
            ],
            messages=conversation,
        )
        print(
            f"Cache stats — write: {response.usage.cache_creation_input_tokens}, read: {response.usage.cache_read_input_tokens}, regular input: {response.usage.input_tokens}")

        assistant_reply = response.content[0].text

        session_id = data.get("session_id", "unknown")
        log_conversation(session_id, conversation, assistant_reply)

        return jsonify({"reply": assistant_reply})

    except anthropic.APIConnectionError as e:
        print(f"ERROR — Connection issue with Anthropic: {e}")
        return jsonify({"reply": "I'm having trouble connecting right now. Please try again in a moment."}), 503

    except anthropic.RateLimitError as e:
        print(f"ERROR — Anthropic rate limit hit: {e}")
        return jsonify({"reply": "I'm getting a lot of traffic right now. Please try again in a minute."}), 503

    except anthropic.APIStatusError as e:
        print(f"ERROR — Anthropic API status error: {e.status_code} — {e}")
        return jsonify({"reply": "Something went wrong on my end. Please try again, or call (847) 432-3338 if it keeps happening."}), 503

    except Exception as e:
        print(f"ERROR — Unexpected error in chat(): {type(e).__name__}: {e}")
        return jsonify({"reply": "Something went wrong. Please try again, or call (847) 432-3338 for help."}), 500


@app.route("/")
def home():
    """Serve the chat page."""
    return send_from_directory("static", "index.html")
@app.route("/admin")
def admin():
    """Show all conversation logs."""
    password = request.args.get("password", "")
    print(f"DEBUG — got password: '{password}' | expecting: '{ADMIN_PASSWORD}'")
    if password != ADMIN_PASSWORD:
        return "Unauthorized. Add ?password=YOUR_PASSWORD to the URL.", 401

    # Load all conversation files
    conversations = []
    for log_file in sorted(LOGS_DIR.glob("*.json"), reverse=True):
        with open(log_file, "r", encoding="utf-8") as f:
            conversations.append(json.load(f))

    # Sort by last_updated, newest first
    conversations.sort(key=lambda c: c.get("last_updated", ""), reverse=True)

    # Build the HTML page
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Michael's Bot — Conversation Logs</title>
        <style>
            body { font-family: sans-serif; max-width: 800px; margin: 20px auto; padding: 20px; background: #f5f5f5; }
            h1 { color: #c8102e; }
            .conversation { background: white; border-radius: 8px; padding: 16px; margin-bottom: 16px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
            .meta { color: #666; font-size: 13px; margin-bottom: 12px; }
            .message { padding: 8px 12px; border-radius: 8px; margin-bottom: 6px; max-width: 80%; }
            .user { background: #c8102e; color: white; margin-left: auto; }
            .assistant { background: #eee; }
            .empty { color: #999; font-style: italic; text-align: center; padding: 40px; }
        </style>
    </head>
    <body>
        <h1>Michael's Bot — Conversation Logs</h1>
    """

    if not conversations:
        html += '<div class="empty">No conversations yet.</div>'
    else:
        html += f"<p>{len(conversations)} conversation(s) total.</p>"
        for conv in conversations:
            html += '<div class="conversation">'
            html += f'<div class="meta">'
            html += f'Started: {conv.get("started_at", "unknown")[:19]}<br>'
            html += f'Last updated: {conv.get("last_updated", "unknown")[:19]}<br>'
            html += f'Messages: {len(conv.get("messages", []))}<br>'
            html += f'Session ID: {conv.get("session_id", "unknown")[:8]}...'
            html += '</div>'

            for msg in conv.get("messages", []):
                role = msg.get("role", "")
                content = msg.get("content", "").replace("<", "&lt;").replace(">", "&gt;")
                html += f'<div class="message {role}"><strong>{role}:</strong> {content}</div>'

            html += '</div>'

    html += "</body></html>"
    return html

if __name__ == "__main__":
    # Start the server on port 5000
    app.run(debug=True, port=5000)