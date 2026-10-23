/* RedScribe web frontend. Vanilla JS, no build step, no external assets. */
(() => {
  "use strict";

  /* ==================================================================
   * Utilities
   * ================================================================ */

  const $id = (id) => document.getElementById(id);
  const esc = (text) =>
    String(text).replace(/[&<>"']/g, (ch) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch]);
  const debounce = (fn, ms) => {
    let timer = null;
    return (...args) => { clearTimeout(timer); timer = setTimeout(() => fn(...args), ms); };
  };
  const clamp = (value, lo, hi) => Math.min(hi, Math.max(lo, value));
  const fmtWords = (n) => (n === 1 ? "1 word" : `${n.toLocaleString()} words`);
  const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

  async function api(method, body = {}) {
    const response = await fetch(`/api/${method}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    let payload = null;
    try { payload = await response.json(); } catch { payload = null; }
    if (!response.ok || !payload || payload.ok !== true) {
      const message = payload && payload.error ? payload.error : `Request failed (${response.status})`;
      throw new Error(message);
    }
    return payload.data;
  }

  function copyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(
        () => toast("Copied to clipboard"),
        () => toast("Copy failed", true),
      );
      return;
    }
    const area = document.createElement("textarea");
    area.value = text;
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    try { document.execCommand("copy"); toast("Copied to clipboard"); } catch { toast("Copy failed", true); }
    area.remove();
  }

  function toast(message, isError = false, ms = 2600) {
    const el = document.createElement("div");
    el.className = `toast${isError ? " err" : ""}`;
    el.textContent = message;
    $id("toasts").appendChild(el);
    setTimeout(() => { el.style.opacity = "0"; el.style.transition = "opacity .2s"; }, ms - 250);
    setTimeout(() => el.remove(), ms);
  }

  /* ==================================================================
   * State and DOM references
   * ================================================================ */

  const S = {
    boot: null,
    nodes: new Map(),
    tree: [],
    expanded: new Set(),
    selectedId: null,
    note: null,
    viewMode: "split",
    theme: "dark",
    fontSize: 13,
    syncScroll: true,
    lastTemplate: "ctf",
    restoreLastNote: true,
    templates: [],
    paletteResults: [],
    paletteSel: 0,
    searchResults: [],
    searchSel: 0,
    snippets: [],
    activeCategory: "__all",
    snippetQuery: "",
    snippetSel: null,
    editingSnippetId: null,
    selectedTemplate: "ctf",
    statusColors: { todo: "var(--faint)", active: "var(--blue)", done: "var(--green)", blocked: "var(--red)" },
    dirty: false,
    saveTimer: null,
    saveChain: Promise.resolve(),
    splitPos: null,
    sidebarDragged: false,
  };

  const D = {
    tree: $id("tree"),
    editor: $id("editor"),
    preview: $id("preview"),
    previewScroll: $id("previewScroll"),
    titleInput: $id("titleInput"),
    crumb: $id("noteCrumb"),
    chips: $id("chips"),
    welcomePane: $id("welcomePane"),
    noteArea: $id("noteArea"),
    welcomeStats: $id("welcomeStats"),
    welcomeRecent: $id("welcomeRecent"),
    welcomeActions: $id("welcomeActions"),
    saveDot: $id("saveDot"),
    saveState: $id("saveState"),
    wordCount: $id("wordCount"),
    statusLocation: $id("statusLocation"),
    statusFlag: $id("statusFlag"),
    sidebar: $id("sidebar"),
    sidebarSash: $id("sidebarSash"),
    sidebarCount: $id("sidebarCount"),
    split: $id("split"),
    editorPane: $id("editorPane"),
    previewPane: $id("previewPane"),
    btnPin: $id("btnPin"),
    toasts: $id("toasts"),
    paletteInput: $id("paletteInput"),
    paletteList: $id("paletteList"),
    searchInput: $id("searchInput"),
    searchList: $id("searchList"),
    snippetFilter: $id("snippetFilter"),
    snippetCats: $id("snippetCats"),
    snippetList: $id("snippetList"),
    snippetDetail: $id("snippetDetail"),
    templateGrid: $id("templateGrid"),
    newNoteTitle: $id("newNoteTitle"),
    newNoteTarget: $id("newNoteTarget"),
    newNoteParent: $id("newNoteParent"),
    newFolderTitle: $id("newFolderTitle"),
    newFolderParent: $id("newFolderParent"),
    propStatus: $id("propStatus"),
    propDifficulty: $id("propDifficulty"),
    propTarget: $id("propTarget"),
    propTags: $id("propTags"),
    propFlag: $id("propFlag"),
    propStats: $id("propStats"),
    trashList: $id("trashList"),
    trashCount: $id("trashCount"),
    dashCards: $id("dashCards"),
    dashFlags: $id("dashFlags"),
    dashTags: $id("dashTags"),
    setTheme: $id("setTheme"),
    setFontSize: $id("setFontSize"),
    setRestore: $id("setRestore"),
    setSyncScroll: $id("setSyncScroll"),
    setVaultPath: $id("setVaultPath"),
    setVersion: $id("setVersion"),
    snipTitle: $id("snipTitle"),
    snipCommand: $id("snipCommand"),
    snipDescription: $id("snipDescription"),
    snipTags: $id("snipTags"),
    snippetFormTitle: $id("snippetFormTitle"),
    btnSnipDelete: $id("btnSnipDelete"),
    ctxMenu: $id("ctxMenu"),
    helpGrid: $id("helpGrid"),
    confirmTitle: $id("confirmTitle"),
    confirmText: $id("confirmText"),
    confirmButton: $id("confirmButton"),
  };

  /* ==================================================================
   * Icons injected from JS
   * ================================================================ */

  const I = {
    file: '<svg class="ticon note" viewBox="0 0 24 24"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5zm0 0v5h5" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/></svg>',
    folder: '<svg class="ticon" viewBox="0 0 24 24"><path d="M4 5.5A1.5 1.5 0 0 1 5.5 4h4l1.8 2h8A1.5 1.5 0 0 1 20.8 7.5V17a2.5 2.5 0 0 1-2.5 2.5H6A2 2 0 0 1 4 17.5z" fill="currentColor" opacity="0.85"/></svg>',
    chev: '<svg class="chev" viewBox="0 0 24 24"><path d="m6 9 6 6 6-6" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    pin: '<svg class="i" viewBox="0 0 24 24"><path d="M12.7 2.9 21 11.2l-3.4-.6-5-5-1-3.4-1.2.1zM8 16 4 20M9.6 14.4l-5-5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    flag: '<svg class="i" viewBox="0 0 24 24"><path d="M6 3v18M6 4.5h10.5L14 8.5l2.5 4H6" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linejoin="round" stroke-linecap="round"/></svg>',
    copy: '<svg class="i" viewBox="0 0 24 24"><rect x="9" y="9" width="11" height="11" rx="2" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M5 15h-.5A1.5 1.5 0 0 1 3 13.5v-9A1.5 1.5 0 0 1 4.5 3h9A1.5 1.5 0 0 1 15 4.5V5" fill="none" stroke="currentColor" stroke-width="1.7"/></svg>',
    restore: '<svg class="i" viewBox="0 0 24 24"><path d="M4.5 9A8 8 0 1 1 3.6 15M4.5 9V4m0 5H9" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    x: '<svg class="i" viewBox="0 0 24 24"><path d="m6 6 12 12M18 6 6 18" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/></svg>',
    pen: '<svg class="i" viewBox="0 0 24 24"><path d="M4 20h4L19.5 8.5a2.12 2.12 0 0 0-3-3L5 17v3z" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/></svg>',
    dl: '<svg class="i" viewBox="0 0 24 24"><path d="M12 3.5v10m0 0L8.5 10M12 13.5 15.5 10M5 17.5v1a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-1" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg>',
    fileNew: '<svg class="i" viewBox="0 0 24 24"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5zm0 0v5h5m-5 8h4m-4-4h4" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/></svg>',
    folderNew: '<svg class="i" viewBox="0 0 24 24"><path d="M3.5 6A1.5 1.5 0 0 1 5 4.5h3.6l1.8 2H19A1.5 1.5 0 0 1 20.5 8V18a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2zm8.5 8v-4m-2 2h4" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/></svg>',
    dup: '<svg class="i" viewBox="0 0 24 24"><rect x="8" y="8" width="12" height="12" rx="2" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2" fill="none" stroke="currentColor" stroke-width="1.7"/></svg>',
    trash: '<svg class="i" viewBox="0 0 24 24"><path d="M5 7h14M10 4h4m-8 3 .8 13h8.4L16 7m-6 4v6m2.6-6v6" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  };

  const STATUS_ICON = { todo: "○", active: "●", done: "✓", blocked: "⊘" };
  const STATUS_LABEL = { todo: "Open", active: "Active", done: "Done", blocked: "Blocked" };

  /* ==================================================================
   * Modals
   * ================================================================ */

  const openOverlays = [];

  function openModal(id) {
    const overlay = $id(id);
    if (!overlay) return;
    overlay.classList.remove("hidden");
    if (!openOverlays.includes(id)) openOverlays.push(id);
    const input = overlay.querySelector("input:not([type=checkbox]), textarea");
    if (input) setTimeout(() => { input.focus(); input.select(); }, 10);
  }

  function closeModal(id) {
    const overlay = $id(id);
    if (overlay) overlay.classList.add("hidden");
    const index = openOverlays.lastIndexOf(id);
    if (index >= 0) openOverlays.splice(index, 1);
  }

  function topOverlay() { return openOverlays[openOverlays.length - 1]; }

  function closeTopOverlay() {
    const id = topOverlay();
    if (id) closeModal(id);
    hideMenus();
  }

  function anyOverlayOpen() { return openOverlays.length > 0; }

  let confirmAction = null;
  function confirmAsk(title, textHtml, okLabel, action) {
    D.confirmTitle.textContent = title;
    D.confirmText.innerHTML = textHtml;
    D.confirmButton.textContent = okLabel || "Confirm";
    confirmAction = action;
    openModal("confirmModal");
    setTimeout(() => D.confirmButton.focus(), 20);
  }

  D.confirmButton.addEventListener("click", async () => {
    const action = confirmAction;
    confirmAction = null;
    closeModal("confirmModal");
    if (action) await action();
  });

  /* ==================================================================
   * Theme, font, view mode
   * ================================================================ */

  function applyTheme(theme) {
    S.theme = theme || "dark";
    document.body.dataset.theme = S.theme;
  }

  function applyFontSize(size) {
    S.fontSize = clamp(size || 13, 9, 18);
    document.documentElement.style.setProperty("--ed-size", `${S.fontSize}px`);
  }

  function applyViewMode(mode) {
    S.viewMode = mode || "split";
    document.body.dataset.viewmode = S.viewMode;
  }

  function cycleView() {
    const order = ["editor", "split", "preview"];
    const next = order[(order.indexOf(S.viewMode) + 1) % 3];
    setViewMode(next);
  }

  function setViewMode(mode) {
    applyViewMode(mode);
    saveSettings({ view_mode: mode });
    if (mode !== "editor") schedulePreview();
  }

  function saveSettings(values) {
    api("set_settings", values).catch((err) => toast(err.message, true));
  }

  /* ==================================================================
   * Save pipeline (autosave)
   * ================================================================ */

  function setSaveState(state) {
    D.saveDot.classList.remove("saving", "saved", "dirty");
    D.saveDot.classList.add(state);
    D.saveState.textContent = state === "saving" ? "Saving…"
      : state === "saved" ? "All changes saved"
      : state === "dirty" ? "Unsaved changes" : "Idle";
  }

  function queueSave() {
    if (!S.note) return;
    S.dirty = true;
    setSaveState("dirty");
    clearTimeout(S.saveTimer);
    schedulePreview();
    scheduleWordCount();
    S.saveTimer = setTimeout(() => { flushSave(); }, 700);
  }

  function flushSave() {
    if (!S.note || !S.dirty) return S.saveChain;
    clearTimeout(S.saveTimer);
    S.saveTimer = null;
    S.dirty = false;
    setSaveState("saving");
    const content = D.editor.value;
    const noteId = S.note.id;
    S.saveChain = S.saveChain
      .then(() => api("save_content", { id: noteId, content }))
      .then((node) => {
        if (S.note && S.note.id === noteId && node) S.note.updated_at = node.updated_at;
        setSaveState("saved");
      })
      .catch(() => { S.dirty = true; setSaveState("dirty"); toast("Save failed — will retry", true); });
    return S.saveChain;
  }

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState !== "hidden" || !S.dirty || !S.note) return;
    fetch(`/api/save_content`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: S.note.id, content: D.editor.value }),
      keepalive: true,
    });
  });

  window.addEventListener("beforeunload", (event) => {
    if (S.dirty) {
      flushSave();
      event.preventDefault();
      event.returnValue = "";
    }
  });

  const schedulePreview = debounce(async () => {
    if (!S.note || S.viewMode === "editor") return;
    const html = await api("render_preview", { content: D.editor.value });
    if (S.note) D.preview.innerHTML = html || '<p class="preview-empty">Nothing to preview yet.</p>';
  }, 420);

  const scheduleWordCount = debounce(updateWordCount, 150);

  function updateWordCount() {
    const words = S.note ? (D.editor.value.trim().match(/\S+/g) || []).length : 0;
    D.wordCount.textContent = fmtWords(words);
  }

  function updateStatusLocation() {
    if (!S.note) { D.statusLocation.textContent = "No note selected"; return; }
    D.statusLocation.textContent = `in ${S.note.path || "vault root"}`;
  }

  /* ==================================================================
   * Tree
   * ================================================================ */

  function walkTree(nodes) {
    for (const node of nodes) {
      S.nodes.set(node.id, node);
      if (node.children) walkTree(node.children);
    }
  }

  async function refreshTree() {
    S.tree = await api("tree");
    S.nodes.clear();
    walkTree(S.tree);
    renderTree();
  }

  function renderTree() {
    let noteCount = 0;
    for (const node of S.nodes.values()) if (node.kind === "note") noteCount += 1;
    D.sidebarCount.textContent = noteCount ? plural(noteCount, "note") : "";
    D.tree.innerHTML = "";
    if (!S.tree.length) {
      const empty = document.createElement("div");
      empty.className = "tree-empty";
      empty.innerHTML = "No notes yet.<br>Create one with <b>+ New note</b> or <kbd>Ctrl</kbd> <kbd>N</kbd>.";
      D.tree.appendChild(empty);
      return;
    }
    appendTreeLevel(S.tree, 0, D.tree);
  }

  function appendTreeLevel(nodes, depth, host) {
    for (const node of nodes) host.appendChild(buildTreeRow(node, depth));
  }

  function buildTreeRow(node, depth) {
    const row = document.createElement("div");
    row.className = "tree-row";
    if (node.id === S.selectedId) row.classList.add("active-note");
    row.dataset.id = String(node.id);
    row.dataset.kind = node.kind;
    row.draggable = true;
    row.style.setProperty("--indent", `${depth * 14}px`);

    if (node.kind === "folder") {
      const open = S.expanded.has(node.id);
      const chev = document.createElement("span");
      chev.className = "chevwrap";
      chev.style.marginLeft = `${8 + depth * 14}px`;
      const chevBtn = document.createElement("button");
      chevBtn.type = "button";
      chevBtn.innerHTML = I.chev;
      chevBtn.setAttribute("aria-label", "Toggle folder");
      if (open) chevBtn.classList.add("open");
      chevBtn.addEventListener("click", (event) => {
        event.stopPropagation();
        toggleFolder(node.id);
      });
      chev.appendChild(chevBtn);
      row.appendChild(chev);

      const icon = document.createElement("span");
      icon.innerHTML = I.folder;
      const label = document.createElement("span");
      label.className = "tlabel folder";
      label.textContent = node.title;
      const grow = document.createElement("span");
      grow.className = "del";
      const badge = document.createElement("span");
      badge.className = "badge";
      badge.textContent = node.children && node.children.length ? String(node.children.length) : "";
      row.append(icon, label, grow, badge);
      row.addEventListener("click", () => toggleFolder(node.id));
    } else {
      const pad = document.createElement("span");
      pad.style.marginLeft = `${8 + depth * 14 + 14}px`;
      pad.style.flex = "none";
      row.appendChild(pad);
      const icon = document.createElement("span");
      icon.innerHTML = I.file;
      const label = document.createElement("span");
      label.className = "tlabel";
      label.textContent = node.title;
      const grow = document.createElement("span");
      grow.className = "del";
      row.append(icon, label, grow);
      if (node.flag) {
        const flagIcon = document.createElement("span");
        flagIcon.className = "flagmini";
        flagIcon.innerHTML = I.flag;
        flagIcon.title = node.flag;
        row.appendChild(flagIcon);
      }
      if (node.pinned) {
        const pinIcon = document.createElement("span");
        pinIcon.className = "minibadge";
        pinIcon.innerHTML = I.pin;
        row.appendChild(pinIcon);
      }
      const dot = document.createElement("span");
      dot.className = `dot ${node.status || "todo"}`;
      row.appendChild(dot);
      row.addEventListener("click", () => selectNode(node.id));
    }

    row.addEventListener("contextmenu", (event) => showTreeCtx(event, node));
    row.addEventListener("dragstart", (event) => {
      draggedId = node.id;
      try { event.dataTransfer.setData("text/plain", String(node.id)); } catch { /* WebView2 may refuse */ }
      event.dataTransfer.effectAllowed = "move";
    });
    row.addEventListener("dragend", () => { draggedId = null; });
    row.addEventListener("dragover", (event) => {
      if (draggedId === null || draggedId === node.id) return;
      const targetKind = node.kind === "folder" ? "folder" : "parent";
      if (targetKind === "folder" || draggedId !== node.id) {
        event.preventDefault();
        row.classList.add("dragover");
      }
    });
    row.addEventListener("dragleave", () => row.classList.remove("dragover"));
    row.addEventListener("drop", async (event) => {
      event.preventDefault();
      event.stopPropagation();
      row.classList.remove("dragover");
      const sourceId = draggedId !== null ? draggedId : Number(event.dataTransfer.getData("text/plain"));
      draggedId = null;
      if (!sourceId || sourceId === node.id) return;
      const parentId = node.kind === "folder" ? node.id : node.parent_id;
      const source = S.nodes.get(sourceId);
      if (source && source.parent_id === parentId && node.kind === "note") return;
      try {
        await api("move_node", { id: sourceId, parent_id: parentId });
        if (parentId !== null) S.expanded.add(parentId);
        await refreshTree();
        if (S.note && S.note.id === sourceId) await selectNode(sourceId, { keepFocus: true });
        toast(parentId === null ? "Moved to vault root" : "Moved");
      } catch (err) { toast(err.message, true); }
    });
    return row;
  }

  let draggedId = null;

  $id("treeRootRow").addEventListener("dragover", (event) => event.preventDefault());
  $id("treeRootRow").addEventListener("drop", async (event) => {
    event.preventDefault();
    event.stopPropagation();
    const sourceId = draggedId !== null ? draggedId : Number(event.dataTransfer.getData("text/plain"));
    draggedId = null;
    if (!sourceId) return;
    const source = S.nodes.get(sourceId);
    if (source && source.parent_id === null) return;
    try {
      await api("move_node", { id: sourceId, parent_id: null });
      await refreshTree();
      toast("Moved to vault root");
    } catch (err) { toast(err.message, true); }
  });

  async function toggleFolder(id) {
    if (S.expanded.has(id)) S.expanded.delete(id);
    else S.expanded.add(id);
    renderTree();
  }

  function expandAncestors(id) {
    let node = S.nodes.get(id);
    while (node && node.parent_id !== null) {
      S.expanded.add(node.parent_id);
      node = S.nodes.get(node.parent_id);
    }
  }

  /* ==================================================================
   * Note selection & rendering
   * ================================================================ */

  async function selectNode(id, options = {}) {
    await flushSave();
    let node;
    try {
      node = await api("node", { id });
    } catch (err) {
      toast(err.message, true);
      return;
    }
    if (node.kind === "folder") {
      S.expanded.add(id);
      renderTree();
      return;
    }
    S.selectedId = id;
    S.note = node;
    S.dirty = false;
    clearTimeout(S.saveTimer);
    saveSettings({ last_note: String(id) });
    D.welcomePane.classList.add("hidden");
    D.noteArea.classList.remove("hidden");
    D.titleInput.value = node.title;
    D.editor.value = node.content || "";
    D.preview.innerHTML = node.preview_html || '<p class="preview-empty">Nothing to preview yet.</p>';
    updateWordCount();
    renderChips(node);
    renderCrumb(node);
    updateStatusLocation();
    D.btnPin.classList.toggle("on", !!node.pinned);
    const hasFlag = !!node.flag;
    D.statusFlag.classList.toggle("hidden", !hasFlag);
    D.statusFlag.textContent = node.flag || "";
    D.statusFlag.title = hasFlag ? "Click to copy the captured flag" : "";
    setSaveState("idle");
    expandAncestors(id);
    renderTree();
    D.editor.scrollTop = 0;
    if (!options.keepFocus) D.editor.focus();
  }

  function renderCrumb(node) {
    const parts = node.path ? node.path.split(" / ") : [];
    const sections = parts.map((p) => `<b>${esc(p)}</b>`).join(" / ");
    D.crumb.innerHTML = (sections ? `${sections} / ` : "<b>Vault root</b> / ") + `<strong>${esc(node.title)}</strong>`;
  }

  function renderChips(node) {
    D.chips.innerHTML = "";
    const chips = [];
    chips.push(makeChip(`<span class="dot ${node.status}"></span>${STATUS_ICON[node.status]} ${STATUS_LABEL[node.status]}`, `s-${node.status}`, () => {}));
    if (node.difficulty) chips.push(makeChip(esc(node.difficulty), `d-${node.difficulty}`, () => {}));
    if (node.flag) chips.push(makeChip(esc(node.flag), "flagchip", "flag"));
    if (node.target) {
      chips.push(makeChip(`<svg class="i" viewBox="0 0 24 24"><circle cx="12" cy="12" r="8" stroke="currentColor" stroke-width="1.7" fill="none"/><circle cx="12" cy="12" r="3.2" fill="currentColor"/></svg>${esc(node.target)}`, "", () => {}));
    }
    for (const tag of node.tag_list) {
      chips.push(makeSelectableChip(`#${esc(tag)}`, "tagchipp", tag));
    }
    chips.push(makeChip("+ properties", "addchip", "props"));
    chips.forEach((el) => D.chips.appendChild(el));
  }

  function makeChip(html, cls, action) {
    const el = document.createElement("span");
    el.className = `chip ${cls}`.trim();
    el.innerHTML = html;
    el.addEventListener("click", (event) => {
      event.stopPropagation();
      if (action === "flag") { copyText(S.note ? S.note.flag : D.statusFlag.textContent); return; }
      if (action === "props") { openProperties(); return; }
      openProperties();
    });
    return el;
  }

  function makeSelectableChip(html, cls, tag) {
    const el = document.createElement("span");
    el.className = `chip ${cls}`.trim();
    el.innerHTML = html;
    const remove = document.createElement("button");
    remove.className = "tagchip-x";
    remove.innerHTML = I.x;
    remove.title = `Remove #${tag}`;
    remove.addEventListener("click", async (event) => {
      event.stopPropagation();
      if (!S.note) return;
      try {
        const tags = S.note.tag_list.filter((t) => t !== tag);
        const node = await api("update_node", { id: S.note.id, tags: tags.join(", ") });
        S.note.tags = node.tags;
        S.note.tag_list = node.tag_list;
        renderChips(S.note);
        await refreshTree();
        toast(`Removed #${tag}`);
      } catch (err) { toast(err.message, true); }
    });
    el.appendChild(remove);
    el.addEventListener("click", () => openProperties());
    return el;
  }

  /* ==================================================================
   * Welcome pane
   * ================================================================ */

  async function renderWelcome() {
    const [stats, recent] = await Promise.all([
      api("stats").catch(() => S.boot.stats),
      api("recent_notes", { limit: 5 }),
    ]);
    D.welcomeStats.innerHTML = [
      ["notes", stats.notes], ["folders", stats.folders], ["flags", stats.flags],
      ["targets", stats.targets], ["pinned", stats.pinned],
    ].map(([label, count]) => `<span class="wall-chip"><b>${count}</b><span>${label}</span></span>`).join("");
    D.welcomeRecent.innerHTML = "";
    if (recent.length) {
      for (const row of recent) {
        const el = document.createElement("button");
        el.className = "recent-row";
        el.innerHTML = `<span class="dot ${row.status}"></span><span class="rt">${esc(row.title)}</span><span class="rp">${esc(row.path || "root")}</span>`;
        el.addEventListener("click", () => selectNode(row.id));
        D.welcomeRecent.appendChild(el);
      }
    } else {
      D.welcomeRecent.insertAdjacentHTML("beforeend", '<p class="welcome-tag" style="margin:0">Nothing here yet — create your first note.</p>');
    }
    const actions = D.welcomeActions;
    actions.innerHTML = "";
    addWelcomeBtn(actions, "New note", "primary", () => openNewNote());
    addWelcomeBtn(actions, "New folder", "ghost", () => openNewFolder());
    addWelcomeBtn(actions, "Snippet library", "ghost", openSnippets);
    if (S.boot.empty && !stats.notes) addWelcomeBtn(actions, "Load demo vault", "ghost", loadDemoVault);
  }

  function addWelcomeBtn(host, label, kind, onClick) {
    const button = document.createElement("button");
    button.className = `btn ${kind}`;
    button.textContent = label;
    button.type = "button";
    button.addEventListener("click", onClick);
    host.appendChild(button);
  }

  async function loadDemoVault() {
    try {
      await api("load_demo");
      await bootData();
      toast("Demo vault loaded");
    } catch (err) { toast(err.message, true); }
  }

  /* ==================================================================
   * Palette (Ctrl+P)
   * ================================================================ */

  const runPalette = debounce(async () => {
    const query = D.paletteInput.value.trim();
    S.paletteResults = query
      ? await api("quick_jump", { query })
      : await api("recent_notes", { limit: 12 });
    S.paletteSel = 0;
    renderPaletteList(query ? "Matches" : "Recent notes");
  }, 120);

  function openPalette() {
    if (topOverlay() === "paletteModal") return;
    openModal("paletteModal");
    D.paletteInput.value = "";
    S.paletteResults = [];
    S.paletteSel = 0;
    runPalette();
  }

  function renderPaletteList(header) {
    D.paletteList.innerHTML = "";
    if (header) {
      const head = document.createElement("div");
      head.className = "snipt-head";
      head.textContent = header;
      D.paletteList.appendChild(head);
    }
    if (!S.paletteResults.length) {
      D.paletteList.insertAdjacentHTML("beforeend", '<div class="mrow-empty">No matching notes</div>');
      return;
    }
    S.paletteResults.forEach((item, index) => {
      const row = document.createElement("div");
      row.className = "mrow" + (index === S.paletteSel ? " hl" : "");
      row.innerHTML = `
        ${I.file}
        <span class="mtitle">${esc(item.title)}</span>
        <span class="mpath">${esc(item.path || "root")}</span>
        ${item.pinned ? `<span class="pinmini" title="Pinned">${I.pin}</span>` : ""}
        ${item.flag ? `<span class="flagmini" title="${esc(item.flag)}">${I.flag}</span>` : ""}
        <span class="dot ${item.status}"></span>`;
      row.addEventListener("click", () => { closeModal("paletteModal"); selectNode(item.id); });
      D.paletteList.appendChild(row);
    });
  }

  function movePaletteSel(delta) {
    if (!S.paletteResults.length) return;
    S.paletteSel = (S.paletteSel + delta + S.paletteResults.length) % S.paletteResults.length;
    renderPaletteList(D.paletteInput.value.trim() ? "Matches" : "Recent notes");
    const active = D.paletteList.querySelectorAll(".mrow")[S.paletteSel];
    if (active) active.scrollIntoView({ block: "nearest" });
  }

  D.paletteInput.addEventListener("input", () => { S.paletteSel = 0; runPalette(); });
  D.paletteInput.addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown") { event.preventDefault(); movePaletteSel(1); }
    else if (event.key === "ArrowUp") { event.preventDefault(); movePaletteSel(-1); }
    else if (event.key === "Enter") {
      event.preventDefault();
      const item = S.paletteResults[S.paletteSel];
      if (item) { closeModal("paletteModal"); selectNode(item.id); }
    }
  });

  /* ==================================================================
   * Global search modal
   * ================================================================ */

  const runSearch = debounce(async () => {
    const query = D.searchInput.value.trim();
    if (!query) { S.searchResults = []; renderSearchList(); return; }
    S.searchResults = await api("search", { query });
    S.searchSel = 0;
    renderSearchList();
  }, 220);

  function openSearchModal() {
    if (topOverlay() === "searchModal") return;
    openModal("searchModal");
    D.searchInput.value = "";
    S.searchResults = [];
    S.searchSel = 0;
    renderSearchList();
  }

  function renderSearchList() {
    D.searchList.innerHTML = "";
    if (!S.searchResults.length) {
      const empty = D.searchInput.value.trim()
        ? '<div class="mrow-empty">No notes match — try fewer words.</div>'
        : '<div class="mrow-empty">Search note bodies, titles, and tags.</div>';
      D.searchList.insertAdjacentHTML("beforeend", empty);
      return;
    }
    S.searchResults.forEach((hit, index) => {
      const row = document.createElement("div");
      row.className = "hitrow" + (index === S.searchSel ? " hl" : "");
      row.innerHTML = `
        <div class="ht">${esc(hit.title)}</div>
        <div class="hp">${esc(hit.path || "root")}</div>
        <div class="hs">${highlightMarkers(hit.snippet)}</div>`;
      row.addEventListener("click", () => { closeModal("searchModal"); selectNode(hit.node_id); });
      row.addEventListener("mousemove", () => {
        if (S.searchSel !== index) {
          S.searchSel = index;
          D.searchList.querySelectorAll(".hitrow").forEach((el, i) => el.classList.toggle("hl", i === index));
        }
      });
      D.searchList.appendChild(row);
    });
  }

  function highlightMarkers(snippet) {
    const safe = esc(snippet);
    let index = safe.indexOf("[");
    if (index < 0) return safe;
    const close = safe.indexOf("]", index + 1);
    if (close < 0) return safe;
    return `${safe.slice(0, index)}<mark>${safe.slice(index + 1, close)}</mark>${safe.slice(close + 1)}`;
  }

  D.searchInput.addEventListener("input", runSearch);
  D.searchInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      const hit = S.searchResults[S.searchSel];
      if (hit) { closeModal("searchModal"); selectNode(hit.node_id); }
    }
  });

  /* ==================================================================
   * Snippets
   * ================================================================ */

  let snippetEditingOpen = false;

  async function openSnippets() {
    openModal("snippetsModal");
    S.snippets = await api("list_snippets");
    S.activeCategory = "__all";
    D.snippetFilter.value = "";
    S.snippetQuery = "";
    S.snippetSel = null;
    renderSnippetCats();
    renderSnippetList();
    renderSnippetDetail();
  }

  function renderSnippetCats() {
    const counts = new Map();
    for (const snippet of S.snippets) {
      const category = snippet.tag_list[0] || "misc";
      counts.set(category, (counts.get(category) || 0) + 1);
    }
    D.snippetCats.innerHTML = "";
    D.snippetCats.appendChild(categoryButton("__all", "All snippets", S.snippets.length));
    for (const [category, count] of [...counts.entries()].sort((a, b) => a[0].localeCompare(b[0]))) {
      D.snippetCats.appendChild(categoryButton(category, category, count));
    }
  }

  function categoryButton(key, label, count) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "scat" + (key === S.activeCategory ? " sel" : "");
    button.textContent = "";
    button.innerHTML = `${esc(label)}<span class="n">${count}</span>`;
    button.addEventListener("click", () => {
      S.activeCategory = key;
      S.snippetSel = null;
      renderSnippetCats();
      renderSnippetList();
      renderSnippetDetail();
    });
    return button;
  }

  function visibleSnippets() {
    const needle = S.snippetQuery.trim().toLowerCase();
    return S.snippets.filter((snippet) => {
      if (S.activeCategory !== "__all" && (snippet.tag_list[0] || "misc") !== S.activeCategory) return false;
      if (!needle) return true;
      return `${snippet.title} ${snippet.command} ${snippet.description}`.toLowerCase().includes(needle);
    });
  }

  function renderSnippetList() {
    const list = visibleSnippets();
    if (!S.snippetSel || !list.includes(S.snippetSel)) S.snippetSel = list[0] || null;
    D.snippetList.innerHTML = "";
    for (const snippet of list) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "snipt" + (snippet === S.snippetSel ? " sel" : "");
      button.innerHTML = `
        <span class="st">${esc(snippet.title)}${snippet.builtin ? "" : `<span class="fed" title="Custom">${I.pen}</span>`}</span>
        <span class="sc">${esc(snippet.command)}</span>`;
      button.addEventListener("click", () => {
        S.snippetSel = snippet;
        renderSnippetList();
        renderSnippetDetail();
      });
      D.snippetList.appendChild(button);
    }
    if (!list.length) D.snippetList.innerHTML = '<div class="mrow-empty">No snippets match.</div>';
  }

  function renderSnippetDetail() {
    const current = S.snippetSel;
    D.snippetDetail.innerHTML = "";
    if (!current) return;
    const target = S.note ? (S.note.target || "") : "";
    const shell = document.createElement("div");
    shell.innerHTML = `
      <div class="sd-title">${esc(current.title)}</div>
      ${current.description ? `<div class="sd-desc">${esc(current.description)}</div>` : ""}
      ${target ? `<div class="sd-desc">Fill from current note target <b>${esc(target)}</b>.</div>` : ""}
      <div class="sd-cmd">${highlightPlaceholders(current.command)}</div>
      <div class="sd-actions">
        <button class="btn ghost" type="button" id="sdCopyRaw">${I.copy} Copy raw</button>
        ${target ? '<button class="btn primary" type="button" id="sdCopyResolved thu">Fill &amp; copy</button>' : ""}
        ${S.note ? '<button class="btn ghost" type="button" id="sdInsert">Insert into note</button>' : ""}
        ${!current.builtin ? '<button class="btn ghost" type="button" id="sdEdit">Edit snippet</button>' : ""}
      </div>`;
    D.snippetDetail.appendChild(shell);
    $id("sdCopyRaw").addEventListener("click", () => copyText(current.command));
    const resolvedButton = $id("sdCopyResolved thu");
    if (resolvedButton) {
      resolvedButton.id = "sdCopyResolved";
      resolvedButton.addEventListener("click", async () => {
        const out = await api("resolve_snippet", { command: current.command, target });
        copyText(out.command);
      });
    }
    const insertButton = $id("sdInsert");
    if (insertButton) insertButton.addEventListener("click", async () => {
      const text = target
        ? await api("resolve_snippet", { command: current.command, target }).then((out) => out.command).catch(() => current.command)
        : current.command;
      insertIntoNote(text);
      closeModal("snippetsModal");
      toast("Snippet inserted");
    });
    const editButton = $id("sdEdit");
    if (editButton) editButton.addEventListener("click", () => openSnippetForm(current));
  }

  function highlightPlaceholders(command) {
    return esc(command).replace(/\{\{([A-Za-z0-9_]+)\}\}/g, '<span class="ph">{{$1}}</span>');
  }

  D.snippetFilter.addEventListener("input", () => {
    S.snippetQuery = D.snippetFilter.value;
    renderSnippetList();
  });

  $id("btnSnippetNew").addEventListener("click", () => openSnippetForm(null));

  function openSnippetForm(snippet) {
    snippetEditingOpen = !!snippet && !snippet.builtin;
    S.editingSnippetId = snippetEditingOpen ? snippet.id : null;
    D.snippetFormTitle.textContent = S.editingSnippetId ? "Edit snippet" : "New snippet";
    D.snipTitle.value = snippet && !snippet.builtin ? snippet.title : "";
    D.snipCommand.value = snippet && !snippet.builtin ? snippet.command : "";
    D.snipDescription.value = snippet && !snippet.builtin ? snippet.description : "";
    D.snipTags.value = snippet && !snippet.builtin ? snippet.tags : "";
    D.btnSnipDelete.style.display = S.editingSnippetId ? "" : "none";
    openModal("snippetFormModal");
  }

  $id("btnSnipSave").addEventListener("click", async () => {
    const payload = {
      title: D.snipTitle.value,
      command: D.snipCommand.value,
      description: D.snipDescription.value,
      tags: D.snipTags.value,
    };
    try {
      if (S.editingSnippetId) {
        await api("update_snippet", Object.assign({ id: S.editingSnippetId }, payload));
      } else {
        await api("create_snippet", payload);
      }
      closeModal("snippetFormModal");
      S.snippets = await api("list_snippets");
      renderSnippetCats();
      renderSnippetList();
      renderSnippetDetail();
      toast("Snippet saved");
    } catch (err) { toast(err.message, true); }
  });

  D.btnSnipDelete.addEventListener("click", () => {
    if (!S.editingSnippetId) return;
    confirmAsk("Delete snippet", "Remove this custom snippet from the vault.", "Delete", async () => {
      try {
        await api("delete_snippet", { id: S.editingSnippetId });
        closeModal("snippetFormModal");
        S.snippets = await api("list_snippets");
        renderSnippetCats();
        renderSnippetList();
        renderSnippetDetail();
        toast("Snippet deleted");
      } catch (err) { toast(err.message, true); }
    });
  });

  function insertIntoNote(text) {
    const editor = D.editor;
    const at = Math.min(editor.selectionEnd, editor.value.length);
    const before = editor.value.slice(0, at);
    const after = editor.value.slice(editor.selectionEnd);
    const newline = before && !before.endsWith("\n") ? "\n" : "";
    editor.value = before + newline + text + "\n" + after;
    editor.selectionStart = editor.selectionEnd = at + newline.length + text.length;
    queueSave();
  }

  /* ==================================================================
   * New note / folder
   * ================================================================ */

  async function openNewNote(parentIdOverride = undefined) {
    if (anyOverlayOpen() && topOverlay() !== "newNoteModal") return;
    S.templates = await api("templates");
    const settings = await api("get_settings");
    const keys = new Set(S.templates.map((template) => template.key));
    S.lastTemplate = keys.has(settings.last_template) ? settings.last_template : "ctf";
    S.selectedTemplate = S.lastTemplate;
    D.newNoteTitle.value = "";
    D.newNoteTarget.value = S.note ? (S.note.target || "") : "";
    fillFolderOptions(D.newNoteParent, parentIdOverride !== undefined ? parentIdOverride : defaultParentId());
    fillFolderOptions(D.newFolderParent, parentIdOverride !== undefined ? parentIdOverride : defaultParentId());
    renderTemplateGrid();
    openModal("newNoteModal");
  }

  function defaultParentId() {
    return S.note ? S.note.parent_id : null;
  }

  function fillFolderOptions(select, selected) {
    select.innerHTML = "";
    const root = document.createElement("option");
    root.value = "";
    root.textContent = "Vault root";
    select.appendChild(root);
    for (const folder of allFolders()) {
      const option = document.createElement("option");
      option.value = String(folder.id);
      option.textContent = "· ".repeat(folder.depth) + folder.title;
      if (folder.id === selected) option.selected = true;
      select.appendChild(option);
    }
  }

  function allFolders() {
    const out = [];
    function walk(children, depth) {
      for (const node of children) {
        if (node.kind === "folder") {
          out.push({ id: node.id, title: node.title, depth });
          if (node.children) walk(node.children, depth + 1);
        }
      }
    }
    walk(S.tree, 0);
    return out;
  }

  function renderTemplateGrid() {
    D.templateGrid.innerHTML = "";
    for (const template of S.templates) {
      const card = document.createElement("button");
      card.type = "button";
      card.className = "tcard" + (template.key === S.selectedTemplate ? " sel" : "");
      card.innerHTML = `<span class="tglyph">${esc(template.glyph)}</span>
        <span class="tname">${esc(template.name)}</span>
        <span class="tdesc">${esc(template.description)}</span>`;
      card.addEventListener("click", () => { S.selectedTemplate = template.key; renderTemplateGrid(); });
      D.templateGrid.appendChild(card);
    }
  }

  $id("btnCreateNote").addEventListener("click", async () => {
    try {
      const node = await api("create_note", {
        template_key: S.selectedTemplate,
        title: D.newNoteTitle.value.trim(),
        target: D.newNoteTarget.value.trim(),
        parent_id: D.newNoteParent.value ? Number(D.newNoteParent.value) : null,
      });
      closeModal("newNoteModal");
      if (node.parent_id) S.expanded.add(node.parent_id);
      await refreshTree();
      await selectNode(node.id);
      toast(`Created “${node.title}”`);
    } catch (err) { toast(err.message, true); }
  });

  async function quickNewNote() {
    const settings = await api("get_settings").catch(() => ({ last_template: "ctf" }));
    const templates = await api("templates").catch(() => []);
    const keys = new Set(templates.map((template) => template.key));
    const templateKey = keys.has(settings.last_template) ? settings.last_template : "ctf";
    try {
      const node = await api("create_note", {
        template_key: templateKey,
        title: "",
        target: S.note ? (S.note.target || "") : "",
        parent_id: defaultParentId(),
      });
      if (node.parent_id) S.expanded.add(node.parent_id);
      await refreshTree();
      await selectNode(node.id);
      toast(`Created “${node.title}” (${templateKey} template)`);
    } catch (err) { toast(err.message, true); }
  }

  async function openNewFolder(parentIdOverride = undefined) {
    if (anyOverlayOpen()) return;
    fillFolderOptions(D.newFolderParent, parentIdOverride !== undefined ? parentIdOverride : defaultParentId());
    D.newFolderTitle.value = "";
    openModal("newFolderModal");
  }

  $id("btnCreateFolder").addEventListener("click", async () => {
    try {
      const node = await api("create_folder", {
        title: D.newFolderTitle.value.trim() || "New folder",
        parent_id: D.newFolderParent.value ? Number(D.newFolderParent.value) : null,
      });
      closeModal("newFolderModal");
      if (node.parent_id) S.expanded.add(node.parent_id);
      S.expanded.add(node.id);
      await refreshTree();
      toast(`Created “${node.title}”`);
    } catch (err) { toast(err.message, true); }
  });

  /* ==================================================================
   * Properties
   * ================================================================ */

  function markPropStatus(status) {
    D.propStatus.querySelectorAll("button").forEach((b) => b.classList.toggle("on", b.dataset.status === status));
  }

  function openProperties() {
    if (!S.note) return;
    D.propsTitle.textContent && (document.querySelector("#propsModal .modal-title").textContent = `Properties — ${S.note.title}`);
    markPropStatus(S.note.status);
    D.propDifficulty.value = S.note.difficulty || "";
    D.propTarget.value = S.note.target || "";
    D.propTags.value = S.note.tags || "";
    D.propFlag.value = S.note.flag || "";
    const path = S.note.path || "vault root";
    D.propStats.textContent = `Created ${S.note.created_at.slice(0, 10)} · Modified ${S.note.updated_at.slice(0, 16).replace("T", " ")} · in ${path}`;
    openModal("propsModal");
  }

  D.propStatus.addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (button) markPropStatus(button.dataset.status);
  });

  $id("btnPropSave").addEventListener("click", async () => {
    if (!S.note) { closeModal("propsModal"); return; }
    const statusButton = D.propStatus.querySelector(".on");
    try {
      const node = await api("update_node", {
        id: S.note.id,
        status: statusButton ? statusButton.dataset.status : S.note.status,
        difficulty: D.propDifficulty.value,
        target: D.propTarget.value.trim(),
        tags: D.propTags.value,
        flag: D.propFlag.value.trim(),
      });
      closeModal("propsModal");
      Object.assign(S.note, {
        status: node.status,
        difficulty: node.difficulty,
        target: node.target,
        tags: node.tags,
        tag_list: node.tag_list,
        flag: node.flag,
      });
      renderChips(S.note);
      const hasFlag = !!S.note.flag;
      D.statusFlag.classList.toggle("hidden", !hasFlag);
      D.statusFlag.textContent = S.note.flag || "";
      await refreshTree();
      toast("Properties saved");
    } catch (err) { toast(err.message, true); }
  });

  $id("btnPropTrash").addEventListener("click", () => {
    if (S.note) confirmTrash(S.note);
  });

  D.btnPin.addEventListener("click", () => {
    if (S.note) togglePinById(S.note.id);
  });

  function focusTitle() {
    if (!S.note) return;
    D.titleInput.focus();
    D.titleInput.select();
  }

  async function renameCurrent(title) {
    if (!S.note) return;
    const name = title.trim() || "Untitled";
    try {
      const node = await api("rename", { id: S.note.id, title: name });
      S.note.title = node.title;
      D.titleInput.value = node.title;
      renderCrumb(node);
      updateStatusLocation();
      await refreshTree();
      toast("Renamed");
    } catch (err) { toast(err.message, true); }
  }

  D.titleInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      D.titleInput.blur();
      D.editor.focus();
    } else if (event.key === "Escape") {
      event.preventDefault();
      D.titleInput.value = S.note ? S.note.title : "";
      D.titleInput.blur();
    }
  });
  D.titleInput.addEventListener("change", () => {
    if (!S.note) return;
    const value = D.titleInput.value.trim();
    if (value && value !== S.note.title) renameCurrent(value);
  });
  D.titleInput.addEventListener("blur", () => {
    if (S.note) D.titleInput.value = S.note.title;
  });

  /* ==================================================================
   * Trash
   * ================================================================ */

  async function openTrash() {
    openModal("trashModal");
    await refreshTrash();
  }

  async function refreshTrash() {
    const items = await api("trashed_nodes");
    D.trashList.innerHTML = "";
    for (const node of items) {
      const row = document.createElement("div");
      row.className = "trow";
      row.innerHTML = `
        <span style="width:15px;flex:none;color:var(--faint)">${node.kind === "folder" ? I.folder : I.file}</span>
        <span class="tt">${esc(node.title)}</span>
        <span class="td">${esc(node.trashed_at || "")}</span>`;
      const restoreButton = document.createElement("button");
      restoreButton.className = "btn tiny ghost";
      restoreButton.textContent = "Restore";
      restoreButton.addEventListener("click", async () => {
        try {
          await api("restore_node", { id: node.id });
          await refreshTrash();
          await refreshTree();
          if (S.note) await selectNode(S.note.id, { keepFocus: true });
          toast("Restored");
        } catch (err) { toast(err.message, true); }
      });
      const purgeButton = document.createElement("button");
      purgeButton.className = "btn tiny danger-ghost";
      purgeButton.textContent = "Delete forever";
      purgeButton.addEventListener("click", () => {
        confirmAsk("Delete forever", `Delete <b>${esc(node.title)}</b> and its children permanently?`, "Delete forever", async () => {
          try {
            await api("trash_node", { id: node.id });
            await refreshTrash();
            await refreshTree();
          } catch (err) { toast(err.message, true); }
        });
      });
      row.append(restoreButton, purgeButton);
      D.trashList.appendChild(row);
    }
    if (!items.length) D.trashList.innerHTML = '<div class="trow-empty">Trash is empty.</div>';
    D.trashCount.textContent = plural(items.length, "item");
  }

  $id("btnEmptyTrash").addEventListener("click", () => {
    confirmAsk("Empty the trash", "All trashed items will be permanently deleted.", "Empty trash", async () => {
      try {
        await api("empty_trash");
        await refreshTrash();
        await refreshTree();
        toast("Trash emptied");
      } catch (err) { toast(err.message, true); }
    });
  });

  async function trashNode(id) {
    try {
      const result = await api("trash_node", { id, permanent: false });
      const wasSelected = S.selectedId === id;
      closeModal("propsModal");
      if (wasSelected) {
        S.note = null;
        S.selectedId = null;
        D.noteArea.classList.add("hidden");
        D.welcomePane.classList.remove("hidden");
        setSaveState("idle");
        updateStatusLocation();
      }
      await refreshTree();
      if (wasSelected) renderWelcome();
      toast(result && result.removed > 1 ? `Moved ${plural(result.removed, "item")} to trash` : "Moved to trash");
    } catch (err) { toast(err.message, true); }
  }

  /* ==================================================================
   * Dashboard
   * ================================================================ */

  async function openDashboard() {
    openModal("dashboardModal");
    await renderDashboard();
  }

  async function renderDashboard() {
    const [stats, flags, tags] = await Promise.all([
      api("stats"),
      api("collected_flags"),
      api("tag_counts"),
    ]);
    D.dashCards.innerHTML = [
      ["Notes", stats.notes, ""], ["Folders", stats.folders, ""],
      ["Flags", stats.flags, "daccent"], ["Targets", stats.targets, ""],
      ["Tags", stats.tags, ""], ["Pinned", stats.pinned, ""],
    ].map(([label, count, cls]) => `<div class="dcard ${cls}"><b>${count}</b><span>${label}</span></div>`).join("");
    D.dashFlags.innerHTML = "";
    if (!flags.length) {
      D.dashFlags.innerHTML = '<div class="mrow-empty">No flags captured yet. Set one in note properties — or paste a flag in a note body.</div>';
    }
    for (const hit of flags) {
      const row = document.createElement("div");
      row.className = "frow";
      row.title = `Open “${hit.title}”`;
      row.innerHTML = `
        <span class="ff">${esc(hit.flag)}</span>
        <span class="fn">${esc(hit.title)}</span>`;
      const copyButton = document.createElement("button");
      copyButton.className = "tbtn";
      copyButton.title = "Copy flag";
      copyButton.innerHTML = I.copy;
      copyButton.addEventListener("click", (event) => {
        event.stopPropagation();
        copyText(hit.flag);
      });
      row.appendChild(copyButton);
      row.addEventListener("click", () => { closeModal("dashboardModal"); selectNode(hit.node_id); });
      D.dashFlags.appendChild(row);
    }
    D.dashTags.innerHTML = '<div class="tagcloud"></div>';
    const cloud = D.dashTags.querySelector(".tagcloud");
    if (!tags.length) {
      D.dashTags.insertAdjacentHTML("beforeend", '<div class="mrow-empty">No tags yet.</div>');
    }
    for (const tag of tags) {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "tagchip";
      chip.innerHTML = `${esc(tag.tag)} <b>${tag.count}</b>`;
      chip.addEventListener("click", () => showTaggedNotes(tag.tag));
      cloud.appendChild(chip);
    }
  }

  async function showTaggedNotes(tag) {
    const notes = await api("notes_tagged", { tag });
    D.dashFlags.innerHTML = "";
    const back = document.createElement("button");
    back.className = "btn tiny ghost";
    back.type = "button";
    back.style.alignSelf = "flex-start";
    back.style.marginBottom = "6px";
    back.textContent = `← Back to flags (#${esc(tag)})`;
    back.addEventListener("click", renderDashboard);
    D.dashFlags.appendChild(back);
    if (!notes.length) {
      D.dashFlags.insertAdjacentHTML("beforeend", '<div class="mrow-empty">No notes with this tag.</div>');
    }
    for (const node of notes) {
      const row = document.createElement("div");
      row.className = "frow";
      row.innerHTML = `<span class="ff" style="color:var(--text);font-family:var(--font-ui);font-size:12.5px">${esc(node.title)}</span><span class="fn">${esc(node.path || "root")}</span>`;
      row.addEventListener("click", () => { closeModal("dashboardModal"); selectNode(node.id); });
      D.dashFlags.appendChild(row);
    }
  }

  /* ==================================================================
   * Settings
   * ================================================================ */

  function markThemeSeg(theme) {
    D.setTheme.querySelectorAll("button").forEach((b) => b.classList.toggle("on", b.dataset.theme === theme));
  }

  async function openSettings() {
    if (anyOverlayOpen()) return;
    const data = await api("get_settings");
    D.setVaultPath.textContent = S.boot ? S.boot.vault_path : "";
    D.setVersion.textContent = S.boot ? `RedScribe v${S.boot.version}` : "";
    markThemeSeg(data.theme || S.theme);
    D.setRestore.checked = (data.restore_last_note || "1") !== "0";
    D.setSyncScroll.checked = (data.sync_preview_scroll || "1") !== "0";
    D.setFontSize.value = String(clamp(Number(data.font_size) || S.fontSize, 9, 18));
    openModal("settingsModal");
  }

  D.setTheme.addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    markThemeSeg(button.dataset.theme);
    applyTheme(button.dataset.theme);
    saveSettings({ theme: button.dataset.theme });
  });

  for (let size = 9; size <= 18; size += 1) {
    const option = document.createElement("option");
    option.value = String(size);
    option.textContent = `${size} px`;
    D.setFontSize.appendChild(option);
  }

  D.setFontSize.addEventListener("change", () => {
    applyFontSize(Number(D.setFontSize.value));
    saveSettings({ font_size: Number(D.setFontSize.value) });
  });

  D.setRestore.addEventListener("change", () => saveSettings({ restore_last_note: D.setRestore.checked ? "1" : "0" }));
  D.setSyncScroll.addEventListener("change", () => {
    S.syncScroll = D.setSyncScroll.checked;
    saveSettings({ sync_preview_scroll: D.setSyncScroll.checked ? "1" : "0" });
  });

  $id("btnCopyVault").addEventListener("click", () => copyText(D.setVaultPath.textContent || ""));

  /* ==================================================================
   * Exports
   * ================================================================ */

  let exportMenu = null;

  function showExportMenu(anchor) {
    hideMenus();
    if (!exportMenu) {
      exportMenu = document.createElement("div");
      exportMenu.className = "menu";
      document.body.appendChild(exportMenu);
    }
    exportMenu.innerHTML = `
      <div class="menu-label">This note</div>
      <button type="button" data-act="md">${I.dl} Export as Markdown <small>.md</small></button>
      <button type="button" data-act="html">${I.dl} Export as HTML <small>.html</small></button>
      <div class="ctx-sep"></div>
      <div class="menu-label">Whole vault</div>
      <button type="button" data-act="vault">${I.dl} Browsable HTML report</button>`;
    const rect = anchor.getBoundingClientRect();
    exportMenu.style.top = `${rect.bottom + 6}px`;
    exportMenu.style.left = `${clamp(rect.right - 248, 8, window.innerWidth - 260)}px`;
    exportMenu.style.display = "";
    exportMenu.addEventListener("click", (event) => {
      const button = event.target.closest("button");
      if (!button) return;
      hideMenus();
      if (!S.note && button.dataset.act !== "vault") { toast("Open a note first", true); return; }
      triggerDownload(button.dataset.act === "vault" ? "/download/vault/html" : `/download/note/${S.note.id}/${button.dataset.act}`);
    });
  }

  function triggerDownload(url) {
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    toast("Export started");
  }

  function hideMenus() {
    if (exportMenu) { exportMenu.style.display = "none"; }
    D.ctxMenu.classList.add("hidden");
  }

  $id("btnExport").addEventListener("click", (event) => {
    event.stopPropagation();
    if (exportMenu && exportMenu.style.display !== "none") { hideMenus(); return; }
    showExportMenu($id("btnExport"));
  });

  /* ==================================================================
   * Context menu on the tree
   * ================================================================ */

  function showTreeCtx(event, node) {
    event.preventDefault();
    event.stopPropagation();
    if (node.kind === "note" && S.selectedId !== node.id) selectNode(node.id, { keepFocus: true });
    hideMenus();
    D.ctxMenu.innerHTML = "";
    contextItemsFor(node).forEach((item, index) => {
      if (item === "-") {
        D.ctxMenu.appendChild(document.createElement("div")).className = "ctx-sep";
        return;
      }
      const button = document.createElement("button");
      button.type = "button";
      button.innerHTML = `${item.icon}<span>${esc(item.label)}</span>${item.key ? `<span class="ctx-k">${esc(item.key)}</span>` : ""}`;
      if (item.danger) button.classList.add("danger");
      button.addEventListener("click", () => { hideMenus(); item.run(); });
      D.ctxMenu.appendChild(button);
    });
    D.ctxMenu.classList.remove("hidden");
    positionMenu(D.ctxMenu, event);
  }

  function contextItemsFor(node) {
    const items = [];
    if (node.kind === "folder") {
      items.push({ icon: I.fileNew, label: "New note inside", run: () => openNewNote(node.id) });
      items.push({ icon: I.folderNew, label: "New folder inside", run: () => openNewFolder(node.id) });
    } else {
      items.push({ icon: I.fileNew, label: "New note (last template)", run: () => quickNewNote() });
    }
    if (node.kind === "note") {
      items.push({ icon: I.pen, label: "Rename title", key: "F2", run: focusTitle });
    }
    items.push({ icon: I.dup, label: "Duplicate", run: () => duplicateNode(node.id) });
    if (node.kind === "note") {
      items.push({ icon: I.pin, label: node.pinned ? "Unpin note" : "Pin note", key: "Ctrl⇧P", run: () => togglePinById(node.id) });
    }
    items.push("-");
    items.push({ icon: I.trash, label: "Move to trash", key: "Del", danger: true, run: () => confirmTrash(node) });
    return items;
  }

  async function duplicateNode(id) {
    try {
      await api("duplicate_node", { id });
      const source = S.nodes.get(id);
      if (source && source.parent_id !== null) S.expanded.add(source.parent_id);
      await refreshTree();
      toast("Duplicated");
    } catch (err) { toast(err.message, true); }
  }

  async function togglePinById(id) {
    const node = S.nodes.get(id);
    if (!node) return;
    const updated = await api("set_pinned", { id, pinned: !node.pinned });
    node.pinned = updated.pinned;
    renderTree();
    if (S.note && S.note.id === id) {
      S.note.pinned = updated.pinned;
      D.btnPin.classList.toggle("on", updated.pinned);
    }
    toast(updated.pinned ? "Note pinned" : "Note unpinned");
  }

  function confirmTrash(node) {
    const what = node.kind === "folder" ? "and everything inside it" : "";
    confirmAsk("Move to trash", `Move <b>${esc(node.title)}</b> ${what} to the trash?`, "Move to trash", () => trashNode(node.id));
  }

  function positionMenu(menu, event) {
    menu.style.top = "";
    menu.style.left = "";
    const rect = menu.getBoundingClientRect();
    let x = event.clientX + 2;
    let y = event.clientY + 2;
    if (x + rect.width > window.innerWidth - 8) x = event.clientX - rect.width - 2;
    if (y + rect.height > window.innerHeight - 8) y = window.innerHeight - rect.height - 8;
    menu.style.left = `${Math.max(8, x)}px`;
    menu.style.top = `${Math.max(8, y)}px`;
  }

  document.addEventListener("mousedown", (event) => {
    if (!event.target.closest("#ctxMenu") && !event.target.closest(".menu") && !event.target.closest("#btnExport")) {
      hideMenus();
    }
  });

  /* ==================================================================
   * Help
   * ================================================================ */

  const HELP_GROUPS = [
    [
      ["Ctrl P", "Quick switch"],
      ["Ctrl ⇧ F", "Full-text search"],
      ["Ctrl ⇧ S", "Snippet library"],
      ["Ctrl ⇧ D", "Dashboard"],
      ["Ctrl N", "New note (last template)"],
      ["Ctrl ⇧ N", "New folder"],
      ["Ctrl ,", "Settings"],
      ["F1", "This help"],
    ],
    [
      ["Ctrl S", "Save now"],
      ["Ctrl E", "Cycle Editor › Split › Preview"],
      ["Ctrl ⇧ P", "Pin or unpin note"],
      ["F2", "Note properties"],
      ["Delete", "Move tree item to trash"],
      ["Ctrl ↑ / ↓", "Reorder in the vault"],
    ],
    [
      ["Ctrl B", "Bold"],
      ["Ctrl I", "Italic"],
      ["Ctrl K", "Inline code"],
      ["Ctrl ⇧ X", "Strikethrough"],
      ["Tab / ⇧ Tab", "Indent / outdent"],
      ["↵", "Continue a list"],
    ],
  ];

  function renderHelp() {
    D.helpGrid.innerHTML = "";
    for (const group of HELP_GROUPS) {
      for (const [keys, description] of group) {
        const item = document.createElement("div");
        item.className = "help-item";
        item.innerHTML = `<span class="keys">${keys.split(" ").map((k) => `<kbd>${esc(k)}</kbd>`).join("")}</span><span class="desc">${esc(description)}</span>`;
        D.helpGrid.appendChild(item);
      }
    }
  }

  /* ==================================================================
   * Editor behaviors
   * ================================================================ */

  D.editor.addEventListener("input", queueSave);

  D.editor.addEventListener("scroll", () => {
    if (!S.syncScroll || S.viewMode !== "split") return;
    const previewHeight = D.previewScroll.scrollHeight - D.previewScroll.clientHeight;
    const editorHeight = D.editor.scrollHeight - D.editor.clientHeight;
    if (previewHeight <= 0 || editorHeight <= 0) return;
    D.previewScroll.scrollTop = (D.editor.scrollTop / editorHeight) * previewHeight;
  });

  D.editor.addEventListener("keydown", (event) => {
    const control = event.ctrlKey || event.metaKey;
    if (event.key === "Tab") {
      event.preventDefault();
      indentSelection(event.shiftKey);
      return;
    }
    if (event.key === "Enter" && !control && !event.shiftKey) {
      if (continueList()) event.preventDefault();
      return;
    }
    if (!control) return;
    const key = event.key.toLowerCase();
    if (key === "b") { event.preventDefault(); wrapSelection("**", "**", "bold text"); return; }
    if (key === "i") { event.preventDefault(); wrapSelection("*", "*", "italic"); return; }
    if (key === "k") { event.preventDefault(); wrapSelection("`", "`", "code"); return; }
    if (event.shiftKey && key === "x") { event.preventDefault(); wrapSelection("~~", "~~", "struck out"); }
  });

  function indentSelection(outdent) {
    const { value, selectionStart, selectionEnd } = D.editor;
    const lineStart = value.lastIndexOf("\n", selectionStart - 1) + 1;
    let lineEnd = value.indexOf("\n", selectionEnd);
    if (lineEnd < 0) lineEnd = value.length;
    const lines = value.slice(lineStart, lineEnd).split("\n");
    const shifted = lines.map((line) => (outdent ? line.replace(/^(\t| {1,4})/, "") : `    ${line}`));
    const replacement = shifted.join("\n");
    D.editor.setRangeText(replacement, lineStart, lineEnd, "end");
    D.editor.selectionStart = lineStart;
    D.editor.selectionEnd = lineStart + replacement.length;
    queueSave();
  }

  function wrapSelection(prefix, suffix, placeholder) {
    const { value, selectionStart, selectionEnd } = D.editor;
    const selected = value.slice(selectionStart, selectionEnd);
    if (selected.startsWith(prefix) && selected.endsWith(suffix)) {
      const inner = selected.slice(prefix.length, selected.length - suffix.length);
      D.editor.setRangeText(inner, selectionStart, selectionEnd, "end");
      D.editor.selectionStart = selectionStart;
      D.editor.selectionEnd = selectionStart + inner.length;
    } else {
      const inner = selected || placeholder;
      D.editor.setRangeText(prefix + inner + suffix, selectionStart, selectionEnd, "end");
      D.editor.selectionStart = selectionStart + prefix.length;
      D.editor.selectionEnd = selectionStart + prefix.length + inner.length;
    }
    D.editor.focus();
    queueSave();
  }

  function continueList() {
    const { value, selectionStart } = D.editor;
    const lineStart = value.lastIndexOf("\n", selectionStart - 1) + 1;
    let lineEnd = value.indexOf("\n", selectionStart);
    if (lineEnd < 0) lineEnd = value.length;
    const line = value.slice(lineStart, lineEnd);
    const match = /^(\s*)([-+*] \[[ xX]\] |[-+*] |\d{1,9}[.)] )(.*)$/.exec(line);
    if (!match) return false;
    if (match[2] === "" || match[3].trim() === "") {
      return false;
    }
    let marker = match[2];
    const numbered = /^(\d{1,9})([.)]) $/.exec(marker);
    if (numbered) marker = `${Number(numbered[1]) + 1}${numbered[2]} `;
    D.editor.setRangeText(`\n${match[1]}${marker}`, selectionStart, selectionStart, "end");
    queueSave();
    return true;
  }

  /* ==================================================================
   * Sashes
   * ================================================================ */

  function attachSash(el, apply, finish) {
    el.addEventListener("pointerdown", (event) => {
      event.preventDefault();
      el.setPointerCapture(event.pointerId);
      el.classList.add("dragging");
      const onMove = (moveEvent) => apply(moveEvent);
      const onUp = () => {
        el.classList.remove("dragging");
        el.removeEventListener("pointermove", onMove);
        el.removeEventListener("pointerup", onUp);
        el.removeEventListener("pointercancel", onUp);
        if (finish) finish();
      };
      el.addEventListener("pointermove", onMove);
      el.addEventListener("pointerup", onUp);
      el.addEventListener("pointercancel", onUp);
    });
  }

  attachSash(
    D.sidebarSash,
    (event) => {
      const width = clamp(event.clientX, 200, 460);
      D.sidebar.style.width = `${width}px`;
    },
    () => saveSettings({ sidebar_width: Math.round(D.sidebar.getBoundingClientRect().width) }),
  );

  attachSash(
    $id("splitSash"),
    (event) => {
      const rect = D.split.getBoundingClientRect();
      const fraction = clamp((event.clientX - rect.left) / rect.width, 0.25, 0.85);
      applySplitSash(fraction * 100);
      S.splitPos = fraction * 100;
    },
    () => {
      if (S.splitPos !== null) saveSettings({ split_sash: Math.round(S.splitPos) });
    },
  );

  function applySplitSash(percent) {
    D.editorPane.style.flex = `0 0 ${percent}%`;
    D.previewPane.style.flex = "1 1 0";
  }

  /* ==================================================================
   * Global shortcuts
   * ================================================================ */

  document.addEventListener("keydown", (event) => {
    const control = event.ctrlKey || event.metaKey;
    const key = event.key;

    if (key === "Escape") {
      if (anyOverlayOpen()) { closeTopOverlay(); event.preventDefault(); }
      else if (!D.ctxMenu.classList.contains("hidden")) hideMenus();
      return;
    }

    if (anyOverlayOpen()) {
      if (topOverlay() === "helpModal" && key === "F1") { closeTopOverlay(); event.preventDefault(); return; }
      return;
    }

    if (control && !event.shiftKey && (key === "p" || key === "P")) { event.preventDefault(); openPalette(); return; }
    if (control && event.shiftKey && (key === "p" || key === "P")) { event.preventDefault(); if (S.note) togglePinById(S.note.id); return; }
    if (control && event.shiftKey && (key === "f")) { event.preventDefault(); openSearchModal(); return; }
    if (!control && event.shiftKey && (key === "F")) { /* Shift alone does nothing */ }
    if (control && event.shiftKey && (key === "s")) { event.preventDefault(); openSnippets(); return; }
    if (control && event.shiftKey && (key === "d")) { event.preventDefault(); openDashboard(); return; }
    if (control && event.shiftKey && (key === "N" || key === "n")) { event.preventDefault(); openNewFolder(); return; }
    if (control && !event.shiftKey && (key === "n" || key === "N")) { event.preventDefault(); quickNewNote(); return; }
    if (control && (key === "e" || key === "E")) { event.preventDefault(); cycleView(); return; }
    if (control && (key === "s" || key === "S")) { event.preventDefault(); flushSave().then(() => toast("Saved")); return; }
    if (control && key === ",") { event.preventDefault(); openSettings(); return; }
    if (key === "F1") { event.preventDefault(); renderHelp(); openModal("helpModal"); return; }
    if (key === "F2") { event.preventDefault(); if (S.note) { openProperties(); setTimeout(() => D.propTarget.focus(), 20); } return; }

    const typing = event.target === D.editor
      || document.activeElement instanceof HTMLInputElement
      || document.activeElement instanceof HTMLTextAreaElement
      || document.activeElement instanceof HTMLSelectElement;
    if (typing) return;

    if (key === "Delete" && S.selectedId && S.nodes.get(S.selectedId)) {
      confirmAsk("Move to trash", `Move <b>${esc(S.nodes.get(S.selectedId).title)}</b> to the trash?`, "Move to trash", () => trashNode(S.selectedId));
      return;
    }
    if (control && key === "ArrowUp" && S.selectedId) { event.preventDefault(); reorderSelected(-1); return; }
    if (control && key === "ArrowDown" && S.selectedId) { event.preventDefault(); reorderSelected(1); }
  });

  async function reorderSelected(offset) {
    try {
      await api("reorder_node", { id: S.selectedId, offset });
      await refreshTree();
    } catch (err) { toast(err.message, true); }
  }

  /* ==================================================================
   * Toolbar wiring
   * ================================================================ */

  $id("paletteTrigger").addEventListener("click", openPalette);
  $id("btnSearchAll").addEventListener("click", openSearchModal);
  $id("btnSnippets").addEventListener("click", openSnippets);
  $id("btnDashboard").addEventListener("click", openDashboard);
  $id("btnNewNote").addEventListener("click", () => openNewNote());
  $id("btnNewFolder").addEventListener("click", () => openNewFolder());
  $id("btnTheme").addEventListener("click", () => {
    const next = S.theme === "dark" ? "light" : "dark";
    applyTheme(next);
    markThemeSeg(next);
    saveSettings({ theme: next });
  });
  $id("btnSettings").addEventListener("click", openSettings);
  $id("btnHelp").addEventListener("click", () => { renderHelp(); openModal("helpModal"); });
  $id("btnTrash").addEventListener("click", openTrash);
  $id("btnProps").addEventListener("click", openProperties);

  $id("viewSeg").querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => setViewMode(button.dataset.view));
  });

  $id("brandHome").addEventListener("click", () => {
    flushSave();
    S.note = null;
    S.selectedId = null;
    D.noteArea.classList.add("hidden");
    D.welcomePane.classList.remove("hidden");
    updateStatusLocation();
    setSaveState("idle");
    renderTree();
    renderWelcome();
  });

  document.querySelectorAll("[data-close]").forEach((button) => {
    button.addEventListener("click", () => {
      const overlay = button.closest(".overlay");
      if (overlay) closeModal(overlay.id);
    });
  });

  document.querySelectorAll("[data-modal]").forEach((overlay) => {
    overlay.addEventListener("mousedown", (event) => {
      if (event.target === overlay) closeModal(overlay.id);
    });
  });

  D.statusFlag.addEventListener("click", () => copyText(D.statusFlag.textContent || ""));

  /* ==================================================================
   * Boot
   * ================================================================ */

  async function bootData() {
    S.boot = await api("boot");
    applyTheme(S.boot.theme);
    applyFontSize(S.boot.font_size);
    applyViewMode(S.boot.view_mode);
    S.syncScroll = S.boot.sync_preview_scroll !== false;
    S.restoreLastNote = S.boot.restore_last_note;
    S.lastTemplate = S.boot.last_template || "ctf";
    if (S.boot.split_sash) applySplitSash(S.boot.split_sash);
    if (S.boot.sidebar_width) D.sidebar.style.width = `${S.boot.sidebar_width}px`;
    D.setSyncScroll.checked = S.syncScroll;
    refreshTree();
    const wanted = S.boot.restore_last_note ? S.boot.last_note : null;
    if (wanted) {
      const restored = await api("node", { id: wanted }).catch(() => null);
      if (restored && restored.kind === "note") {
        await selectNode(wanted, { keepFocus: false });
        return;
      }
    }
    await renderWelcome();
  }

  bootData().catch((err) => toast(`Failed to load the vault: ${err.message}`, true, 8000));
})();
