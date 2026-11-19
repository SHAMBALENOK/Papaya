#!/bin/sh
# Снимок состояния процесса pytest: потоки, CPU, ожидание, дети.
PID=20
for t in /proc/$PID/task/*; do
  tid=$(basename "$t")
  echo "thread $tid stat=$(cut -d' ' -f14,15 "$t/stat") wchan=$(cat "$t/wchan" 2>/dev/null)"
done
echo "--- children of pytest"
for p in /proc/[0-9]*; do
  pid=$(basename "$p")
  ppid=$(awk '{print $4}' "$p/stat" 2>/dev/null)
  if [ "$ppid" = "$PID" ]; then
    echo "child $pid: $(tr '\0' ' ' < "$p/cmdline")"
  fi
done
echo "--- tesseract-like"
for p in /proc/[0-9]*; do
  cmd=$(tr '\0' ' ' < "$p/cmdline" 2>/dev/null)
  case "$cmd" in
    *tesseract*) echo "$(basename "$p"): $cmd" ;;
  esac
done
