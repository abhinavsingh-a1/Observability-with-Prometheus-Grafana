# 13 · Databases: PostgreSQL & Redis

> **Is the data layer healthy: connections, slow transactions, cache efficiency, memory?**

| | |
|---|---|
| **Layer** | Dependencies |
| **Method** | USE for the database, plus database-specific health signals |
| **Data source** | `postgres_exporter` (:9187) and `redis_exporter` (:9121) |
| **Files** | `alerts.yml` · `dashboard.json` · `trigger.sh` |
| **Prerequisite** | `make db-on` (starts the containers and enables the scrape targets) |
| **Time** | ~25 min |

## 1. Why this matters

Most application incidents are really **database incidents**. The app gets slow or throws 5xx because:

| Problem | Symptom in the app |
|---|---|
| Connections exhausted (`too many clients`) | Sudden 5xx on every endpoint |
| Long-running transaction holding locks | Queries pile up behind it, latency explodes |
| Long transactions blocking VACUUM | Table bloat, slow queries over days |
| Working set no longer fits in memory (low cache hit) | Gradual latency increase |
| Deadlocks | Sporadic failed writes |
| Redis full → evictions → misses | More load on the DB behind the cache, a cascade |

## 2. How it works

Databases don't expose Prometheus metrics natively, so an **exporter** sits next to each one. It connects as a client, runs internal queries, and translates the results into metrics:

- postgres_exporter reads `pg_stat_activity`, `pg_stat_database`, `pg_settings`, and more.
- redis_exporter reads `INFO` and `CONFIG`.

The lab deliberately sets Postgres `max_connections=50` and Redis `maxmemory 64mb` with `allkeys-lru`, so problems are easy to trigger.

`make db-on` does two things: starts the `db` compose profile, and copies `prometheus/file_sd/available/{postgres,redis}.json` into `file_sd/enabled/`. Prometheus picks up the new targets within 30s (file-based service discovery). `make db-off` reverses both.

## 3. Key metrics

**PostgreSQL**

| Metric | Meaning |
|---|---|
| `pg_up` | Exporter can connect |
| `pg_stat_activity_count{datname,state}` | Connections by state (active, idle, idle in transaction) |
| `pg_settings_max_connections` | Limit |
| `pg_stat_activity_max_tx_duration{datname,state}` | Age of the oldest open transaction |
| `pg_stat_database_blks_hit` / `blks_read` | Buffer cache hits vs disk reads |
| `pg_stat_database_xact_commit` / `xact_rollback` | Transactions |
| `pg_stat_database_deadlocks` | Deadlock counter |

**Redis**

| Metric | Meaning |
|---|---|
| `redis_up` | Reachable |
| `redis_memory_used_bytes` / `redis_memory_max_bytes` | Memory vs maxmemory |
| `redis_evicted_keys_total` | Keys evicted by the maxmemory policy |
| `redis_keyspace_hits_total` / `misses_total` | Cache efficiency |
| `redis_connected_clients` / `redis_config_maxclients` | Clients |
| `redis_commands_processed_total` | Throughput |

## 4. PromQL cookbook

```promql
# Connection saturation
sum(pg_stat_activity_count) / max(pg_settings_max_connections)

# "idle in transaction" = app opened a transaction and forgot it (connection + lock leak)
sum(pg_stat_activity_count{state="idle in transaction"})

# Oldest transaction
max by (datname) (pg_stat_activity_max_tx_duration)

# Buffer cache hit ratio (aim for > 99% on OLTP)
sum(rate(pg_stat_database_blks_hit[5m]))
/ (sum(rate(pg_stat_database_blks_hit[5m])) + sum(rate(pg_stat_database_blks_read[5m])))

# TPS
sum(rate(pg_stat_database_xact_commit[5m]) + rate(pg_stat_database_xact_rollback[5m]))

# Redis memory %, hit ratio, evictions/s
redis_memory_used_bytes / redis_memory_max_bytes
rate(redis_keyspace_hits_total[5m]) / (rate(redis_keyspace_hits_total[5m]) + rate(redis_keyspace_misses_total[5m]))
rate(redis_evicted_keys_total[5m])
```

## 5. Alerts (`alerts.yml`)

| Alert | Condition | Severity |
|---|---|---|
| `PostgresDown` | `pg_up == 0` for 1m | critical |
| `PostgresTooManyConnections` | > 80% of max_connections for 2m | warning |
| `PostgresLongRunningTransaction` | oldest tx > 60s (lab; production 5–30 min) | warning |
| `PostgresLowCacheHitRatio` | < 90% with real read load, for 10m | warning |
| `PostgresDeadlocks` | any deadlock in 5m | warning |
| `RedisDown` | `redis_up == 0` for 1m | critical |
| `RedisMemoryNearMax` | > 90% of maxmemory | warning |
| `RedisEvictingKeys` | evictions > 0 for 2m | warning |
| `RedisLowHitRatio` | < 80% with > 10 lookups/s for 10m | warning |
| `RedisTooManyClients` | > 80% of maxclients | warning |

## 6. Dashboard

- **Stats:** PG up, PG connections %, Redis up, and Redis memory %.
- **Postgres graphs:** connections by state vs max, longest transaction, cache hit ratio, and TPS with deadlocks.
- **Redis graphs:** memory vs max, hit ratio, operations and evictions, and clients.

## 7. Hands-on lab

```bash
make db-on
./projects/13-databases/trigger.sh connections   # 45/50 connections
./projects/13-databases/trigger.sh reset
./projects/13-databases/trigger.sh long-tx       # 5-minute transaction
./projects/13-databases/trigger.sh deadlock      # a real deadlock
./projects/13-databases/trigger.sh load          # pgbench, watch TPS
./projects/13-databases/trigger.sh redis-fill    # evictions
./projects/13-databases/trigger.sh redis-miss    # low hit ratio
./projects/13-databases/trigger.sh reset
make db-off
```

Try `docker stop lab-postgres`: `PostgresDown` fires while `up{job="postgres"}` stays **1**. The exporter is fine; the database isn't. That's why exporters report their own `*_up` metric.

## 8. Runbook

**Too many connections**

1. Who's connected? `select usename, application_name, state, count(*) from pg_stat_activity group by 1,2,3 order by 4 desc;`
2. Many `idle` connections point to a pool that is too large. Many `idle in transaction` point to an app bug.
3. Fix it with a connection pooler (PgBouncer), right-sized app pools, and `idle_in_transaction_session_timeout`.

**Long-running transaction**

1. Find it: `select pid, now()-xact_start, state, query from pg_stat_activity order by xact_start limit 5;`
2. Find out who it blocks with `pg_blocking_pids(pid)`.
3. Terminate it only if you're sure: `select pg_terminate_backend(<pid>);`

**Low cache hit ratio:** check whether the working set outgrew `shared_buffers` and RAM, or whether a new query is scanning a big table (missing index). Use `pg_stat_statements` to find it.

**Redis evicting:** increase maxmemory, shorten TTLs, or check whether the eviction policy fits (allkeys-lru for caches, noeviction for data stores).

## 9. Production tips & pitfalls

- Give the exporter a **dedicated read-only user** (`pg_monitor` role), never the superuser.
- Enable `pg_stat_statements` and the exporter's queries for it to get per-query latency. That's the most valuable Postgres signal.
- Replication: `pg_replication_lag_seconds` (on replicas) and `pg_stat_replication_*` on the primary. Alert when lag exceeds your RPO.
- For MySQL use `mysqld_exporter`; for MongoDB, `mongodb_exporter`. The concepts are identical.

## 10. Exercises

1. Add an alert on `pg_stat_activity_count{state="idle in transaction"} > 5`.
2. Enable `pg_stat_statements` and build a "top 5 slowest queries" table.
3. Add a Redis panel for `redis_db_keys` (keys per database).
