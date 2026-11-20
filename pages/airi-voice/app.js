(() => {
  "use strict";

  const state = {
    items: [],
    keywordItems: [],
    query: "",
    keywordQuery: "",
    source: "",
    sort: "name",
    activeView: "audio",
    loading: false,
    error: "",
  };
  let pendingDeleteId = null;
  let currentAudioUrl = null;
  let currentVoice = null;
  let previewRequestVersion = 0;

  const elements = {
    error: document.getElementById("error-message"),
    status: document.getElementById("status-message"),
    total: document.getElementById("voice-total"),
    list: document.getElementById("voice-list"),
    table: document.getElementById("voice-table"),
    empty: document.getElementById("empty-state"),
    search: document.getElementById("search-input"),
    source: document.getElementById("source-filter"),
    sort: document.getElementById("sort-filter"),
    clearSearch: document.getElementById("clear-search"),
    clearKeywordSearch: document.getElementById("clear-keyword-search"),
    fileFeedback: document.getElementById("file-feedback"),
    audioStop: document.getElementById("audio-player-stop"),
    refresh: document.getElementById("refresh-button"),
    audioTab: document.getElementById("audio-tab"),
    keywordsTab: document.getElementById("keywords-tab"),
    audioView: document.getElementById("audio-management-view"),
    keywordView: document.getElementById("keyword-management-view"),
    keywordList: document.getElementById("keyword-list"),
    keywordTable: document.getElementById("keyword-table"),
    keywordEmpty: document.getElementById("keyword-empty-state"),
    keywordSearch: document.getElementById("keyword-search-input"),
    uploadForm: document.getElementById("upload-form"),
    keyword: document.getElementById("keyword-input"),
    file: document.getElementById("file-input"),
    uploadFeedback: document.getElementById("upload-feedback"),
    audioCard: document.getElementById("audio-player-card"),
    audioTitle: document.getElementById("audio-player-title"),
    audioSource: document.getElementById("audio-player-source"),
    audio: document.getElementById("audio-player"),
    audioMiniPlay: document.getElementById("audio-player-mini-play"),
    audioToggle: document.getElementById("audio-player-toggle"),
    deleteDialog: document.getElementById("delete-dialog"),
    deleteDescription: document.getElementById("delete-description"),
    confirmDelete: document.getElementById("confirm-delete-button"),
  };

  function bridge() {
    const pageBridge = window.AstrBotPluginPage;
    if (!pageBridge) throw new Error("AstrBot 页面桥接不可用，请从 AstrBot 控制台打开此页面。");
    return pageBridge;
  }

  function messageFrom(error, fallback) {
    if (error && typeof error === "object" && error.error && error.error.message) return error.error.message;
    if (error && typeof error === "object" && error.body && error.body.error && error.body.error.message) return error.body.error.message;
    if (error instanceof Error && error.message) return error.message;
    return fallback;
  }

  async function readResponse(response) {
    if (response && typeof response.ok === "boolean" && !response.ok) {
      let payload = null;
      try { payload = await response.json(); } catch (_) { /* use generic error below */ }
      throw payload || new Error("请求未成功完成。");
    }
    if (response && typeof response.json === "function") return response.json();
    if (response && response.error) throw response;
    if (response && response.body && response.body.error) throw response.body;
    return response;
  }

  function setLoading(loading, statusText) {
    state.loading = loading;
    document.querySelectorAll("[data-mutation]").forEach((control) => { control.disabled = loading; });
    if (statusText) elements.status.textContent = statusText;
  }

  function showError(error) {
    state.error = error ? messageFrom(error, "操作未完成，请稍后重试。") : "";
    elements.error.textContent = state.error;
    elements.error.hidden = !state.error;
  }

  function showUploadFeedback(message, kind = "") {
    elements.uploadFeedback.textContent = message || "";
    elements.uploadFeedback.hidden = !message;
    elements.uploadFeedback.classList.toggle("is-success", kind === "success");
    elements.uploadFeedback.classList.toggle("is-error", kind === "error");
  }

  function displaySize(bytes) {
    if (!Number.isFinite(bytes) || bytes < 0) return "未知";
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  function sourceLabel(source) {
    return { builtin: "插件内置", user_added: "已上传", extra_voices: "额外目录" }[source] || "其他来源";
  }

  function extractAudioPayload(value) {
    if (typeof value === "string") {
      const text = value.trim();
      if (text.startsWith("{") || text.startsWith("[")) {
        try {
          return extractAudioPayload(JSON.parse(text));
        } catch (_) {
          // Fall through and let the caller show a clear invalid-payload error.
        }
      }
      return { audio_hex: value };
    }
    if (!value || typeof value !== "object") return null;
    if (value.status === "error") {
      throw new Error(value.message || "音频接口返回错误");
    }
    if (typeof value.audio_hex === "string") {
      return { audio_hex: value.audio_hex, content_type: value.content_type || value.contentType, filename: value.filename || "" };
    }
    for (const key of ["data", "body", "result", "payload"]) {
      const nested = extractAudioPayload(value[key]);
      if (nested) return nested;
    }
    return null;
  }

  function audioBlobFromPayload(payload) {
    if (!payload || typeof payload.audio_hex !== "string") throw new Error("音频数据无效");
    const hex = payload.audio_hex;
    if (!hex.length || hex.length % 2 !== 0 || !/^[0-9a-f]+$/i.test(hex)) {
      throw new Error("音频响应不是有效的音频数据");
    }
    const bytes = new Uint8Array(hex.length / 2);
    for (let index = 0; index < bytes.length; index += 1) {
      bytes[index] = Number.parseInt(hex.slice(index * 2, index * 2 + 2), 16);
    }
    return new Blob([bytes], { type: payload.content_type || "application/octet-stream" });
  }

  function audioDownloadFilename(payload, item) {
    const extension = item.extension === ".silk" ? ".wav" : (item.extension || ".wav");
    const fallback = `${item.name || "语音"}${extension}`;
    const name = String(payload.filename || fallback).split(/[\\/]/).pop();
    return name && name !== "." && name !== ".." ? name : fallback;
  }
  function stopCurrentAudio({ hide = false } = {}) {
    const audio = elements.audio;
    audio.pause();
    audio.removeAttribute("src");
    audio.load();
    if (currentAudioUrl) URL.revokeObjectURL(currentAudioUrl);
    currentAudioUrl = null;
    currentVoice = null;
    if (hide) elements.audioCard.hidden = true;
  }

  function isCurrentPreviewRequest(requestVersion) {
    return requestVersion === previewRequestVersion;
  }

  function showAudioPlayer(item, url) {
    stopCurrentAudio();
    currentAudioUrl = url;
    currentVoice = item;
    elements.audio.src = url;
    elements.audioTitle.textContent = item.name || "未命名语音";
    elements.audioSource.textContent = sourceLabel(item.source);
    elements.audioCard.hidden = false;
    setPlayerMini(false);
  }

  function setPlayerMini(mini) {
    elements.audioCard.classList.toggle("is-mini", mini);
    elements.audioToggle.setAttribute("aria-expanded", String(!mini));
    elements.audioToggle.textContent = mini ? "展开" : "收起";
  }

  function updateMiniPlayLabel() {
    const playing = !elements.audio.paused && !elements.audio.ended;
    elements.audioMiniPlay.textContent = playing ? "暂停" : "播放";
    elements.audioMiniPlay.setAttribute("aria-label", playing ? "暂停播放" : "开始播放");
  }

  function makeButton(label, className, callback, disabled = false) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = className;
    button.textContent = label;
    button.disabled = disabled || state.loading;
    button.dataset.mutation = "";
    button.addEventListener("click", callback);
    return button;
  }

  function setActiveView(view) {
    const keywords = view === "keywords";
    state.activeView = keywords ? "keywords" : "audio";
    elements.audioView.hidden = keywords;
    elements.keywordView.hidden = !keywords;
    elements.audioTab.classList.toggle("is-active", !keywords);
    elements.keywordsTab.classList.toggle("is-active", keywords);
    elements.audioTab.setAttribute("aria-selected", String(!keywords));
    elements.keywordsTab.setAttribute("aria-selected", String(keywords));
    elements.audioTab.tabIndex = keywords ? -1 : 0;
    elements.keywordsTab.tabIndex = keywords ? 0 : -1;
    try { window.history.replaceState(null, "", `#${keywords ? "keywords" : "audio"}`); } catch (_) { /* Embedded iframe may restrict history. */ }
    showError(null);
    if (keywords) loadKeywords();
    else loadVoices();
  }

  function applyVoiceSort(items) {
    const sorted = [...items];
    const nameCompare = (a, b) => String(a.name || "").localeCompare(String(b.name || ""), "zh-CN", { numeric: true, sensitivity: "base" });
    if (state.sort === "name-desc") sorted.sort((a, b) => nameCompare(b, a));
    else if (state.sort === "size-desc") sorted.sort((a, b) => (Number(b.size) || 0) - (Number(a.size) || 0) || nameCompare(a, b));
    else if (state.sort === "size") sorted.sort((a, b) => (Number(a.size) || 0) - (Number(b.size) || 0) || nameCompare(a, b));
    else sorted.sort(nameCompare);
    return sorted;
  }

  function renderVoices() {
    elements.list.replaceChildren();
    elements.total.textContent = String(state.items.length);
    elements.empty.hidden = state.items.length !== 0;
    elements.table.hidden = state.items.length === 0;
    for (const item of applyVoiceSort(state.items)) {
      const row = document.createElement("tr");
      const name = document.createElement("td");
      const nameWrap = document.createElement("div");
      nameWrap.className = "voice-name";
      const icon = document.createElement("span");
      icon.className = "voice-file-icon";
      icon.textContent = "♫";
      icon.setAttribute("aria-hidden", "true");
      const nameText = document.createElement("span");
      nameText.className = "voice-name-label";
      nameText.textContent = item.name || "未命名语音";
      nameWrap.append(icon, nameText);
      name.append(nameWrap);
      const source = document.createElement("td");
      source.textContent = sourceLabel(item.source);
      source.className = "source-label";
      const extension = document.createElement("td");
      const extChip = document.createElement("span");
      extChip.className = "extension-chip";
      extChip.textContent = (item.extension || "—").replace(/^\./, "").toUpperCase();
      extension.append(extChip);
      const size = document.createElement("td");
      size.textContent = displaySize(item.size);
      const actions = document.createElement("td");
      actions.className = "row-actions";
      const configuredPoolEntry = typeof item.id === "string" && item.id.startsWith("extra_voices:configured/");
      actions.append(
        makeButton("试听", "button button-small button-secondary", () => playVoice(item), !item.available),
        makeButton("下载", "button button-small button-secondary", () => downloadVoice(item), !item.available),
        makeButton("删除", "button button-small button-danger", () => openDeleteDialog(item), !configuredPoolEntry && !item.available),
      );
      row.append(name, source, extension, size, actions);
      elements.list.append(row);
    }
  }

  function filteredKeywordItems() {
    const query = state.keywordQuery.trim().toLocaleLowerCase();
    if (!query) return state.keywordItems;
    return state.keywordItems.filter((item) => {
      const primary = String(item.name || "").toLocaleLowerCase();
      const aliases = Array.isArray(item.aliases) ? item.aliases : [];
      return primary.includes(query) || aliases.some((alias) => String(alias).toLocaleLowerCase().includes(query));
    });
  }

  function renderKeywords() {
    const visibleItems = filteredKeywordItems();
    elements.keywordList.replaceChildren();
    elements.keywordEmpty.hidden = visibleItems.length !== 0;
    elements.keywordTable.hidden = visibleItems.length === 0;
    const visibleAliasTotal = visibleItems.reduce(
      (total, item) => total + (Array.isArray(item.aliases) ? item.aliases.length : 0),
      0,
    );
    elements.status.textContent = `当前显示 ${visibleItems.length} / ${state.keywordItems.length} 个主关键词，${visibleAliasTotal} 个额外触发关键词。`;

    for (const item of visibleItems) {
      const row = document.createElement("tr");
      const primary = document.createElement("td");
      const primaryName = document.createElement("strong");
      primaryName.textContent = item.name || "未命名语音";
      primary.append(primaryName);
      if (!item.available) {
        const unavailable = document.createElement("span");
        unavailable.className = "keyword-unavailable";
        unavailable.textContent = "文件暂不可用";
        primary.append(unavailable);
      }

      const source = document.createElement("td");
      source.textContent = sourceLabel(item.source);
      source.className = "source-label";

      const aliases = document.createElement("td");
      aliases.className = "alias-list";
      const aliasValues = Array.isArray(item.aliases) ? item.aliases : [];
      if (aliasValues.length === 0) {
        const empty = document.createElement("span");
        empty.className = "alias-empty";
        empty.textContent = "暂无额外关键词";
        aliases.append(empty);
      } else {
        for (const alias of aliasValues) {
          const chip = document.createElement("span");
          chip.className = "alias-chip";
          const label = document.createElement("span");
          label.textContent = alias;
          const remove = document.createElement("button");
          remove.type = "button";
          remove.className = "alias-chip-remove";
          remove.textContent = "×";
          remove.title = `删除额外关键词：${alias}`;
          remove.setAttribute("aria-label", `删除额外关键词 ${alias}`);
          remove.dataset.mutation = "";
          remove.disabled = state.loading;
          remove.addEventListener("click", () => removeAlias(item, alias));
          chip.append(label, remove);
          aliases.append(chip);
        }
      }

      const addCell = document.createElement("td");
      const form = document.createElement("form");
      form.className = "alias-form";
      const input = document.createElement("input");
      input.type = "text";
      input.maxLength = 120;
      input.placeholder = "输入额外触发关键词";
      input.setAttribute("aria-label", `为 ${item.name} 添加额外触发关键词`);
      const addButton = document.createElement("button");
      addButton.type = "submit";
      addButton.className = "button button-small";
      addButton.textContent = "添加";
      addButton.dataset.mutation = "";
      addButton.disabled = state.loading;
      form.addEventListener("submit", (event) => addAlias(event, item, input));
      form.append(input, addButton);
      addCell.append(form);

      row.append(primary, source, aliases, addCell);
      elements.keywordList.append(row);
    }
  }

  async function loadVoices() {
    setLoading(true, "正在加载语音列表…");
    showError(null);
    try {
      const response = await bridge().apiGet("voices", { q: state.query, source: state.source });
      const payload = await readResponse(response);
      state.items = Array.isArray(payload && payload.items) ? payload.items : [];
      renderVoices();
      elements.status.textContent = `已显示 ${state.items.length} 个语音。`;
    } catch (error) {
      state.items = [];
      renderVoices();
      showError(error);
      elements.status.textContent = "无法加载语音列表。";
    } finally {
      setLoading(false);
    }
  }

  async function loadKeywords() {
    setLoading(true, "正在加载关键词列表…");
    showError(null);
    try {
      const response = await bridge().apiGet("keywords");
      const payload = await readResponse(response);
      state.keywordItems = Array.isArray(payload && payload.items) ? payload.items : [];
      renderKeywords();
    } catch (error) {
      state.keywordItems = [];
      renderKeywords();
      showError(error);
      elements.status.textContent = "无法加载关键词列表。";
    } finally {
      setLoading(false);
    }
  }

  async function uploadVoice(event) {
    event.preventDefault();
    const keyword = elements.keyword.value.trim();
    const file = elements.file.files && elements.file.files[0];
    if (!keyword || !file) {
      const error = new Error("请填写关键词并选择音频文件。");
      showError(error);
      showUploadFeedback(`❌ ${error.message}`, "error");
      return;
    }
    setLoading(true, "正在上传语音…");
    showError(null);
    showUploadFeedback("");
    try {
      const dotIndex = file.name.lastIndexOf(".");
      const extension = dotIndex >= 0 ? file.name.slice(dotIndex) : "";
      const uploadFile = new File([file], `${keyword}${extension}`, {
        type: file.type,
        lastModified: file.lastModified,
      });
      const response = await bridge().upload("voices/upload", uploadFile);
      await readResponse(response);
      elements.uploadForm.reset();
      updateFileFeedback();
      await loadVoices();
      showUploadFeedback(`✅ 语音「${keyword}」上传成功，已刷新列表。`, "success");
      elements.status.textContent = `语音「${keyword}」上传成功。`;
    } catch (error) {
      showError(error);
      showUploadFeedback(`❌ 上传失败：${messageFrom(error, "操作未完成，请稍后重试。")}`, "error");
      elements.status.textContent = "上传未完成。";
    } finally {
      setLoading(false);
    }
  }

  async function addAlias(event, item, input) {
    event.preventDefault();
    const alias = input.value.trim();
    if (!alias) { showError(new Error("请输入要添加的额外触发关键词。")); return; }
    setLoading(true, `正在为“${item.name}”添加关键词…`);
    showError(null);
    try {
      const response = await bridge().apiPost("keywords/aliases/add", { voice_id: item.id, alias });
      await readResponse(response);
      input.value = "";
      await loadKeywords();
      elements.status.textContent = `已为“${item.name}”添加额外触发关键词“${alias}”。`;
    } catch (error) {
      showError(error);
      elements.status.textContent = "添加关键词未完成。";
    } finally {
      setLoading(false);
    }
  }

  async function removeAlias(item, alias) {
    setLoading(true, `正在删除额外关键词“${alias}”…`);
    showError(null);
    try {
      const response = await bridge().apiPost("keywords/aliases/remove", { voice_id: item.id, alias });
      await readResponse(response);
      await loadKeywords();
      elements.status.textContent = `已删除额外触发关键词“${alias}”。`;
    } catch (error) {
      showError(error);
      elements.status.textContent = "删除关键词未完成。";
    } finally {
      setLoading(false);
    }
  }

  function openDeleteDialog(item) {
    pendingDeleteId = item.id;
    const configuredPoolEntry = typeof item.id === "string" && item.id.startsWith("extra_voices:configured/");
    elements.deleteDescription.textContent = configuredPoolEntry
      ? `将永久删除“${item.name || "此语音"}”在服务器上的原始音频文件，同时移除“额外语音文件池”中的配置引用。删除不可撤销，请先备份需要保留的音频。确定继续吗？`
      : `将永久删除“${item.name || "此语音"}”在服务器上的原始音频文件。此操作不可撤销，请先备份。确定继续吗？`;
    elements.confirmDelete.textContent = "永久删除";
    if (typeof elements.deleteDialog.showModal === "function") elements.deleteDialog.showModal();
  }

  async function deleteVoice() {
    if (!pendingDeleteId) return;
    const voiceId = pendingDeleteId;
    setLoading(true, "正在删除语音…");
    showError(null);
    try {
      const response = await bridge().apiPost(`voices/${encodeURIComponent(voiceId)}/delete`);
      const outcome = await readResponse(response);
      pendingDeleteId = null;
      elements.deleteDialog.close();
      await loadVoices();
      elements.status.textContent = outcome && outcome.file_deleted === false
        ? "已清除失效的文件池引用；原始音频此前已不存在。"
        : "原始音频已永久删除，语音目录已更新。";
    } catch (error) {
      showError(error);
      elements.status.textContent = "删除未完成。";
    } finally {
      setLoading(false);
    }
  }

  async function reloadVoices() {
    setLoading(true, "正在重载语音目录…");
    showError(null);
    try {
      const response = await bridge().apiPost("voices/reload");
      await readResponse(response);
      if (state.activeView === "keywords") await loadKeywords();
      else await loadVoices();
      elements.status.textContent = "语音目录已重载。";
    } catch (error) {
      showError(error);
      elements.status.textContent = "重载未完成。";
    } finally {
      setLoading(false);
    }
  }

  async function downloadVoice(item) {
    if (state.loading || !item.available) return;
    setLoading(true, `正在准备下载“${item.name || "语音"}”…`);
    showError(null);
    let objectUrl = null;
    try {
      const response = await bridge().apiGet(`voices/${encodeURIComponent(item.id)}/audio`);
      const payload = extractAudioPayload(await readResponse(response));
      const blob = audioBlobFromPayload(payload);
      const filename = audioDownloadFilename(payload, item);
      objectUrl = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = objectUrl;
      link.download = filename;
      link.hidden = true;
      document.body.append(link);
      try { link.click(); } finally { link.remove(); }
      elements.status.textContent = `已发起下载：${filename}。请查看浏览器下载记录。`;
    } catch (error) {
      showError(error);
      elements.status.textContent = "下载未完成。";
    } finally {
      // Keep the Blob URL alive until the browser has accepted the download.
      if (objectUrl) window.setTimeout(() => URL.revokeObjectURL(objectUrl), 30000);
      setLoading(false);
    }
  }
  async function playVoice(item) {
    const requestVersion = ++previewRequestVersion;
    stopCurrentAudio({ hide: true });
    setLoading(true, "正在获取音频预览…");
    showError(null);
    try {
      const response = await bridge().apiGet(`voices/${encodeURIComponent(item.id)}/audio`);
      if (!isCurrentPreviewRequest(requestVersion)) return;
      const payload = extractAudioPayload(await readResponse(response));
      if (!isCurrentPreviewRequest(requestVersion)) return;
      const blob = audioBlobFromPayload(payload);
      if (!isCurrentPreviewRequest(requestVersion)) return;
      const url = URL.createObjectURL(blob);
      showAudioPlayer(item, url);
      await elements.audio.play();
      if (!isCurrentPreviewRequest(requestVersion)) return;
      elements.status.textContent = `正在试听：${item.name || "语音"}。`;
    } catch (error) {
      if (!isCurrentPreviewRequest(requestVersion)) return;
      stopCurrentAudio({ hide: true });
      showError(error);
      elements.status.textContent = "无法播放该语音。";
    } finally {
      if (isCurrentPreviewRequest(requestVersion)) setLoading(false);
    }
  }

  let searchTimer = null;
  function scheduleVoiceSearch() {
    state.query = elements.search.value.trim();
    elements.clearSearch.hidden = !state.query;
    if (searchTimer) window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(loadVoices, 260);
  }
  function updateFileFeedback() {
    const file = elements.file.files && elements.file.files[0];
    elements.fileFeedback.textContent = file ? file.name + "（" + displaySize(file.size) + "）" : "尚未选择文件";
    if (file && !elements.keyword.value.trim()) elements.keyword.value = file.name.replace(/\.[^.]+$/, "");
  }
  function focusActiveSearch() {
    const active = state.activeView === "keywords" ? elements.keywordSearch : elements.search;
    active.focus();
    active.select();
  }
  elements.search.addEventListener("input", scheduleVoiceSearch);
  elements.clearSearch.addEventListener("click", () => { elements.search.value = ""; scheduleVoiceSearch(); elements.search.focus(); });
  elements.keywordSearch.addEventListener("input", () => { elements.clearKeywordSearch.hidden = !elements.keywordSearch.value.trim(); });
  elements.clearKeywordSearch.addEventListener("click", () => { elements.keywordSearch.value = ""; state.keywordQuery = ""; elements.clearKeywordSearch.hidden = true; renderKeywords(); elements.keywordSearch.focus(); });
  elements.sort.addEventListener("change", () => { state.sort = elements.sort.value; renderVoices(); });
  elements.file.addEventListener("change", updateFileFeedback);
  window.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") { event.preventDefault(); focusActiveSearch(); }
    if (event.key === "Escape" && !elements.audioCard.hidden && !elements.deleteDialog.open) { ++previewRequestVersion; stopCurrentAudio({ hide: true }); }
  });
  [elements.audioTab, elements.keywordsTab].forEach((tab, index, tabs) => {
    tab.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      const next = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : (index + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
      tabs[next].click(); tabs[next].focus();
    });
  });
  elements.keywordSearch.addEventListener("input", () => {
    state.keywordQuery = elements.keywordSearch.value.trim();
    renderKeywords();
  });
  elements.source.addEventListener("change", () => { state.source = elements.source.value; loadVoices(); });
  elements.refresh.addEventListener("click", reloadVoices);
  elements.audioTab.addEventListener("click", () => setActiveView("audio"));
  elements.keywordsTab.addEventListener("click", () => setActiveView("keywords"));
  elements.uploadForm.addEventListener("submit", uploadVoice);
  elements.confirmDelete.addEventListener("click", (event) => { event.preventDefault(); deleteVoice(); });
  elements.deleteDialog.addEventListener("close", () => { pendingDeleteId = null; });
  elements.audio.addEventListener("error", () => stopCurrentAudio({ hide: true }));
  elements.audioStop.addEventListener("click", () => { ++previewRequestVersion; stopCurrentAudio({ hide: true }); });
  elements.audioToggle.addEventListener("click", () => {
    setPlayerMini(!elements.audioCard.classList.contains("is-mini"));
  });
  elements.audioMiniPlay.addEventListener("click", async () => {
    if (elements.audio.ended) elements.audio.currentTime = 0;
    if (elements.audio.paused) await elements.audio.play();
    else elements.audio.pause();
    updateMiniPlayLabel();
  });
  elements.audio.addEventListener("play", updateMiniPlayLabel);
  elements.audio.addEventListener("pause", updateMiniPlayLabel);
  elements.audio.addEventListener("ended", updateMiniPlayLabel);
  window.addEventListener("beforeunload", () => stopCurrentAudio());

  window.AiriVoicePage = {
    state,
    loadVoices,
    loadKeywords,
    uploadVoice,
    deleteVoice,
    reloadVoices,
    playVoice, downloadVoice, stopCurrentAudio,
    applyVoiceSort, updateFileFeedback, focusActiveSearch,
    addAlias,
    removeAlias,
    setActiveView,
  };
  if (window.location.hash === "#keywords") setActiveView("keywords");
  else loadVoices();
})();
