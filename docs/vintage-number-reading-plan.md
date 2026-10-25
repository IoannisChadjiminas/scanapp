# Plan: read collector numbers on vintage (WOTC-era) cards on the phone

**Repo:** PokeSingle (`~/StudioProjects/PokeSingle`). Start a new branch from latest `origin/main`.
**Rules:**
- **No server changes.**
- **Stay inside the existing text deadline** (250 ms iOS / 300 ms Android).
- **`flutter analyze` and `flutter test` must pass**, and the iOS and Android release builds must succeed.
- **Bump the build number** (the phone reports `1.0.0+150` although it runs newer code), so staging logs show which build sent each scan.
- **Open a PR, don't merge it,** and don't publish to any store.

## Why

Real iPhone scans on staging (2026-10-22, 26 scans of vintage cards: Base Set `base1`, Jungle `base2`, Fossil `base3`, Base Set 2 `base4`, Team Rocket `base5`):
- **Stage 1 / 1b answered 6 of 26, and all 6 agreed with the full pipeline:** 3 at stage 1 in 18–27 ms, 3 at stage 1b in 264–285 ms.
- **Most of the other 20 abstained with `no_unique_text`**, where the phone read the **name** (`name_agree=true`) but **no collector number**.
- **4 text reads were late** (`client_text.late`).

Answered scans drop from 3–9 s to 0.02–0.3 s, so every extra number read is a fast answer.

**The layout difference:** round 3's footer reading (PokeSingle #153: footer strip at 2×, then corners, then a contrast retry) was tuned on modern cards, where the number sits **bottom left**. On WOTC-era cards (1999–2003: Base, Jungle, Fossil, Base Set 2, Team Rocket, Gym, Neo, Legendary Collection, e-Card), the number is:
- **at the bottom right**, very small: `57/64`, `4/102`, `16/110`
- **often next to a rarity symbol** (●, ◆, ★) on the same line
- **on Base Set, with no set symbol**, which makes the corner look empty to a generic text crop
- **on e-Card sets, in an `H`-prefixed or a `/165`-style format**, and **`#` plus a number for promos** (e.g. Wizards Black Star `#16`)

## Changes

1. **Detect the era from the read text.** These signs mean "vintage layout":
   - a copyright line with `1995, 96, 98, 99` / `Nintendo` / `Wizards` / `©1999-2000`
   - illustrator text `Illus.` at the bottom left
   - an HP format like `60 HP` (number before "HP")
   - "Weakness / Resistance / Retreat Cost" as words

   When it's vintage, read the **bottom-right corner first**. Otherwise keep round 3's order.
2. **A vintage bottom-right crop:** the bottom **10%** of the straightened card × the right **35%**, at **3×**, read by Vision `.accurate` (ML Kit on Android) with a low `minimumTextHeight`. If nothing is found, widen to the right 50% / bottom 13% once.
3. **Number parsing:**
   - **Strip a trailing rarity glyph**, so `57/64●`, `57/64 *` and `57/64 o` read as `57/64`.
   - **Accept `N/T` with T in {102, 64, 62, 82, 130, 110, 105, 111, 75, 95, 64, 132, 165, 144, 147, 182…}**, i.e. check it against the bundled set-total table from #153.
   - **Fix common vintage misreads** inside the number pattern only: `l`/`I` → `1`, `O` → `0`, `S` → `5`, `B` → `8`, and a missing slash (`5764` → `57/64` when a valid total fits).
4. **Contrast retry for holo and worn cards:** if the vintage crop returns no valid number, retry once with a levels stretch plus a mild sharpen. Old holos and yellowed borders hide the digits.
5. **Time budget:** the extra crop must fit the deadline. Run it **in parallel** with the existing full-card read where possible, and cancel it if the full-card read already found a valid number. Measure median and p90 on the iPhone and report them. Also look at why `client_text.late` happened on 4 of 26 scans, and reduce it.

## Test data

- **Unit tests** for the parser: `57/64●`, `4/102 ★`, `16/110`, `5764` → `57/64`, `l6/l02` → `16/102`, the `H`-prefix e-Card numbers, and `#16` promos.
- **Fixtures from vintage photos.** Staging didn't keep these photos (`STORE_CAPTURES` is off). Use the frozen panel's vintage cards (e.g. `en:base1-15`, `en:base5-68`, `en:base1-9`, `en:base1-6` in ScanApp's `docs/experiments/stage0-simulation-20261021.md` lists), or ask the owner to turn on `STORE_CAPTURES` on staging for one test session and rescan about 20 vintage cards. Never put user photos in git; keep the fixtures local, as before.
- **Before / after on the same vintage photos:** the number-read rate (today about 6 of 26 on staging) and the median and p90 text time.

## Done when

- The PR is open, with:
  - the vintage number-read rate before vs after
  - phone timing
  - tests passing
  - release builds passing
  - the new build number
- **On staging, after installing the new TestFlight build:** rescan the same 26 vintage cards. **Expected:** most of the `no_unique_text` scans become stage 1b answers, and `stage1_check` keeps **0 disagreements**.
