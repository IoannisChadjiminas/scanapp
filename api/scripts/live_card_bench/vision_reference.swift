// Dumps every card-shaped rectangle the iOS gallery detector (CardWarp.quads
// with quadsInImage, maxEdge 1024) finds, running Vision on macOS.
// usage: swiftc -O vision_reference.swift -o vision_reference
//        ./vision_reference <photo dir> > candidates.json
// Output: {"<file>": [[conf, x1,y1,x2,y2,x3,y3,x4,y4], ...]}, corners 0..1 from top-left.
import Foundation
import Vision
import ImageIO

func candidates(_ url: URL) -> [[Double]] {
  guard let source = CGImageSourceCreateWithURL(url as CFURL, nil) else { return [] }
  let options: [CFString: Any] = [
    kCGImageSourceCreateThumbnailFromImageAlways: true,
    kCGImageSourceCreateThumbnailWithTransform: true,
    kCGImageSourceThumbnailMaxPixelSize: 1024,
  ]
  guard let image = CGImageSourceCreateThumbnailAtIndex(source, 0, options as CFDictionary)
  else { return [] }
  let request = VNDetectRectanglesRequest()
  request.minimumAspectRatio = 0.55
  request.maximumAspectRatio = 0.82
  request.minimumConfidence = 0.6
  request.minimumSize = 0.2
  request.quadratureTolerance = 30
  request.maximumObservations = 6
  let segmentation = VNDetectDocumentSegmentationRequest()
  let handler = VNImageRequestHandler(cgImage: image, options: [:])
  do { try handler.perform([request, segmentation]) } catch { return [] }
  var found: [VNRectangleObservation] = request.results ?? []
  let size = CGSize(width: image.width, height: image.height)
  if let page = segmentation.results?.first, page.confidence >= 0.6 {
    func d(_ a: CGPoint, _ b: CGPoint) -> Double {
      hypot(Double(a.x - b.x) * size.width, Double(a.y - b.y) * size.height)
    }
    let wide = (d(page.topRight, page.topLeft) + d(page.bottomRight, page.bottomLeft)) / 2
    let tall = (d(page.topLeft, page.bottomLeft) + d(page.topRight, page.bottomRight)) / 2
    let ratio = min(wide, tall) / max(max(wide, tall), 1)
    if ratio >= 0.55, ratio <= 0.82 { found.append(page) }
  }
  return found.map { c in
    [Double(c.confidence)]
      + [c.topLeft, c.topRight, c.bottomRight, c.bottomLeft].flatMap { [Double($0.x), 1 - Double($0.y)] }
  }
}

let dir = URL(fileURLWithPath: CommandLine.arguments[1])
let files = try FileManager.default.contentsOfDirectory(atPath: dir.path).filter { $0.hasSuffix(".jpg") }.sorted()
var out: [String: [[Double]]] = [:]
for f in files { out[f] = candidates(dir.appendingPathComponent(f)) }
let data = try JSONSerialization.data(withJSONObject: out, options: [.sortedKeys])
FileHandle.standardOutput.write(data)
