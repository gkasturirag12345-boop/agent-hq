# Security policy

Agent HQ is a local, read-only viewer. It is designed for one person on their own machine:

- It listens on `127.0.0.1` only and has **no authentication**. Do not expose it through a reverse proxy, tunnel or port forward.
- It never writes files, starts processes or makes network calls.
- It reads Markdown records in the workspace you point it at, plus Claude Code transcript **metadata** for that workspace (file times, tool names, sub-agent type and finished flag). Message content is never kept or returned.

## Reporting a vulnerability
Please open a [private security advisory](https://github.com/gkasturirag12345-boop/agent-hq/security/advisories/new) rather than a public issue. Include the steps to reproduce it and the impact.
