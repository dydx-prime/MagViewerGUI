# Detect python command
PYTHON := $(shell command -v python3 2>/dev/null || command -v python)
VENV   := venv
PIP    := $(VENV)/bin/pip
RUN    := $(VENV)/bin/python

.PHONY: setup run freeze install clean help

help:
	@echo ""
	@echo "Usage: make [command]"
	@echo ""
	@echo "  setup              Create venv and install requirements.txt"
	@echo "  run                Launch main.py inside the venv"
	@echo "  install pkg=<name> Install a new package  (e.g. make install pkg=numpy)"
	@echo "  freeze             Freeze installed packages to requirements.txt"
	@echo "  clean              Delete the venv folder"
	@echo ""

setup:
	@echo "[*] Creating virtual environment..."
	$(PYTHON) -m venv $(VENV)
	@echo "[*] Installing requirements..."
	$(PIP) install -r requirements.txt
	@echo "[*] Setup complete. Run: make run"

run:
	@echo "[*] Launching app..."
	$(RUN) main.py

freeze:
	@echo "[*] Freezing packages..."
	$(PIP) freeze > requirements.txt
	@echo "[*] requirements.txt updated."

install:
	@if [ -z "$(pkg)" ]; then \
		echo "[!] Usage: make install pkg=<package>"; \
	else \
		echo "[*] Installing $(pkg)..."; \
		$(PIP) install $(pkg); \
	fi

clean:
	@echo "[*] Removing venv..."
	rm -rf $(VENV)
	@echo "[*] Cleaned."