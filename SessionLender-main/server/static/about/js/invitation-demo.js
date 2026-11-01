import { byId } from "./dom.js";
export function createInvitationDemo(text) {
  let inviteState = "pending";
  function updateInvitation() {
    const accepted = inviteState === "accepted";
    byId("inviteExplanation").textContent = text(
      accepted ? "acceptedPreview" : "inviteExplanation",
    );
    byId("inviteResult").textContent =
      inviteState === "pending" ? "" : text(accepted ? "accepted" : "rejected");
    byId("acceptDemo").disabled = byId("rejectDemo").disabled =
      inviteState !== "pending";
  }
  byId("acceptDemo").addEventListener("click", () => {
    inviteState = "accepted";
    updateInvitation();
  });
  byId("rejectDemo").addEventListener("click", () => {
    inviteState = "rejected";
    updateInvitation();
  });
  byId("resetInvite").addEventListener("click", () => {
    inviteState = "pending";
    updateInvitation();
  });

  return { refresh: updateInvitation };
}
