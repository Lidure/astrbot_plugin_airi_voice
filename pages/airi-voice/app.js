(() => {
  "use strict";

  const state = { items: [], query: "", source: "", loading: false, error: "" };
  let pendingDeleteId = null;

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
    uploadForm: document.getElementById("upload-form"),
    keyword: document.getElementById("keyword-input"),
    file: document.getElementById("file-input"),
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
      actions.append(
        makeButton("试听", "button button-small button-secondary", () => playVoice(item)),
        makeButton("删除", "button button-small button-danger", () => openDeleteDialog(item), item.source === "builtin"),
      );
      row.append(name, source, extension, size, actions);
      elements.list.append(row);
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

  async function uploadVoice(event) {
    event.preventDefault();
    const keyword = elements.keyword.value.trim();
    const file = elements.file.files && elements.file.files[0];
    if (!keyword || !file) { showError(new Error("请填写关键词并选择音频文件。")); return; }
    setLoading(true, "正在上传语音…");
    showError(null);
    try {
      const endpoint = `voices/upload/${encodeURIComponent(keyword)}`;
      const response = await bridge().upload(endpoint, file);
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
      const response = await bridge().apiDelete(`voices/${encodeURIComponent(voiceId)}`);
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
      await loadVoices();
      elements.status.textContent = "语音目录已重载。";
    } catch (error) {
      showError(error);
      elements.status.textContent = "重载未完成。";
    } finally {
      setLoading(false);
    }
  }

  async function playVoice(item) {
    setLoading(true, "正在获取音频预览…");
    showError(null);
    try {
      const response = await bridge().apiGet(`voices/${encodeURIComponent(item.id)}/audio`);
      let payload = await readResponse(response);
      // AstrBot bridge versions differ: some unwrap {status: "ok", data},
      // while others return the JSON body directly.
      if (payload && payload.status === "ok" && payload.data && typeof payload.data === "object") {
        payload = payload.data;
      }
      if (!payload || typeof payload.data !== "string") throw new Error("音频数据无效");
      const binary = atob(payload.data);
      const bytes = new Uint8Array(binary.length);
      for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
      const blob = new Blob([bytes], { type: payload.content_type || "application/octet-stream" });
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      audio.addEventListener("ended", () => URL.revokeObjectURL(url), { once: true });
      audio.addEventListener("error", () => URL.revokeObjectURL(url), { once: true });
      await audio.play();
      elements.status.textContent = `正在试听：${item.name || "语音"}。`;
    } catch (error) {
      showError(error);
      elements.status.textContent = "无法播放该语音。";
    } finally {
      setLoading(false);
    }
  }

  elements.search.addEventListener("input", () => { state.query = elements.search.value.trim(); loadVoices(); });
  elements.source.addEventListener("change", () => { state.source = elements.source.value; loadVoices(); });
  elements.refresh.addEventListener("click", reloadVoices);
  elements.uploadForm.addEventListener("submit", uploadVoice);
  elements.confirmDelete.addEventListener("click", (event) => { event.preventDefault(); deleteVoice(); });
  elements.deleteDialog.addEventListener("close", () => { pendingDeleteId = null; });

  window.AiriVoicePage = { state, loadVoices, uploadVoice, deleteVoice, reloadVoices, playVoice };
  loadVoices();
})();
