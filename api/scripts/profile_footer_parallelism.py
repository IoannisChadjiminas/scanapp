"""Paired same-pixel OCR benchmark. No catalogue, matching or grading mutation."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
import json
from pathlib import Path
import statistics
import sys
import time

from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.recognition.artifacts import sha256_file
from app.recognition.auxiliary_work import AuxiliaryWorkGate
from app.recognition.ocr import CardOcr


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--audit-dir', type=Path, required=True)
    p.add_argument('--models', type=Path, default=Path('/data/models'))
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--per-kind', type=int, default=10)
    p.add_argument('--reader-source', type=Path,
        help='Load an isolated candidate OCR module without modifying the deployed application')
    args = p.parse_args()
    reader_class = CardOcr
    if args.reader_source:
        import importlib.util
        spec = importlib.util.spec_from_file_location('candidate_ocr_benchmark', args.reader_source)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        reader_class = module.CardOcr
    cases = json.loads((args.audit_dir/'cases.json').read_text())
    counts = Counter(); selected = []
    for case in cases:
        if counts[case['kind']] < args.per_kind:
            selected.append(case); counts[case['kind']] += 1
    for case in selected:
        assert sha256_file(args.audit_dir/case['photo_file']) == case['sha256']
    from rapidocr.utils.vis_res import VisRes
    VisRes.get_font_path = lambda self,*a,**k:'unused-benchmark-font'
    options = dict(det_path=str(args.models/'PP-OCRv6_det_small.onnx'),
        rec_path=str(args.models/'PP-OCRv6_rec_small.onnx'),
        cls_path=str(args.models/'ch_ppocr_mobile_v2.0_cls_mobile.onnx'),
        intra_threads=1, inter_threads=1)
    reader, auxiliary = reader_class(**options), reader_class(**options)
    auxiliary.share_inference_sessions_from(reader)
    reader.auxiliary_gate = AuxiliaryWorkGate()
    records = []
    with ThreadPoolExecutor(max_workers=1) as executor, args.output.open('x') as handle:
        reader.region_executor = executor
        for index, case in enumerate(selected):
            with Image.open(args.audit_dir/case['photo_file']) as source:
                image = source.convert('RGB')
            results = {}
            for parallel in ([False, True] if index % 2 == 0 else [True, False]):
                reader.region_reader = auxiliary
                reader.parallel_footer_halves = parallel
                started = time.perf_counter()
                observed = reader.read(image)
                results[parallel] = (observed, (time.perf_counter()-started)*1000)
                assert not reader.auxiliary_gate.active
            before, before_ms = results[False]; after, after_ms = results[True]
            fields = ('name_text','collector_text','lines','hits','failed',
                'collector_retry_used','collector_retry_contributed','collector_retry_skipped')
            differences = [field for field in fields if getattr(before,field) != getattr(after,field)]
            record = dict(case=case, serial_ms=before_ms, parallel_ms=after_ms,
                differences=differences, before=asdict(before), after=asdict(after))
            records.append(record);handle.write(json.dumps(record)+'\n');handle.flush()
            print(json.dumps(dict(id=case['id'],number=len(records),total=len(selected),
                serial_ms=round(before_ms),parallel_ms=round(after_ms),differences=differences)),flush=True)
    summary = dict(photos=len(records), counts=dict(counts),
        exact_evidence_equal=sum(not r['differences'] for r in records),
        differences=[dict(id=r['case']['id'],fields=r['differences']) for r in records if r['differences']],
        serial_median_ms=statistics.median(r['serial_ms'] for r in records),
        parallel_median_ms=statistics.median(r['parallel_ms'] for r in records),
        median_saved_ms=statistics.median(r['serial_ms']-r['parallel_ms'] for r in records),
        model_hashes={path.name:sha256_file(path) for path in args.models.glob('*onnx')},
        limitations='Uncontended OCR component benchmark, not end-to-end matching, grading or staging latency. '
            'Initial title/footer OCR is parallel in both configurations; only enlarged footer scheduling changes.')
    args.output.with_suffix('.summary.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary),flush=True)
    assert not summary['differences'], 'OCR evidence changed'


if __name__ == '__main__':
    main()
