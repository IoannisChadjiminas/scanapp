import logging

from app.client_diagnostics import phone_diagnostic_lines


def test_phone_events_keep_timings_and_drop_private_fields(caplog):
    lines = phone_diagnostic_lines(
        {
            "events": [
                {
                    "time": "2026-10-06T09:12:38Z",
                    "event": "scan.result",
                    "scan": "1791277942882276-2",
                    "status": "printingAmbiguous",
                    "server_scan": "8e0c8602-d522-4899-a451-355b98d95fe7",
                    "cardmarket_url": "https://www.cardmarket.com/secret",
                    "ocr": "Gardevoir",
                    "server_timings": {"ocr_ms": 1922.94, "note": "drop me"},
                },
                {"event": "bad event"},
                "not-an-event",
            ]
        }
    )
    assert lines == [
        "phone event=scan.result scan=1791277942882276-2 status=printingAmbiguous "
        "server_scan=8e0c8602-d522-4899-a451-355b98d95fe7 server_timings=ocr_ms:1922.94"
    ]
    assert "cardmarket.com" not in lines[0]
    assert "Gardevoir" not in lines[0]
    with caplog.at_level(logging.INFO, logger="scan.diagnostics"):
        logging.getLogger("scan.diagnostics").info("%s", lines[0])
    assert "event=scan.result" in caplog.text


def test_phone_events_reject_a_huge_batch():
    try:
        phone_diagnostic_lines({"events": [{"event": "camera.opened"}] * 41})
    except ValueError as exc:
        assert "short list" in str(exc)
    else:
        raise AssertionError("expected a short-list rejection")
