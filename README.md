# pages-to-audio

Backend server for the Pages to Audio exam processing system.

## Purpose

Receives exam page captures from an ESP32-S3-CAM device (via Android gateway), processes them
through OCR and AI to reconstruct exam questions, then delivers audio answers via MP3 and,
for firmware V2.2, a persistent A-E RGB answer sequence for the WS2812 LED.

## Requirements

- Python 3.12+
- Docker
- uv (Python package manager)

## Setup

```bash
# Install dependencies
make install

# Configure environment
cp .env.example .env
# Edit .env with your values

# Apply database migrations
make migrate

# Start the API server
make dev

# Or start Postgres, Temporal, API, worker and migrations with Docker Compose
make stack-up
```

## Commands

```bash
make install        # Install dependencies
make dev            # Start API in dev mode
make test           # Run all tests
make test-unit      # Unit tests only
make lint           # Lint + format check
make typecheck      # mypy strict check
make migrate        # Apply pending migrations
make migration name="..." # Create new migration
make stack-up       # Start the complete local stack with Docker Compose
make stack-down     # Stop the complete local stack
```

## Architecture

See [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) — this is the architectural source of truth.
See [CODEX_EXECUTION_PLAN.md](CODEX_EXECUTION_PLAN.md) — operational execution plan.

## Security

- Never commit `.env` or real credentials
- All secrets via environment variables
- See `docs/security.md` for full security policy

RGB result contract: [docs/contracts/RGB_RESULT_V1.md](docs/contracts/RGB_RESULT_V1.md).

For a reproducible local setup, see [docs/runbooks/local_stack.md](docs/runbooks/local_stack.md).
