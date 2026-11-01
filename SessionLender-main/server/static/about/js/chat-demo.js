import { byId } from "./dom.js";

const MAX_MESSAGES = 24;
const SENT_DELAY_MS = 550;
const READ_DELAY_MS = 1400;

export function createChatDemo(text, getLanguage) {
  const input = byId("demoText");
  const messages = byId("demoMessages");
  const deliveryLabel = byId("demoDelivery");
  let deliveryState = null;
  let latestMessage = 0;

  function refresh() {
    deliveryLabel.textContent = text(deliveryState || "deliveryHint");
  }

  function createMessage(value) {
    const bubble = document.createElement("div");
    bubble.className = "demo-bubble mine";
    const body = document.createElement("span");
    body.textContent = value;

    const time = document.createElement("small");
    const locale = getLanguage() === "uk" ? "uk-UA" : "en-GB";
    time.textContent =
      new Date().toLocaleTimeString(locale, {
        hour: "2-digit",
        minute: "2-digit",
      }) + " ";

    const receipt = document.createElement("em");
    receipt.textContent = "◷";
    time.append(receipt);
    bubble.append(body, time);
    return { bubble, receipt };
  }

  function appendMessage(bubble) {
    messages.append(bubble);
    while (messages.children.length > MAX_MESSAGES) {
      messages.firstElementChild.remove();
    }
    messages.scrollTop = messages.scrollHeight;
  }

  function updateReceipt(receipt, sequence, symbol, state) {
    receipt.textContent = symbol;
    // Older timers must not overwrite the newest message's status label.
    if (sequence === latestMessage) {
      deliveryState = state;
      refresh();
    }
  }

  function simulateDelivery(receipt, sequence) {
    deliveryState = "sending";
    refresh();
    window.setTimeout(() => {
      updateReceipt(receipt, sequence, "✓", "sent");
    }, SENT_DELAY_MS);
    window.setTimeout(() => {
      updateReceipt(receipt, sequence, "✓✓", "read");
    }, READ_DELAY_MS);
  }

  function sendMessage(event) {
    event.preventDefault();
    const value = input.value.trim();
    if (!value) return;

    const { bubble, receipt } = createMessage(value);
    appendMessage(bubble);
    input.value = "";
    input.focus();
    simulateDelivery(receipt, ++latestMessage);
  }

  byId("demoChatForm").addEventListener("submit", sendMessage);
  return { refresh };
}
