include config.mk dev.mk

# install + run targets
.PHONY: install run

# cluster admin commands to operate Warden
.PHONY: set-accessible \
 ping get-logs

# Mock QPU when the actual QPU is not available
.PHONY: start-mock-qpu start-qutip-qpu

VENV=.venv
PIP_VERSION ?= 26.1
ifeq ($(WITH_PG),1)
INSTALL_FLAGS  += -r requirements-pg.txt
endif
ifeq ($(WITH_MARIADB),1)
INSTALL_FLAGS  += -r requirements-mariadb.txt
endif

# cluster admin commands

config.yaml:
	@new_config="warden/lib/config/config.sample.yaml"; \
	if [ ! -f config.yaml ]; then \
		cp "$$new_config" config.yaml; \
		exit 0; \
	fi; \
	if cmp -s "$$new_config" config.yaml; then \
		exit 0; \
	fi; \
	last_i=0; \
	i=1; \
	while [ -e "config.backup-$$i.yaml" ]; do \
		last_i=$$i; \
		i=$$((i + 1)); \
	done; \
	if [ "$$last_i" -eq 0 ] || ! cmp -s config.yaml "config.backup-$$last_i.yaml"; then \
		cp config.yaml "config.backup-$$i.yaml"; \
	fi; \
	cp "$$new_config" config.yaml

# Note: the --copies flag is used to create a copy of the binaries, since a symlink may not always work
$(VENV)/bin/python: config.yaml
	@if [ -d ./venv ]; then \
		echo "Removing legacy ./venv"; \
		rm -rf ./venv; \
	fi
	@if [ -z "$(PYTHON)" ]; then \
		echo "Usage: make venv PYTHON=/path/to/python"; \
		exit 1; \
	fi
	@if [ -d $(VENV) ]; then \
		echo "$(VENV) already created"; \
	else \
		echo "Creating $(VENV) with $(PYTHON)"; \
		$(PYTHON) -m venv --copies $(VENV); \
		echo "Installing pip $(PIP_VERSION) in $(VENV)"; \
		$(VENV)/bin/python -m pip install -U 'pip~=$(PIP_VERSION)'
		echo "Virtualenv created in $(VENV) using $(PYTHON)"; \
	fi

install: $(VENV)/bin/python
	$(VENV)/bin/python -m pip install -r requirements.txt $(INSTALL_FLAGS)

run: migrate
	@bash -c '\
	set -uo pipefail; \
	PIDS=(); \
	cleanup() { \
		trap - SIGINT SIGTERM EXIT; \
		if [ "$${#PIDS[@]}" -gt 0 ]; then \
			kill -TERM "$${PIDS[@]}" 2>/dev/null || true; \
			for pid in "$${PIDS[@]}"; do \
				wait "$$pid" 2>/dev/null || true; \
			done; \
		fi; \
	}; \
	on_signal() { \
		cleanup; \
		exit 0; \
	}; \
	trap on_signal SIGINT SIGTERM; \
	trap cleanup EXIT; \
	$(VENV)/bin/python -m warden.api.main & PIDS+=($$!); \
	$(VENV)/bin/python -m warden.scheduler & PIDS+=($$!); \
	set +e; \
	wait -n "$${PIDS[@]}"; \
	STATUS=$$?; \
	set -e; \
	cleanup; \
	exit $$STATUS'


migrate:
	$(MAKE) alembic ARGS="upgrade head"

# cluster admin warden requests 
URL ?= http://localhost:8006
MESSAGE ?= Update

define ACCESSIBLE_POST_JSON_PAYLOAD
{"is_accessible": $(IS_ACCESSIBLE), "message": "$(MESSAGE)"}
endef

set-accessible:

	@if [ -z "$(IS_ACCESSIBLE)" ]; then \
		echo "ERROR 'IS_ACCESSIBLE' is required."; \
		echo "Usage: make set-accessible IS_ACCESSIBLE=[true|false] MESSAGE=\"Update\""; \
		exit 1; \
	fi

	curl -X POST $(URL)/accessible \
		-H "X-Munge-Cred: $$(munge -n)" \
		-H "Content-Type: application/json" \
		-d '$(ACCESSIBLE_POST_JSON_PAYLOAD)'

get-logs:

	curl -X GET $(URL)/jobs/$(ID)/logs \
		-H "X-Munge-Cred: $$(munge -n)"

ping:
	curl $(URL)


# Mock QPU when the actual QPU is not available

start-mock-qpu: $(VENV)/bin/python
	$(VENV)/bin/python -m uvicorn mock_qpu_api.app:app --app-dir tests

start-qutip-qpu: $(VENV)/bin/python
	MOCK_QPU_API_EMUL=true $(MAKE) start-mock-qpu
