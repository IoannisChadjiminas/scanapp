const timer = new Worker("poll-worker.js");
timer.onmessage = () => {
  chrome.runtime.sendMessage({ type: "poll" }).catch(() => undefined);
};

function connect() {
  const port = chrome.runtime.connect({ name: "keepalive" });
  port.onDisconnect.addListener(() => {
    setTimeout(connect, 250);
  });
}

connect();
