# Simulador Profissional de Previsão de Jogos de Ténis

Backend de um simulador de jogos de ténis: simulação Monte Carlo
ponto-a-ponto (NumPy vetorizado) e previsão de vencedor por modelo de
Machine Learning (XGBoost calibrado), servidos por uma API REST em
FastAPI, com autenticação JWT, tarefas assíncronas via Celery/Redis,
cache, rate limiting e observabilidade completa.

Projeto de portfólio pessoal — construído módulo a módulo, cada um com
arquitetura explicada, código completo, testes e validação antes de
avançar para o seguinte.

## Stack

Python 3.12 · FastAPI · SQLAlchemy 2.0 (async) · PostgreSQL (SQLite em
testes) · Alembic · Celery + Redis · NumPy/SciPy · scikit-learn +
XGBoost · MLflow · structlog + Prometheus · pytest · Docker

## Arquitetura

```
app/
├── api/            # Routers FastAPI, schemas Pydantic, middleware, dependências
├── auth/           # (hashing e JWT vivem em app/core/security.py)
├── cache/           # Rate limiting (sliding window) e cache de simulações — Redis
├── core/             # Configuração, segurança (JWT/bcrypt), logging, métricas
├── db/               # Engine assíncrono, Base declarativa
├── ml/                # Feature engineering, dataset sintético, modelo preditivo
├── models/           # Modelos ORM (SQLAlchemy 2.0, totalmente tipados)
├── repositories/     # Camada de acesso a dados (Repository Pattern)
├── services/          # Lógica de domínio (estatísticas de jogadores)
├── simulation/        # Motor Monte Carlo vetorizado
└── tasks/             # Tarefas Celery (simulações em background)
```

Cada módulo foi desenvolvido isoladamente, com a respetiva justificação
arquitetural registada na conversa que produziu este código:

1. **Fundação** — configuração + camada de persistência
2. **Repository Pattern** — acesso a dados genérico e tipado
3. **Camada de Serviços** — forma recente, estatísticas por superfície, H2H
4. **Motor Monte Carlo** — simulação ponto-a-ponto vetorizada (validada contra fórmula analítica)
5. **Modelo Preditivo ML** — baseline + XGBoost calibrado, tracking MLflow
6. **Camada de API** — routers, schemas, paginação cursor-based, erros RFC 7807
7. **Autenticação** — JWT, refresh tokens rotacionados, bcrypt
8. **Tarefas assíncronas** — Celery + Redis, simulações em background
9. **Cache** — rate limiting sliding-window + cache de resultados, Redis
10. **Observabilidade** — logging estruturado JSON, métricas Prometheus
11. **Testes E2E + CI/CD** — jornada completa de utilizador, GitHub Actions

## Correr localmente

### Com Docker (recomendado)

```bash
cd backend
docker compose up --build
```

Isto arranca a API (`:8000`), um worker Celery, PostgreSQL e Redis.
Documentação interativa em `http://localhost:8000/docs`.

### Sem Docker

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload
```

Num terminal separado, para as simulações em background:

```bash
celery -A app.tasks.celery_app worker --loglevel=info
```

## Testes

```bash
cd backend
pytest                                    # suite completa (158 testes)
pytest --cov=app --cov-report=term-missing  # com cobertura (92%)
ruff check app/ tests/                    # lint
mypy app/                                 # verificação de tipos
```

A suite inclui testes unitários, de integração (via `httpx.AsyncClient`
sobre a app FastAPI real) e um teste end-to-end
(`tests/e2e/test_full_user_journey.py`) que percorre a jornada completa
de um utilizador através da API HTTP real — registo, login, consulta
de jogadores, simulação Monte Carlo assíncrona, previsão ML, rotação
de tokens e logout — sem mockar nenhuma camada intermédia.

## CI/CD

`.github/workflows/ci.yml`: lint (ruff + mypy) → testes com cobertura →
verificação de migrações Alembic sem drift → build e push da imagem
Docker para o GHCR (só em `main`).

## Migrações de base de dados

```bash
alembic revision --autogenerate -m "descrição da mudança"
alembic upgrade head
```

## Estado do projeto

Todos os 11 módulos do roteiro original estão implementados e
validados (158 testes, 92% de cobertura, `mypy`/`ruff` sem erros). Por
construir, fora do âmbito de portfólio definido: endpoints de escrita
para jogadores/torneios (`POST`/`PATCH /players`, endpoints
`/admin/*`), frontend, e deployment real para uma cloud.
