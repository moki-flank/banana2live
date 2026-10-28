/**
 * banano2live - UI 通知与日志助手模块
 */
(function (root) {
  function showNotification(message, type = 'info') {
    const toast = document.getElementById('b2lToast');
    if (!toast) return;
    toast.textContent = message;
    toast.className = 'b2l-toast show ' + type;
    clearTimeout(toast._timer);
    toast._timer = setTimeout(() => {
      toast.classList.remove('show');
    }, 3400);
  }

  function appendLog(msg) {
    const logBox = document.getElementById('logBox');
    if (!logBox) return;
    const now = new Date().toLocaleTimeString();
    const div = document.createElement('div');
    div.textContent = `[${now}] ${msg}`;
    logBox.appendChild(div);
    logBox.scrollTop = logBox.scrollHeight;
  }

  function formatTime(seconds) {
    const s = Math.max(0, Number(seconds) || 0);
    const mins = Math.floor(s / 60);
    const secs = (s % 60).toFixed(1);
    return `${String(mins).padStart(2, '0')}:${secs.padStart(4, '0')}`;
  }

  root.Banano2Live = root.Banano2Live || {};
  root.Banano2Live.showNotification = showNotification;
  root.Banano2Live.appendLog = appendLog;
  root.Banano2Live.formatTime = formatTime;
})(typeof window !== 'undefined' ? window : globalThis);
