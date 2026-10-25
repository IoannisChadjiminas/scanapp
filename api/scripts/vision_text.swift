// Apple Vision text recognition for card crops: a stand-in for the phone's on-device OCR.
//
// Build: swiftc -O api/scripts/vision_text.swift -o vision_text
// Use:   printf '%s\n' crop1.jpg crop2.jpg | ./vision_text [--fast] [--min-height 0.015]
//
// One JSON object per input line: the image size, the time Vision took, and each
// recognised line with its confidence and box (0...1, measured from the top-left).
// Used by simulate_client_text.py; the iPhone app would run the same request.
import Foundation
import Vision
import ImageIO

var fast = false
var minHeight = Float(-1)
var args = CommandLine.arguments.dropFirst().makeIterator()
while let arg = args.next() {
  if arg == "--fast" {
    fast = true
  } else if arg == "--min-height", let raw = args.next(), let value = Float(raw), value > 0, value < 1 {
    // Footer crops need a lower floor than the 1/32 default. The full-card read leaves this unset.
    minHeight = value
  }
}

func emit(_ object: [String: Any]) {
  let data = try! JSONSerialization.data(withJSONObject: object, options: [.sortedKeys])
  FileHandle.standardOutput.write(data)
  FileHandle.standardOutput.write("\n".data(using: .utf8)!)
}

while let path = readLine() {
  if path.isEmpty { continue }
  guard let source = CGImageSourceCreateWithURL(URL(fileURLWithPath: path) as CFURL, nil),
    let image = CGImageSourceCreateImageAtIndex(source, 0, nil)
  else {
    emit(["path": path, "error": "unreadable"])
    continue
  }
  let request = VNRecognizeTextRequest()
  request.recognitionLevel = fast ? .fast : .accurate
  request.usesLanguageCorrection = false
  request.recognitionLanguages = ["en-US", "ja-JP"]
  if minHeight > 0 {
    request.minimumTextHeight = minHeight
  }
  let handler = VNImageRequestHandler(cgImage: image, options: [:])
  let started = DispatchTime.now()
  var lines: [[String: Any]] = []
  var failure: String? = nil
  do {
    try handler.perform([request])
    for observation in request.results ?? [] {
      guard let best = observation.topCandidates(1).first else { continue }
      let box = observation.boundingBox  // normalised, origin bottom-left
      lines.append([
        "text": best.string, "conf": Double(best.confidence),
        "x": Double(box.minX), "y": Double(1 - box.maxY),
        "w": Double(box.width), "h": Double(box.height),
      ])
    }
  } catch {
    failure = String(describing: error)
  }
  let ms = Double(DispatchTime.now().uptimeNanoseconds - started.uptimeNanoseconds) / 1e6
  var row: [String: Any] = [
    "path": path, "ms": ms, "width": image.width, "height": image.height, "lines": lines,
    "level": fast ? "fast" : "accurate",
  ]
  if let failure { row["error"] = failure }
  emit(row)
}
