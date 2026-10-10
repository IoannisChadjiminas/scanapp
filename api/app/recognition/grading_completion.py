"""Finish an admitted label read without delaying or changing the card result."""
import asyncio
import json
import logging

from app.schemas import GradingEvidence

_updates = set()


def persist_grading(results, scan_id, grading, elapsed_ms):
    # One JSON field update: never overwrite ranking, feedback, price or URL.
    results.execute(
        """UPDATE scans SET ocr_json=json_set(ocr_json,'$.grading',json(?)),
           timings_json=json_set(timings_json,'$.grading_completion_ms',?)
           WHERE id=? AND json_extract(ocr_json,'$.grading.grading_status')='pending'""",
        (json.dumps(grading.model_dump(mode='json')), elapsed_ms, scan_id),
    )
    results.commit()


def schedule_grading_completion(loop, results, scan_id, job):
    async def complete():
        try:
            observed = await asyncio.wait_for(
                asyncio.shield(asyncio.wrap_future(job.future)), timeout=30)
            grading = (observed if observed.company is not None else
                       GradingEvidence(is_graded=False, grading_status='ungraded'))
        except Exception:
            job.stop()
            grading = GradingEvidence(warnings=['grading_completion_unavailable'])
        try:
            persist_grading(results, scan_id, grading, job.elapsed_ms)
        except Exception:
            logging.getLogger(__name__).exception('Could not save grading for %s', scan_id)

    def start():
        task = loop.create_task(complete())
        _updates.add(task)
        task.add_done_callback(_updates.discard)

    loop.call_soon_threadsafe(start)


async def drain_grading_updates():
    if _updates:
        await asyncio.gather(*tuple(_updates), return_exceptions=True)
