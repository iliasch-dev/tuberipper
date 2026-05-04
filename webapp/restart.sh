#!/usr/bin/env bash
set -e

COMPOSE_FILE="$(dirname "$0")/../docker-compose.yml"

docker compose -f "$COMPOSE_FILE" up -d --build webapp
