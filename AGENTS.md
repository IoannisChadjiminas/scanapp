<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->

# Card image URLs

The catalogue API owns `image_url`. Mirrored TCGdex art is served from the public R2 bucket behind `CARD_IMAGE_CDN_BASE_URL`; the mirror job and registry are in `api/app/card_image_mirror.py` and `api/scripts/mirror_card_images.py`. Read `docs/card-image-cdn.md` before changing image delivery. Never mirror Cardmarket product photos or local-only reference images, and keep the TCGdex path layout so clients can swap `high.webp` for `low.webp`.
