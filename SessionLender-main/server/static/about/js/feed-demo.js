import { byId } from "./dom.js";
export function createFeedDemo(text) {
  let activeRoom = "studio";
  let liked = false;
  function updatePost() {
    const labels = { studio: "Studio", friends: "Friends", work: "Work" };
    byId("postArt").dataset.room = activeRoom;
    byId("postArt").querySelector(".post-art-label").textContent =
      labels[activeRoom];
    byId("postArt").querySelector("span").textContent = {
      studio: "✦",
      friends: "✿",
      work: "↗",
    }[activeRoom];
    byId("postAuthor").textContent = "@session · " + labels[activeRoom];
    byId("postText").textContent = text(activeRoom + "Post");
    byId("likeCount").textContent = String(12 + Number(liked));
    byId("demoLike").setAttribute("aria-pressed", String(liked));
    byId("demoLike").querySelector("[aria-hidden]").textContent = liked
      ? "♥"
      : "♡";
  }
  document.querySelectorAll(".room-switch [data-room]").forEach((button) => {
    button.addEventListener("click", () => {
      activeRoom = button.dataset.room;
      liked = false;
      document
        .querySelectorAll(".room-switch button")
        .forEach((item) =>
          item.setAttribute("aria-pressed", String(item === button)),
        );
      updatePost();
    });
  });
  byId("demoLike").addEventListener("click", () => {
    liked = !liked;
    updatePost();
  });

  return { refresh: updatePost };
}
