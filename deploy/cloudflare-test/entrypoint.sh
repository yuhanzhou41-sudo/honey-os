#!/bin/sh
set -eu

mkdir -p /data

restore_state() {
  curl -fsS --max-time 20 http://honeyos-state.r2/manifest -o /tmp/honeyos-state.manifest || return 1
  CHUNK_COUNT=$(cat /tmp/honeyos-state.manifest)
  case "$CHUNK_COUNT" in
    ''|*[!0-9]*) return 1 ;;
  esac
  : > /tmp/honeyos-state.tar.gz
  index=0
  while [ "$index" -lt "$CHUNK_COUNT" ]; do
    suffix=$(printf '%04d' "$index")
    curl -fsS --max-time 20 \
      "http://honeyos-state.r2/chunks/$suffix" \
      -o "/tmp/honeyos-state.chunk.$suffix" || return 1
    cat "/tmp/honeyos-state.chunk.$suffix" >> /tmp/honeyos-state.tar.gz
    index=$((index + 1))
  done
  tar -xzf /tmp/honeyos-state.tar.gz -C /data
}

if ! restore_state; then
  cp -R /seed-home/. /data/
fi
rm -f /tmp/honeyos-state.tar.gz /tmp/honeyos-state.manifest /tmp/honeyos-state.chunk.*

backup_state() {
  set --
  for path in \
    SOUL.md channel_directory.json config.yaml continuity.db story_runtime.db \
    state.db response_store.db kanban.db memories sessions cron kanban hooks \
    pairing pending_messages platforms skills; do
    if [ -e "/data/$path" ]; then
      set -- "$@" "$path"
    fi
  done
  [ "$#" -gt 0 ] || return 0
  tar -czf /tmp/honeyos-state.tar.gz -C /data "$@" 2>/dev/null || return 0
  rm -f /tmp/honeyos-state.chunk.*
  split -b 131072 -d -a 4 /tmp/honeyos-state.tar.gz /tmp/honeyos-state.chunk.
  CHUNK_COUNT=0
  for chunk in /tmp/honeyos-state.chunk.*; do
    suffix=${chunk##*.}
    curl -fsS --max-time 30 -X PUT \
      -H 'content-type: application/octet-stream' \
      -H 'Expect:' \
      --data-binary "@$chunk" \
      "http://honeyos-state.r2/chunks/$suffix" >/dev/null || return 0
    CHUNK_COUNT=$((CHUNK_COUNT + 1))
  done
  printf '%s' "$CHUNK_COUNT" > /tmp/honeyos-state.manifest
  curl -fsS --max-time 30 -X PUT \
    -H 'content-type: text/plain' \
    -H 'Expect:' \
    --data-binary @/tmp/honeyos-state.manifest \
    http://honeyos-state.r2/manifest >/dev/null || true
  rm -f /tmp/honeyos-state.tar.gz /tmp/honeyos-state.manifest /tmp/honeyos-state.chunk.*
}

shutdown() {
  if [ -n "${HONEYOS_PID:-}" ]; then
    kill -TERM "$HONEYOS_PID" 2>/dev/null || true
    wait "$HONEYOS_PID" 2>/dev/null || true
  fi
  backup_state
  exit 0
}

trap shutdown TERM INT

python -m honeyos.runtime.main gateway run --replace &
HONEYOS_PID=$!

(
  while kill -0 "$HONEYOS_PID" 2>/dev/null; do
    sleep 30
    backup_state
  done
) &

STATUS=0
wait "$HONEYOS_PID" || STATUS=$?
backup_state
exit "$STATUS"
