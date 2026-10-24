# IATP 常用开发与验证命令。
# Windows 使用 Git Bash；Linux/macOS 使用系统 make 即可。

ifeq ($(OS),Windows_NT)
PYTHON ?= .venv/Scripts/python
else
PYTHON ?= .venv/bin/python
endif
NPM ?= npm

.PHONY: help install install-backend install-frontend seed serve dev-backend \
        dev-frontend build test lint typecheck check docker-build docker-up \
        docker-down clean

help:
	@echo "IATP targets:"
	@echo "  install          安装后端（editable + dev）与前端依赖"
	@echo "  seed             重建演示运行、基线与回归（--force）"
	@echo "  serve            启动 API + 已构建前端 http://127.0.0.1:8000"
	@echo "  dev-backend      启动带 reload 的后端"
	@echo "  dev-frontend     启动 Vite 开发服务器 http://localhost:5173"
	@echo "  build            前端类型检查与生产构建"
	@echo "  test             pytest tests/ -q"
	@echo "  lint             ruff check ."
	@echo "  typecheck        mypy src"
	@echo "  check            全部质量门禁：lint + typecheck + test + build"
	@echo "  docker-build     构建 Docker 镜像"
	@echo "  docker-up        启动 docker compose 服务"
	@echo "  docker-down      停止 docker compose 服务"
	@echo "  clean            清理缓存与前端构建产物（不删除 data/artifacts）"

install: install-backend install-frontend

install-backend:
	$(PYTHON) -m pip install -e ".[dev]"

install-frontend:
	$(NPM) --prefix frontend install

seed:
	$(PYTHON) -m ia_platform seed --force

serve:
	$(PYTHON) -m ia_platform serve

dev-backend:
	$(PYTHON) -m ia_platform serve --reload

dev-frontend:
	$(NPM) --prefix frontend run dev

build:
	$(NPM) --prefix frontend run typecheck
	$(NPM) --prefix frontend run build

test:
	$(PYTHON) -m pytest tests/ -q

lint:
	$(PYTHON) -m ruff check .

typecheck:
	$(PYTHON) -m mypy src

check: lint typecheck test build

docker-build:
	docker compose build

docker-up:
	docker compose up -d

docker-down:
	docker compose down

clean:
	rm -rf frontend/dist frontend/.vite .pytest_cache .ruff_cache .mypy_cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
