# 11 · Disk Space, Fill Prediction & I/O

> **Will a disk fill up, and is storage slowing everything down?**

| | |
|---|---|
| **Layer** | Infrastructure |
| **Method** | USE for storage, plus **predictive** alerting |
| **Data source** | node_exporter filesystem and diskstats collectors |
| **Files** | `alerts.yml` · `dashboard.json` · `trigger.sh` |
| **Time** | ~25 min (Linux host needed for the fill demo) |

## 1. Why this matters

"Disk full" is one of the most common causes of outages, and one of the most preventable. When a disk hits 100%:

- Databases stop accepting writes or crash, which can corrupt data.
- Logs stop, so you lose the evidence.
- Container runtimes fail to start containers, and Kubernetes evicts pods (`DiskPressure`).

Static thresholds ("alert at 90%") fail both ways. A 10 TB disk at 90% still has 1 TB free, while a disk filling at 5 GB/min goes from 80% to 100% before anyone reacts. The answer is `predict_linear`: **"at the current rate, when will it be full?"**

Two other classics:

- **Inode exhaustion:** "No space left on device" while `df -h` shows free space. Millions of tiny files (sessions, caches, mail queues) are the usual cause.
- **Read-only remount:** the kernel remounts a filesystem read-only after I/O errors. Everything that writes fails.

## 2. How it works

node_exporter reports every mounted filesystem with the labels `device`, `mountpoint`, and `fstype`. Virtual filesystems (`tmpfs`, `overlay`, `squashfs`...) are filtered out in every query. For I/O, it reports per-device counters from `/proc/diskstats`.

The lab creates a **300 MB loopback filesystem** (`/mnt/lab-disk`) and fills it, so your real disks are never touched. node_exporter is started with `/:/host:ro,rslave`; `rslave` is what lets it see mounts created *after* it started.

## 3. Key metrics

| Metric | Meaning |
|---|---|
| `node_filesystem_avail_bytes` | Free space for non-root users (use this, not `free_bytes`) |
| `node_filesystem_size_bytes` | Size |
| `node_filesystem_files`, `node_filesystem_files_free` | Inodes |
| `node_filesystem_readonly` | 1 = read-only |
| `node_disk_io_time_seconds_total` | Time the device was busy (utilization) |
| `node_disk_read_bytes_total`, `written_bytes_total` | Throughput |
| `node_disk_read_time_seconds_total` / `reads_completed_total` | Latency (and the same for writes) |

## 4. PromQL cookbook

```promql
# Used %, real filesystems only
1 - node_filesystem_avail_bytes{fstype!~"tmpfs|overlay|squashfs|nsfs|fuse.*|ramfs"}
  / node_filesystem_size_bytes

# Predicted free space in 4 hours based on the last 1 hour
predict_linear(node_filesystem_avail_bytes{fstype!~"tmpfs|overlay"}[1h], 4 * 3600)

# Hours until full (only for filling disks)
node_filesystem_avail_bytes / -deriv(node_filesystem_avail_bytes[1h]) / 3600 > 0

# Inodes used %
1 - node_filesystem_files_free / node_filesystem_files

# Disk busy % (utilization)
rate(node_disk_io_time_seconds_total[5m])

# Average read latency
rate(node_disk_read_time_seconds_total[5m]) / rate(node_disk_reads_completed_total[5m])
```

## 5. Alerts (`alerts.yml`)

| Alert | Condition | Severity |
|---|---|---|
| `HostDiskWillFillIn4Hours` | predict_linear(1h window, +4h) < 0 **and** > 60% used, for 5m | warning |
| `HostDiskSpaceLow` | < 10% free for 2m | critical |
| `HostInodesLow` | < 10% inodes free | critical |
| `HostFilesystemReadOnly` | readonly == 1 | critical |
| `HostDiskSaturated` | busy > 90% for 10m | warning |

The `> 60% used` guard in the prediction alert matters. Without it, any write burst to an empty disk "predicts" a full disk and pages people for nothing.

## 6. Dashboard

- **Bar gauges:** used % and inodes used % per mountpoint.
- **Graphs:** available bytes, 4h prediction (below zero = trouble), disk utilization, throughput, and read/write latency.

## 7. Hands-on lab (Linux)

```bash
./projects/11-disk-space-io/trigger.sh fill      # about 25 min to 95%, watch the prediction go negative early
./projects/11-disk-space-io/trigger.sh reset
./projects/11-disk-space-io/trigger.sh io        # I/O stress: utilization, latency, iowait (project 10)
./projects/11-disk-space-io/trigger.sh reset
```

What you'll see with `fill`: `HostDiskWillFillIn4Hours` fires **long before** `HostDiskSpaceLow`. That lead time is the whole point of predictive alerting.

**Mac/Windows:** loop mounts don't work with Docker Desktop. Use `io`, and study the fill behaviour by temporarily changing the threshold in `alerts.yml` to your current usage.

## 8. Runbook

**Disk will fill / space low**

1. Find the biggest consumers with `du -xh --max-depth=2 / | sort -h | tail -20`.
2. Check the usual suspects:

   | Suspect | Check with |
   |---|---|
   | Logs | `/var/log`, container logs: `docker system df` |
   | Old images | `docker image prune` |
   | DB WAL or binlogs | Database tooling |
   | Core dumps | The dump directory |
   | Deleted-but-open files | `lsof +L1` |

3. Free space safely, then fix the root cause: log rotation, retention policies, or a bigger volume.

**Inodes low:** `find / -xdev -type d -size +1M` finds directories with huge file counts.

**Read-only:** check `dmesg` for I/O errors. The disk may be failing, so plan to replace it rather than just remount.

## 9. Production tips & pitfalls

- `avail_bytes` excludes the root-reserved 5% on ext4. `free_bytes` includes it. Alert on avail.
- Tune the prediction window to the workload. Use `[6h]` → +24h for slow-growing volumes, and `[1h]` → +4h for fast ones.
- On Kubernetes, also watch PVCs: `kubelet_volume_stats_available_bytes` / `kubelet_volume_stats_capacity_bytes`.

## 10. Exercises

1. Add a `HostDiskWillFillIn24Hours` alert with `[6h]` and `24 * 3600`.
2. Add an "hours until full" stat panel using the `deriv` query.
3. Add an alert for write latency > 100 ms for 10m.
