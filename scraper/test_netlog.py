import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from netlog import summarize_net_log

TYPES = {
    "HTTP_TRANSACTION_SEND_TUNNEL_HEADERS": 10,
    "HTTP_TRANSACTION_READ_TUNNEL_RESPONSE_HEADERS": 11,
    "URL_REQUEST_START_JOB": 12,
    "HTTP_TRANSACTION_READ_RESPONSE_HEADERS": 13,
    "REQUEST_ALIVE": 14,
}
CONSTANTS = {"logEventTypes": TYPES, "netError": {"ERR_TIMED_OUT": -7, "ERR_ABORTED": -3}}


def _event(name, source, params):
    return {"type": TYPES[name], "source": {"id": source, "type": 1}, "phase": 0, "params": params}


def _file(events, cut=False):
    lines = [json.dumps(event) for event in events]
    text = '{"constants":' + json.dumps(CONSTANTS) + ',\n"events": [\n' + ",\n".join(lines)
    return text + ",\n" if cut else text + '],\n"polledData": []\n}\n'


def test_reports_tunnel_replies_responses_and_errors_for_watched_hosts():
    events = [
        _event("HTTP_TRANSACTION_SEND_TUNNEL_HEADERS", 1, {"headers": [
            "Host: www.cardmarket.com:443", "Proxy-Authorization: [redacted]",
        ]}),
        _event("HTTP_TRANSACTION_READ_TUNNEL_RESPONSE_HEADERS", 1, {"headers": [
            "HTTP/1.1 407 Proxy Authentication Required",
        ]}),
        _event("HTTP_TRANSACTION_SEND_TUNNEL_HEADERS", 2, {"headers": ["Host: www.cardmarket.com:443"]}),
        _event("HTTP_TRANSACTION_READ_TUNNEL_RESPONSE_HEADERS", 2, {"headers": ["HTTP/1.1 200 Connection established"]}),
        _event("HTTP_TRANSACTION_SEND_TUNNEL_HEADERS", 3, {"headers": ["Host: challenges.cloudflare.com:443"]}),
        _event("HTTP_TRANSACTION_SEND_TUNNEL_HEADERS", 4, {"headers": ["Host: www.google.com:443"]}),
        _event("HTTP_TRANSACTION_READ_TUNNEL_RESPONSE_HEADERS", 4, {"headers": ["HTTP/1.1 200 Connection established"]}),
        _event("URL_REQUEST_START_JOB", 9, {"url": "https://www.cardmarket.com/en/Pokemon/Products/Singles/a/b"}),
        _event("HTTP_TRANSACTION_READ_RESPONSE_HEADERS", 9, {"headers": ["HTTP/1.1 403", "set-cookie: [redacted]"]}),
        _event("REQUEST_ALIVE", 9, {"net_error": -7}),
    ]
    summary = summarize_net_log(_file(events))
    assert summary == {
        "challenges.cloudflare.com": {"tunnel": {"no reply": 1}},
        "www.cardmarket.com": {
            "tunnel": {"407 Proxy Authentication Required": 1, "200 Connection established": 1},
            "response": {"403": 1},
            "error": {"ERR_TIMED_OUT": 1},
        },
    }
    assert "redacted" not in json.dumps(summary)


def test_a_file_cut_off_by_a_killed_browser_still_reads():
    events = [
        _event("HTTP_TRANSACTION_SEND_TUNNEL_HEADERS", 1, {"headers": ["Host: www.cardmarket.com:443"]}),
        _event("URL_REQUEST_START_JOB", 2, {"url": "https://www.cardmarket.com/en"}),
    ]
    text = _file(events, cut=True) + '{"type": 10, "source": {"id"'
    assert summarize_net_log(text) == {"www.cardmarket.com": {"tunnel": {"no reply": 1}}}


def test_an_empty_or_unfinished_header_returns_nothing():
    assert summarize_net_log("") == {}
    assert summarize_net_log('{"constants":{"logEventTypes"') == {}
