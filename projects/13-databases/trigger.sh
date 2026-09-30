#!/usr/bin/env bash
# Project 13 - Databases. Requires: make db-on
# Usage: ./trigger.sh connections|long-tx|load|deadlock|redis-fill|redis-miss|reset
set -euo pipefail
PSQL="docker exec lab-postgres psql -U postgres -q"
docker inspect lab-postgres >/dev/null 2>&1 || { echo "Run 'make db-on' first."; exit 1; }
case "${1:-help}" in
  connections)
    echo "opening 45 connections, each running a 4-minute query (max_connections=50)"
    docker exec -d lab-postgres sh -c 'for i in $(seq 45); do psql -U postgres -c "select pg_sleep(240)" >/dev/null 2>&1 & done; wait'
    echo "-> PostgresTooManyConnections (and LongRunningTransaction) in ~3 min" ;;
  long-tx)
    docker exec -d lab-postgres psql -U postgres -c "begin; select txid_current(); select pg_sleep(300); commit;"
    echo "one 5-minute transaction -> PostgresLongRunningTransaction in ~2 min" ;;
  load)
    $PSQL -c "select 1" >/dev/null
    docker exec lab-postgres pgbench -U postgres -i -s 20 postgres >/dev/null 2>&1 || true
    echo "pgbench: 20 clients for 3 min (watch TPS, cache hit ratio, connections)"
    docker exec lab-postgres pgbench -U postgres -c 20 -j 4 -T 180 -P 30 postgres ;;
  deadlock)
    $PSQL -c "create table if not exists lab_dl(id int primary key, v int); insert into lab_dl values (1,0),(2,0) on conflict do nothing;"
    docker exec -d lab-postgres psql -U postgres -c "begin; update lab_dl set v=v+1 where id=1; select pg_sleep(2); update lab_dl set v=v+1 where id=2; commit;"
    docker exec    lab-postgres psql -U postgres -c "begin; update lab_dl set v=v+1 where id=2; select pg_sleep(2); update lab_dl set v=v+1 where id=1; commit;" || true
    echo "one transaction was killed with 'deadlock detected' -> PostgresDeadlocks" ;;
  redis-fill)
    echo "writing ~200 MB of 1 KB values into a 64 MB Redis -> memory near max + evictions"
    docker exec lab-redis redis-benchmark -q -t set -n 200000 -r 1000000 -d 1024 ;;
  redis-miss)
    echo "reading random keys that mostly don't exist -> low hit ratio"
    docker exec lab-redis redis-benchmark -q -t get -n 500000 -r 100000000 ;;
  reset)
    $PSQL -c "select pg_terminate_backend(pid) from pg_stat_activity where pid <> pg_backend_pid() and backend_type='client backend';" >/dev/null
    docker exec lab-redis redis-cli flushall >/dev/null
    echo "terminated client connections, flushed redis" ;;
  *) echo "usage: $0 connections|long-tx|load|deadlock|redis-fill|redis-miss|reset"; exit 1 ;;
esac
