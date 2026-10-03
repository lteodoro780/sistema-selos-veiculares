"use strict";
(() => {
  const video = document.getElementById("qr-video");
  const canvas = document.getElementById("qr-canvas");
  const context = canvas.getContext("2d", {willReadFrequently: true});
  const startButton = document.getElementById("camera-start");
  const stopButton = document.getElementById("camera-stop");
  const flipButton = document.getElementById("camera-flip");
  const status = document.getElementById("camera-status");
  const placeholder = document.getElementById("camera-placeholder");
  const form = document.getElementById("lookup-form");
  const photo = document.getElementById("qr-photo");
  let stream = null, timer = null, facing = "environment", generation = 0, submitting = false;
  const say = message => { status.textContent = message; };
  function stop() {
    generation++;
    clearTimeout(timer);
    if (stream) stream.getTracks().forEach(track => track.stop());
    stream = null;
    video.srcObject = null;
    placeholder.hidden = false;
    startButton.hidden = false;
    startButton.disabled = false;
    stopButton.hidden = flipButton.hidden = true;
  }
  function submitCode(value) {
    if (submitting) return;
    if (!navigator.onLine) { say("Sem conexão. Reconecte ao Wi-Fi antes de consultar a validade."); return; }
    submitting = true;
    stop();
    document.getElementById("seal-code").value = value;
    say("QR Code lido. Consultando a situação no banco…");
    form.requestSubmit();
  }
  function decode(source, width, height, maxWidth = 960) {
    if (!width || !height) return null;
    const scale = Math.min(1, maxWidth / Math.max(width, height));
    canvas.width = Math.round(width * scale);
    canvas.height = Math.round(height * scale);
    context.drawImage(source, 0, 0, canvas.width, canvas.height);
    const pixels = context.getImageData(0, 0, canvas.width, canvas.height);
    return window.jsQR(pixels.data, pixels.width, pixels.height, {inversionAttempts: "attemptBoth"});
  }
  function readFrame(session) {
    if (!stream || session !== generation) return;
    try {
      if (video.readyState >= 2) {
        const result = decode(video, video.videoWidth, video.videoHeight);
        if (result?.data) { submitCode(result.data); if (submitting) return; }
      }
    } catch (_error) {
      stop(); say("Não foi possível ler a imagem. Tente novamente ou use uma foto do QR."); return;
    }
    timer = setTimeout(() => readFrame(session), 150);
  }
  async function start() {
    stop();
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
      document.getElementById("secure-warning").hidden = false;
      say("Câmera indisponível. Use HTTPS confiável no celular ou consulte pelo número."); return;
    }
    if (typeof window.jsQR !== "function") { say("O leitor não carregou. Atualize a página ou consulte pelo número."); return; }
    const session = generation;
    startButton.disabled = true;
    stopButton.hidden = false;
    say("Aguardando permissão para abrir a câmera…");
    try {
      const opened = await navigator.mediaDevices.getUserMedia({audio: false, video: {facingMode: {ideal: facing}, width: {ideal: 1280}, height: {ideal: 720}}});
      if (session !== generation) { opened.getTracks().forEach(track => track.stop()); return; }
      stream = opened; video.srcObject = stream;
      await video.play();
      if (session !== generation) return;
      placeholder.hidden = true; startButton.hidden = true;
      startButton.disabled = false; stopButton.hidden = flipButton.hidden = false;
      say("Aproxime o QR Code. Mantenha a câmera firme e evite reflexos.");
      readFrame(session);
    } catch (error) {
      if (session !== generation) return;
      stop();
      const messages = {NotAllowedError: "Permissão negada. Autorize a câmera nas opções do navegador ou use uma foto.", NotFoundError: "Nenhuma câmera encontrada. Escolha uma foto ou digite o número.", NotReadableError: "A câmera está em uso por outro aplicativo. Feche-o e tente novamente."};
      say(messages[error.name] || "Não foi possível abrir a câmera. Tente uma foto ou consulte pelo número.");
    }
  }
  startButton.addEventListener("click", start);
  stopButton.addEventListener("click", () => { stop(); say("Câmera desligada."); });
  flipButton.addEventListener("click", () => { facing = facing === "environment" ? "user" : "environment"; start(); });
  photo.addEventListener("change", async () => {
    stop();
    const file = photo.files[0];
    if (!file) return;
    if (file.size > 15 * 1024 * 1024) { say("Escolha uma imagem com até 15 MB."); photo.value = ""; return; }
    if (typeof window.jsQR !== "function") { say("O leitor não carregou. Atualize a página ou consulte pelo número."); return; }
    const url = URL.createObjectURL(file);
    try {
      say("Lendo a foto neste aparelho…");
      const picture = new Image();
      await new Promise((resolve, reject) => { picture.onload = resolve; picture.onerror = reject; picture.src = url; });
      const result = decode(picture, picture.naturalWidth, picture.naturalHeight, 1600);
      if (result?.data) submitCode(result.data);
      else say("Nenhum QR encontrado. Recorte a foto para destacar o código ou digite o número.");
    } catch (_error) { say("Não foi possível ler essa foto. Tente uma imagem JPG/PNG ou digite o número."); }
    finally { URL.revokeObjectURL(url); photo.value = ""; }
  });
  form.addEventListener("submit", event => {
    if (!navigator.onLine) { event.preventDefault(); submitting = false; say("Sem conexão: não é possível validar o selo. Reconecte ao computador."); return; }
    stop();
  });
  window.addEventListener("pagehide", stop);
  window.addEventListener("pageshow", () => { submitting = false; });
  document.addEventListener("visibilitychange", () => { if (document.hidden) { stop(); say("Câmera pausada. Toque em abrir câmera para continuar."); } });
  if (!window.isSecureContext) document.getElementById("secure-warning").hidden = false;
})();
