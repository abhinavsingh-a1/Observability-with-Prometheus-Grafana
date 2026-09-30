#!/usr/bin/env bash
# Project 11 - Disk fill. LINUX ONLY (needs sudo). Creates a 300 MB loopback
# filesystem at /mnt/lab-disk and fills it slowly - your real disks are untouched.
# Usage: ./trigger.sh fill|fast-fill|io|reset
set -euo pipefail
IMG=/tmp/lab-disk.img; MNT=/mnt/lab-disk
setup() {
  if ! mountpoint -q "$MNT"; then
    sudo truncate -s 300M "$IMG"
    sudo mkfs.ext4 -q -F "$IMG"
    sudo mkdir -p "$MNT" && sudo mount -o loop "$IMG" "$MNT"
    sudo chmod 777 "$MNT"
    echo "mounted $MNT (300 MB). node_exporter sees it within ~15s."
  fi
}
fill() {  # $1 = MB per step, $2 = seconds between steps
  echo "writing $1 MB every $2 s until 95% full (Ctrl+C to stop)"
  i=0
  while [ "$(df --output=pcent "$MNT" | tail -1 | tr -dc 0-9)" -lt 95 ]; do
    dd if=/dev/zero of="$MNT/file-$i" bs=1M count="$1" status=none; i=$((i+1))
    df -h "$MNT" | tail -1; sleep "$2"
  done
}
case "${1:-help}" in
  fill)      setup; fill 3 20 ;;   # ~9 MB/min -> prediction alert first, then DiskSpaceLow
  fast-fill) setup; fill 10 5 ;;
  io)        docker rm -f lab-io-stress >/dev/null 2>&1 || true
             docker run -d --rm --name lab-io-stress alpine:3.20 sh -c \
               "apk add -q --no-cache stress-ng >/dev/null && stress-ng --hdd 2 --hdd-bytes 512M --timeout 300s" >/dev/null
             echo "disk I/O stress for 5 min -> utilization / iowait / latency panels (and project 10 iowait)" ;;
  reset)     docker rm -f lab-io-stress >/dev/null 2>&1 || true
             if mountpoint -q "$MNT"; then sudo umount "$MNT"; fi
             sudo rm -f "$IMG"; echo "cleaned up" ;;
  *)         echo "usage: $0 fill|fast-fill|io|reset"; exit 1 ;;
esac
