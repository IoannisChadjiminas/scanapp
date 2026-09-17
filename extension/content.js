import { waitForPage } from "./lib/extract.js";

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type !== "extract") {
    return undefined;
  }
  waitForPage(document, window.location.href, document.title).then((result) => {
    const payload = {
      type: "extract-result",
      requestId: message.requestId,
      jobId: message.jobId,
      ...result,
      url: window.location.href,
    };
    sendResponse(payload);
  });
  return true;
});
