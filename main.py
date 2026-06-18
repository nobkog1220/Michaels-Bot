import anthropic
import os
from dotenv import load_dotenv

load_dotenv()
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def load_system_prompt():
    """Load all .md files from the knowledge/ folder and combine into one prompt."""
    folder = "knowledge"
    parts = []
    for filename in sorted(os.listdir(folder)):
        if filename.endswith(".md"):
            path = os.path.join(folder, filename)
            with open(path, "r", encoding="utf-8") as f:
                parts.append(f.read())
    return "\n\n".join(parts)


SYSTEM_PROMPT = load_system_prompt()

conversation = []

print("Chat started. Type 'quit' to exit.\n")

while True:
    user_input = input("You: ").strip()
    if user_input.lower() in ("quit", "exit"):
        break
    if not user_input:
        continue

    conversation.append({"role": "user", "content": user_input})

    response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=1000,
        system= [
            {
                "type":"text",
                "text":SYSTEM_PROMPT,
                "cache_control":{"type":"ephemeral"}
            }
        ],
        messages=conversation,
    )
    print(f"Cache stats — write: {response.usage.cache_creation_input_tokens}, read: {response.usage.cache_read_input_tokens}, regular input: {response.usage.input_tokens}")

    assistant_reply = response.content[0].text
    conversation.append({"role": "assistant", "content": assistant_reply})

    print(f"\nClaude: {assistant_reply}\n")