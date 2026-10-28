# Stored-scan replay

Every change to the server ranking (number rules, guards, the choose list) is
replayed on all stored staging scans before it is merged: same scans, the
switch off and then on, and every scan whose answer changes is checked by hand.

1. Export (read-only on staging; the script is streamed, nothing is written):
   `ssh auctaro-staging "docker exec -i scanapp-scanapp-z1mwj4-api-1 python3 -" < api/scripts/stored_scan_replay/export_cases.py > <work>/cases.jsonl`
   The file holds OCR text: keep `<work>` outside Git and delete it afterwards.
2. For number rules that need set totals, use the catalogue and totals files of
   the last phone-index export (`api/scripts/on_phone_index/README.md`).
3. Replay from the branch with the change:
   `cd api && .venv/bin/python scripts/stored_scan_replay/replay_ranking.py <work>/cases.jsonl --flag <setting> [--catalog ... --totals ...]`
4. Gate: each listed scan moves to the right card or to a fair choose list,
   0 moves to a wrong card. Put the counts in the PR.

The replay reranks the stored visual top 20 and OCR read; it does not re-run
OCR or the picture search, so it covers ranking and choose-list changes only.
