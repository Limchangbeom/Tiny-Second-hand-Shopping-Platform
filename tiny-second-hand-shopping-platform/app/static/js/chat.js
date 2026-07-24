(function () {
    const root = document.querySelector("[data-chat-room]");
    if (!root || typeof io === "undefined") {
        return;
    }

    const room = root.dataset.chatRoom;
    const mode = root.dataset.chatMode;
    const currentUserId = Number(root.dataset.currentUserId || "0");
    const recipientId = root.dataset.recipientId || null;
    const list = document.querySelector("[data-message-list]");
    const form = document.querySelector("[data-chat-form]");
    const input = document.querySelector("[data-chat-input]");
    const errorBox = document.querySelector("[data-chat-error]");
    const socket = io();

    function showError(message) {
        if (!errorBox) {
            return;
        }
        errorBox.textContent = message || "채팅 처리 중 오류가 발생했습니다.";
        errorBox.classList.add("visible");
        window.setTimeout(() => errorBox.classList.remove("visible"), 3500);
    }

    function appendMessage(payload) {
        if (!list || !payload) {
            return;
        }

        const card = document.createElement("article");
        card.className = "message-bubble";
        if (Number(payload.sender_id) === currentUserId) {
            card.classList.add("own");
        }

        const header = document.createElement("header");
        const name = document.createElement("strong");
        const time = document.createElement("span");
        const body = document.createElement("p");

        name.textContent = payload.sender_name;
        time.textContent = payload.created_at;
        body.textContent = payload.body;

        header.appendChild(name);
        header.appendChild(time);
        card.appendChild(header);
        card.appendChild(body);
        list.appendChild(card);
        list.scrollTop = list.scrollHeight;
    }

    socket.on("connect", () => {
        socket.emit("join_room", { room: room });
    });

    socket.on("new_message", appendMessage);
    socket.on("chat_error", (payload) => showError((payload || {}).message));

    if (form && input) {
        form.addEventListener("submit", (event) => {
            event.preventDefault();
            const body = input.value.trim();
            if (!body) {
                return;
            }

            if (mode === "global") {
                socket.emit("send_global_message", { body: body });
            } else {
                socket.emit("send_direct_message", { body: body, recipient_id: recipientId });
            }
            input.value = "";
            input.focus();
        });
    }
})();
