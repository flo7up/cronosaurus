# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in Cronosaurus, please report it
responsibly. **Do not open a public GitHub issue.**

Instead, email **[security@cronosaurus.dev](mailto:security@cronosaurus.dev)**
with:

- A description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

We will acknowledge your report within **48 hours** and aim to release a fix
within **7 days** for critical issues.

## Supported Versions

| Version | Supported |
| ------- | --------- |
| main    | ✅        |

## Scope

The following are in scope:

- Backend API (FastAPI)
- Frontend (React/Vite)
- Docker configuration
- Dependencies listed in `requirements.txt` and `package.json`

The following are **out of scope**:

- Azure Cosmos DB service itself
- Azure AI Foundry service itself
- Third-party MCP servers connected by the user
