(() => {
  "use strict";

  function parseMaybeJson(value) {
    if (typeof value !== "string") return value;
    const text = value.trim();
    if (!text || !(text.startsWith("{") || text.startsWith("["))) return value;
    try {
      return JSON.parse(text);
    } catch (_) {
      return value;
    }
  }

  function extractMessage(value, depth = 0) {
    if (value == null || depth > 6) return null;

    const parsed = parseMaybeJson(value);
    if (parsed !== value) return extractMessage(parsed, depth + 1);
    if (typeof parsed !== "object") return null;

    if (typeof parsed.error === "string" && parsed.error.trim()) {
      return parsed.error.trim();
    }
    if (parsed.error && typeof parsed.error === "object") {
      const nestedError = extractMessage(parsed.error, depth + 1);
      if (nestedError) return nestedError;
    }

    if (typeof parsed.message === "string" && parsed.message.trim()) {
      const message = parsed.message.trim();
      if (!/^Request failed with status code \d+$/i.test(message)) return message;
    }

    for (const key of ["response", "data", "body", "result", "payload", "detail"]) {
      if (parsed[key] == null) continue;
      const nested = extractMessage(parsed[key], depth + 1);
      if (nested) return nested;
    }
    return null;
  }

  function readableFallback(error) {
    const status = error && error.response && error.response.status
      ? error.response.status
      : error && error.status
        ? error.status
        : null;
    return status
      ? `请求失败（HTTP ${status}）：后端未返回可读的错误详情。`
      : "请求失败：后端未返回可读的错误详情。";
  }

  function patchBridge() {
    const bridge = window.AstrBotPluginPage;
    if (!bridge || bridge.__airiVoiceErrorPatch) return;

    for (const method of ["apiPost", "apiGet", "upload"]) {
      if (typeof bridge[method] !== "function") continue;
      const original = bridge[method].bind(bridge);
      bridge[method] = (...args) => Promise.resolve().then(() => original(...args)).catch((error) => {
        const message = extractMessage(error) || readableFallback(error);
        throw {
          error: { message },
          body: error && error.response ? error.response.data : undefined,
          original: error,
        };
      });
    }
    bridge.__airiVoiceErrorPatch = true;
  }

  patchBridge();
  const timer = window.setInterval(() => {
    patchBridge();
    if (window.AstrBotPluginPage && window.AstrBotPluginPage.__airiVoiceErrorPatch) {
      window.clearInterval(timer);
    }
  }, 100);
})();
