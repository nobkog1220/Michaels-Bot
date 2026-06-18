const messagesDiv = document.getElementById("messages");
const userInput = document.getElementById("user-input");
const sendBtn = document.getElementById("send-btn");

const toggleBtn = document.getElementById("chat-toggle-btn");
const closeBtn = document.getElementById("chat-close-btn");
const chatWidget = document.getElementById("chat-widget");

let conversation = [];
let sessionId = crypto.randomUUID();

function addMessage(text, sender) {
    const messageDiv = document.createElement("div");
    messageDiv.className = "message " + sender + "-message";
    if (sender === "bot") {
        messageDiv.innerHTML = marked.parse(text);
    } else {
        messageDiv.textContent = text;
    }
    messagesDiv.appendChild(messageDiv);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
}

async function sendMessage() {
    const text = userInput.value.trim();
    if (!text) return;

    addMessage(text, "user");
    conversation.push({role: "user", content: text});
    userInput.value = "";
    sendBtn.disabled = true;

    try {
        const response = await fetch("/chat", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({conversation: conversation, session_id:sessionId})
        });

        const data = await response.json();
        addMessage(data.reply, "bot");
        conversation.push({role: "assistant", content: data.reply});

    } catch (error) {
        addMessage("Error: could not reach server.", "bot");
        console.error(error);
    }

    sendBtn.disabled = false;
    userInput.focus();
}

sendBtn.addEventListener("click", sendMessage);
userInput.addEventListener("keypress", function(event) {
    if (event.key === "Enter") {
        sendMessage();
    }
});

toggleBtn.addEventListener("click", function() {
    chatWidget.classList.toggle("hidden");
    if (!chatWidget.classList.contains("hidden")) {
        userInput.focus();
    }
});

closeBtn.addEventListener("click", function() {
    chatWidget.classList.add("hidden");
});