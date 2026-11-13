# How Agent HQ was tested

## Automated (run them yourself)
`python3 -B -m unittest discover tests` runs 37 tests covering:
- **Parsing:** task-board tables with `file:line` sources; handoff front matter; checker results matching the command-line checker; whole-name owner matching; status arrows matched to the handoff's own task.
- **Inconsistencies:** reported and never corrected: board/handoff mismatch, missing linked handoffs, unknown statuses, incomplete handoffs, files that aren't UTF-8, agents without a name.
- **Live metadata:**
  - states from file times; `finished` handling;
  - incremental reads; over-long lines skipped, including across two scans; in-place and same-size rewrites;
  - malformed or oversized meta files; deeply nested JSON;
  - the 24 h window; symlinks skipped;
  - only the workspace's own transcript folder is scanned;
  - a secret string placed in fixture transcripts never appears in the output, and neither does the home path or username.
- **Server:** 200/404 routes; 405 for POST, PUT, DELETE, PATCH, OPTIONS, TRACE and CONNECT; a 403 Host check; HEAD with no body; security headers; no CORS headers.

## Mutation checks
Six fixes were each removed in turn to confirm the tests catch the regression: long-line skipping, the same-size rewrite reset, the RecursionError guard, own-task-id arrow matching, the UnicodeDecodeError guard, and the generic source label. Every removal made a test fail.

## Manual and browser checks
- **HTTP probes against a running server:** path traversal (encoded and double-slash), an 8 KB path, CRLF injection, Host variants (no port, look-alike domains, missing Host), and 40 concurrent requests.
- **Script injection:** an XSS payload (`<img onerror>`, `<script>`) was placed in every Markdown field of a fake workspace, and the page was checked in Chrome. Nothing executed, and the payload showed as literal text.
- **Real mouse events through the Chrome DevTools Protocol:**
  - hover tooltips for desks, boards, trays and the door, and none on empty floor;
  - clicking a room opens its project page;
  - repeated refreshes leave a single canvas;
  - stopping the server shows the "live data unavailable" banner.
- **Live runs:** short, real, read-only Claude Code sub-agent runs appeared as active, then showed their last tool, then ended.

## Independent review
The code went through four rounds of review by a separate read-only reviewer agent. The checks covered:
- requirement compliance: read-only, loopback-only, standard library only, no hooks or settings changes, no transcript content, and no fabricated activity;
- security: traversal, DNS rebinding, XSS, symlinks, error leakage and denial of service;
- correctness.

The final verdict was PASS. These low-severity limits were accepted:
- the Markdown is re-parsed on every request, and there is no thread cap (loopback only);
- the in-memory cache is not pruned;
- if a handoff doesn't name its own task, the first status arrow in its text is used;
- meta files of past runs are re-read on every poll.
