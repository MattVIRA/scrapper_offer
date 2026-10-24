// List of offers, one line each, and the bar that resizes it beside the card.
//
// data: {rows, checked, open, splitKey, listPaneKey, cardOpen, stars}
// Events sent to Python: checked (ids), opened (id), starred (id).
// Texts come from the websites: always set with textContent, never as HTML.

const WIDTH_VAR = "--offer-list-width";
const HEIGHT_VAR = "--offer-pane-height";
const WIDTH_STORAGE = "offers.listWidth";
// Share of the page taken by the list, beside the card.
const MIN_SHARE = 0.25;
const MAX_SHARE = 0.75;
// Space kept under the list and the card, in pixels.
const BOTTOM_MARGIN = 16;
const HANDLE_WIDTH = 10;

// Per instance: last open offer, to scroll to it only when it changes.
const instances = new WeakMap();

export default function (component) {
  const { data, parentElement, setTriggerValue } = component;
  const list = parentElement.querySelector(".offer-list");
  const state = instances.get(parentElement) || { open: null };
  instances.set(parentElement, state);

  restoreWidth();
  render(list, data, setTriggerValue);
  requestAnimationFrame(() => {
    fitHeights(list);
    placeSplitter(data);
    if (data.open !== state.open) {
      list.querySelector(".row.open")?.scrollIntoView({ block: "nearest" });
    }
    state.open = data.open;
  });
  watchWindow(list, data);
}

function render(list, data, setTriggerValue) {
  const checked = new Set(data.checked);
  const send = () => setTriggerValue("checked", [...checked]);
  list.replaceChildren(header(data.rows, checked, send));
  for (const row of data.rows) {
    list.append(line(row, data, checked, send, setTriggerValue));
  }
}

function header(rows, checked, send) {
  const element = document.createElement("div");
  element.className = "list-header";
  const all = document.createElement("input");
  all.type = "checkbox";
  all.title = "Tout cocher";
  all.checked = rows.length > 0 && rows.every((row) => checked.has(row.id));
  all.indeterminate = !all.checked && rows.some((row) => checked.has(row.id));
  all.addEventListener("change", () => {
    for (const row of rows) all.checked ? checked.add(row.id) : checked.delete(row.id);
    send();
  });
  const label = document.createElement("span");
  label.textContent = "Tout cocher";
  element.append(all, label);
  return element;
}

function line(row, data, checked, send, setTriggerValue) {
  const element = document.createElement("div");
  element.className = ["row", row.marker, row.unread ? "unread" : "", row.id === data.open ? "open" : ""]
    .filter(Boolean)
    .join(" ");
  element.addEventListener("click", () => setTriggerValue("opened", row.id));

  const box = document.createElement("input");
  box.type = "checkbox";
  box.checked = checked.has(row.id);
  box.addEventListener("click", (event) => event.stopPropagation());
  box.addEventListener("change", () => {
    box.checked ? checked.add(row.id) : checked.delete(row.id);
    send();
  });

  element.append(box);
  if (data.stars) element.append(star(row, setTriggerValue));
  element.append(text("title", row.title), text("company", row.subtitle));
  if (row.letter) element.append(text("chip", row.letter));
  element.append(text("chip", row.source), text("score", row.score), text("date", row.date));
  element.title = row.title;
  return element;
}

function star(row, setTriggerValue) {
  const star = document.createElement("button");
  star.className = row.favorite ? "star on" : "star";
  star.textContent = row.favorite ? "★" : "☆";
  star.title = row.favorite ? "Retirer des favoris" : "Favori";
  star.addEventListener("click", (event) => {
    event.stopPropagation();
    setTriggerValue("starred", row.id);
  });
  return star;
}

function text(className, value) {
  const element = document.createElement("span");
  element.className = className;
  element.textContent = value ?? "";
  return element;
}

// The list and the card scroll each on their own, down to the bottom of the window.
function fitHeights(list) {
  const top = list.getBoundingClientRect().top;
  list.style.maxHeight = `${Math.max(window.innerHeight - top - BOTTOM_MARGIN, 200)}px`;
}

function setPaneHeight(split) {
  const top = split.getBoundingClientRect().top;
  const height = Math.max(window.innerHeight - top - BOTTOM_MARGIN, 200);
  document.documentElement.style.setProperty(HEIGHT_VAR, `${height}px`);
}

function restoreWidth() {
  try {
    const share = parseFloat(localStorage.getItem(WIDTH_STORAGE));
    if (share >= MIN_SHARE && share <= MAX_SHARE) setShare(share);
  } catch {
    // No storage (private window): the default width stays.
  }
}

function setShare(share) {
  document.documentElement.style.setProperty(WIDTH_VAR, `${(share * 100).toFixed(1)}%`);
}

// The bar is added to the page itself, between the list and the card.
function placeSplitter(data) {
  const split = document.querySelector(`.st-key-${data.splitKey}`);
  const pane = document.querySelector(`.st-key-${data.listPaneKey}`);
  if (!split || !pane) return;
  setPaneHeight(split);
  let handle = split.querySelector(":scope > .offer-splitter");
  if (!handle) {
    handle = makeHandle(split);
    split.append(handle);
  }
  handle.style.display = data.cardOpen ? "block" : "none";
  const left = pane.getBoundingClientRect().right - split.getBoundingClientRect().left;
  handle.style.left = `${left}px`;
}

function makeHandle(split) {
  const handle = document.createElement("div");
  handle.className = "offer-splitter";
  handle.title = "Glisser pour changer la largeur";
  Object.assign(handle.style, {
    position: "absolute",
    top: "0",
    bottom: "0",
    width: `${HANDLE_WIDTH}px`,
    cursor: "col-resize",
    zIndex: "10",
    touchAction: "none",
  });
  let share = null;
  handle.addEventListener("pointerdown", (event) => {
    handle.setPointerCapture(event.pointerId);
    event.preventDefault();
    const move = (moveEvent) => {
      const box = split.getBoundingClientRect();
      share = Math.min(Math.max((moveEvent.clientX - box.left) / box.width, MIN_SHARE), MAX_SHARE);
      setShare(share);
      handle.style.left = `${share * box.width}px`;
    };
    const stop = () => {
      handle.removeEventListener("pointermove", move);
      handle.removeEventListener("pointerup", stop);
      try {
        if (share !== null) localStorage.setItem(WIDTH_STORAGE, String(share));
      } catch {
        // Not kept for the next opening, nothing more.
      }
    };
    handle.addEventListener("pointermove", move);
    handle.addEventListener("pointerup", stop);
  });
  return handle;
}

function watchWindow(list, data) {
  window.__offerListResize && window.removeEventListener("resize", window.__offerListResize);
  window.__offerListResize = () => {
    fitHeights(list);
    placeSplitter(data);
  };
  window.addEventListener("resize", window.__offerListResize);
}
