(() => {
  "use strict";

  const state = {
    items: [],
    keywordItems: [],
    query: "",
    source: "",
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
    refresh: document.getElementById("refresh-button"),
    audioTab: document.getElementById("audio-tab"),
    keywordsTab: document.getElementById("keywords-tab"),
    audioView: document.getElementById("audio-management-view"),
    keywordView: document.getElementById("keyword-management-view"),
    keywordList: document.getElementById("keyword-list"),
    keywordTable: document.getElementById("keyword-table"),
    keywordEmpty: document.getElementById("keyword-empty-state"),
    uploadForm: document.getElementById("upload-form"),
    keyword: document.getElementById("keyword-input"),
    file: document.getElementById("file-input"),
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
      return { audio_hex: value.audio_hex, content_type: value.content_type || value.contentType };
    }
    for (const key of ["data", "body", "result", "payload"]) {
      const nested = extractAudioPayload(value[key]);
      if (nested) return nested;
    }
    return null;
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
    showError(null);
    if (keywords) loadKeywords();
    else loadVoices();
  }

  function renderVoices() {
    elements.list.replaceChildren();
    elements.total.textContent = String(state.items.length);
    elements.empty.hidden = state.items.length !== 0;
    elements.table.hidden = state.items.length === 0;
    for (const item of state.items) {
      const row = document.createElement("tr");
      const name = document.createElement("td");
      name.textContent = item.name || "未命名语音";
      const source = document.createElement("td");
      source.textContent = sourceLabel(item.source);
      const extension = document.createElement("td");
      extension.textContent = item.extension || "—";
      const size = document.createElement("td");
      size.textContent = displaySize(item.size);
      const actions = document.createElement("td");
      actions.className = "row-actions";
      const configuredReadOnly = typeof item.id === "string" && item.id.startsWith("extra_voices:configured/");
      actions.append(
        makeButton("试听", "button button-small button-secondary", () => playVoice(item)),
        makeButton("删除", "button button-small button-danger", () => openDeleteDialog(item), configuredReadOnly),
      );
      row.append(name, source, extension, size, actions);
      elements.list.append(row);
    }
  }

  function renderKeywords() {
    elements.keywordList.replaceChildren();
    elements.keywordEmpty.hidden = state.keywordItems.length !== 0;
    elements.keywordTable.hidden = state.keywordItems.length === 0;

    for (const item of state.keywordItems) {
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
      const aliasTotal = state.keywordItems.reduce(
        (total, item) => total + (Array.isArray(item.aliases) ? item.aliases.length : 0),
        0,
      );
      elements.status.textContent = `共 ${state.keywordItems.length} 个主关键词，${aliasTotal} 个额外触发关键词。`;
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
    if (!keyword || !file) { showError(new Error("请填写关键词并选择音频文件。")); return; }
    setLoading(true, "正在上传语音…");
    showError(null);
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
      await loadVoices();
      elements.status.textContent = "语音已上传并刷新列表。";
    } catch (error) {
      showError(error);
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
      const endpoint = `keywords/aliases/add?voice_id=${encodeURIComponent(item.id)}&alias=${encodeURIComponent(alias)}`;
      const response = await bridge().apiPost(endpoint);
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
      const endpoint = `keywords/aliases/remove?voice_id=${encodeURIComponent(item.id)}&alias=${encodeURIComponent(alias)}`;
      const response = await bridge().apiPost(endpoint);
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
    elements.deleteDescription.textContent = `确定要删除“${item.name || "此语音"}”吗？此操作无法撤销。`;
    if (typeof elements.deleteDialog.showModal === "function") elements.deleteDialog.showModal();
  }

  async function deleteVoice() {
    if (!pendingDeleteId) return;
    const voiceId = pendingDeleteId;
    setLoading(true, "正在删除语音…");
    showError(null);
    try {
      const response = await bridge().apiPost(`voices/${encodeURIComponent(voiceId)}/delete`);
      await readResponse(response);
      pendingDeleteId = null;
      elements.deleteDialog.close();
      await loadVoices();
      elements.status.textContent = "语音已删除并刷新列表。";
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
      if (!payload || typeof payload.audio_hex !== "string") throw new Error("音频数据无效");
      if (!/^[0-9a-f]*$/i.test(payload.audio_hex) || payload.audio_hex.length % 2 !== 0) {
        throw new Error("音频响应不是有效的音频数据");
      }
      const bytes = new Uint8Array(payload.audio_hex.length / 2);
      for (let index = 0; index < bytes.length; index += 1) {
        bytes[index] = Number.parseInt(payload.audio_hex.slice(index * 2, index * 2 + 2), 16);
      }
      if (!isCurrentPreviewRequest(requestVersion)) return;
      const blob = new Blob([bytes], { type: payload.content_type || "application/octet-stream" });
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

  elements.search.addEventListener("input", () => { state.query = elements.search.value.trim(); loadVoices(); });
  elements.source.addEventListener("change", () => { state.source = elements.source.value; loadVoices(); });
  elements.refresh.addEventListener("click", reloadVoices);
  elements.audioTab.addEventListener("click", () => setActiveView("audio"));
  elements.keywordsTab.addEventListener("click", () => setActiveView("keywords"));
  elements.uploadForm.addEventListener("submit", uploadVoice);
  elements.confirmDelete.addEventListener("click", (event) => { event.preventDefault(); deleteVoice(); });
  elements.deleteDialog.addEventListener("close", () => { pendingDeleteId = null; });
  elements.audio.addEventListener("error", () => stopCurrentAudio({ hide: true }));
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
    playVoice, stopCurrentAudio,
    addAlias,
    removeAlias,
    setActiveView,
  };
  loadVoices();
})();
