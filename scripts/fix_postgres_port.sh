#!/bin/bash
# Fix: port 5432 already in use

PORT=5432

echo "=== Checking what is using port $PORT ==="

# Find the process using the port
PID=$(sudo lsof -ti tcp:$PORT 2>/dev/null || ss -tlnp | grep ":$PORT" | awk '{print $7}' | grep -oP 'pid=\K[0-9]+')

if [ -z "$PID" ]; then
    # Try netstat fallback
    PID=$(netstat -tlnp 2>/dev/null | grep ":$PORT " | awk '{print $7}' | cut -d/ -f1)
fi

if [ -n "$PID" ]; then
    PROCESS=$(ps -p "$PID" -o comm= 2>/dev/null)
    echo "Port $PORT is used by PID $PID ($PROCESS)"

    read -rp "Kill this process? [y/N] " CONFIRM
    if [[ "$CONFIRM" =~ ^[Yy]$ ]]; then
        sudo kill -9 "$PID"
        echo "Killed PID $PID"
    else
        echo "Skipping kill. You can change the port in docker-compose.yml instead (e.g. '5433:5432')."
        exit 1
    fi
else
    echo "No process found on port $PORT — may already be free."
fi

echo ""
echo "=== Restarting Docker postgres service ==="
docker compose up -d postgres

echo ""
echo "=== Waiting for postgres to be healthy ==="
for i in $(seq 1 20); do
    STATUS=$(docker compose ps postgres --format json 2>/dev/null | grep -o '"Health":"[^"]*"' | cut -d'"' -f4)
    echo "  [$i/20] Status: ${STATUS:-unknown}"
    if [ "$STATUS" = "healthy" ]; then
        echo "Postgres is up and healthy on port $PORT."
        exit 0
    fi
    sleep 3
done

echo "Postgres did not become healthy in time. Check logs:"
echo "  docker compose logs postgres"
exit 1
