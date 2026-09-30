# Observability Lab - common commands.  Run `make` or `make help` for the list.
SHELL := /bin/bash
PROM_IMG := prom/prometheus:v3.1.0
AM_IMG   := prom/alertmanager:v0.28.0
SD       := prometheus/file_sd

.DEFAULT_GOAL := help
.PHONY: help up down clean ps logs reload validate dashboards alerts reset-chaos db-on db-off mq-on mq-off k8s-up k8s-down

help: ## Show this help
	@grep -E '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n",$$1,$$2}'

up: ## Start the core stack (builds demo images)
	docker compose up -d --build
	@echo; echo "Grafana      http://localhost:3000  (admin/admin)"; \
	 echo "Prometheus   http://localhost:9090"; echo "Alertmanager http://localhost:9093"; \
	 echo "Alerts log:  docker logs -f lab-alert-logger"

down: ## Stop everything (keeps data volumes)
	rm -f $(SD)/enabled/*.json
	docker compose --profile db --profile mq down

clean: ## Stop everything AND delete Prometheus/Grafana data
	rm -f $(SD)/enabled/*.json
	docker compose --profile db --profile mq down -v --remove-orphans
	-docker rm -f lab-loadgen-spike lab-cpu-hog lab-host-stress lab-io-stress lab-iperf-server lab-iperf-client 2>/dev/null

ps: ## Show running lab containers
	docker compose --profile db --profile mq ps

logs: ## Follow logs of all lab containers
	docker compose --profile db --profile mq logs -f --tail=50

reload: ## Reload Prometheus config and rules without restart
	curl -fsS -X POST http://localhost:9090/-/reload && echo "reloaded"

validate: ## Check Prometheus config, all rules and Alertmanager config (via Docker)
	docker run --rm --entrypoint promtool -v $(CURDIR)/prometheus:/etc/prometheus:ro -v $(CURDIR)/projects:/lab/projects:ro \
	  $(PROM_IMG) check config /etc/prometheus/prometheus.yml
	docker run --rm --entrypoint amtool -v $(CURDIR)/alertmanager:/etc/alertmanager:ro \
	  $(AM_IMG) check-config /etc/alertmanager/alertmanager.yml

dashboards: ## Regenerate projects/*/dashboard.json from tools/build_dashboards.py
	python3 tools/build_dashboards.py

alerts: ## List pending and firing alerts
	@python3 tools/alerts.py

reset-chaos: ## Reset chaos on both demo apps
	-curl -fsS -X POST http://localhost:8081/chaos/reset; echo
	-curl -fsS -X POST http://localhost:8082/chaos/reset; echo

db-on: ## Project 13: start Postgres + Redis and their exporters, enable scraping
	docker compose --profile db up -d
	cp $(SD)/available/postgres.json $(SD)/available/redis.json $(SD)/enabled/
	@echo "Targets appear in Prometheus within ~30s"

db-off: ## Project 13: stop databases and disable scraping
	rm -f $(SD)/enabled/postgres.json $(SD)/enabled/redis.json
	docker compose --profile db stop postgres postgres-exporter redis redis-exporter
	docker compose --profile db rm -f postgres postgres-exporter redis redis-exporter

mq-on: ## Project 14: start Kafka, exporter, producer and consumer, enable scraping
	docker compose --profile mq up -d --build
	cp $(SD)/available/kafka.json $(SD)/enabled/
	@echo "Kafka needs ~30-60s before messages flow"

mq-off: ## Project 14: stop Kafka stack and disable scraping
	rm -f $(SD)/enabled/kafka.json
	docker compose --profile mq stop kafka kafka-exporter mq-producer mq-consumer
	docker compose --profile mq rm -f kafka kafka-exporter mq-producer mq-consumer

k8s-up: ## Projects 08/09: create kind cluster + kube-prometheus-stack
	./k8s/install.sh

k8s-down: ## Projects 08/09: delete the kind cluster
	./k8s/uninstall.sh
