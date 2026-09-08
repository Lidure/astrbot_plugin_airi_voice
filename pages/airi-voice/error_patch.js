(() => {
  "use strict";

  function extractMessage(error) {
    const payload = error && error.response && error.response.data
      ? error.response.data
      : error && error.data
        ? error.data
        : error && error.body
          ? error.body
          : null;
    return payload && payload.error && payload.error.message ? payload.error.message : null;
  }

  function patchBridge() {
    const bridge = window.AstrBotPluginPage;
    if (!bridge || bridge.__airiVoiceErrorPatch) return;

    for (const method of ["apiPost", "apiGet", "upload"]) {
      if (typeof bridge[method] !== "function") continue;
      const original = bridge[method].bind(bridge);
      bridge[method] = (...args) => original(...args).catch((error) => {
        const message = extractMessage(error);
        if (message) {
          throw { error: { message }, body: error && error.response ? error.response.data : undefined };
        }
        throw error;
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
