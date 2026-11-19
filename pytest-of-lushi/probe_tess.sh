#!/bin/sh
# Состояние процесса tesseract: state, cpu, wchan, стек ожидания.
for p in /proc/[0-9]*; do
  cmd=$(tr '\0' ' ' < "$p/cmdline" 2>/dev/null)
  case "$cmd" in
    *tesseract*)
      pid=$(basename "$p")
      echo "pid $pid: $cmd"
      awk '{print "state="$3, "utime="$14, "stime="$15}' "$p/stat"
      echo "wchan=$(cat "$p/wchan" 2>/dev/null)"
      ;;
  esac
done
