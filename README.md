# NL2SQL Optimizer: Schema-Aware Translation with Automated Query Optimization Feedback

An end-to-end research engineering system that translates natural language questions into relational SQL queries, dynamically inspects query execution plans (`EXPLAIN ANALYZE`), detects structural database anti-patterns, and provides an optimized query rewrite with empirical before-and-after cost comparisons.

---

## 🎯 Problem Statement & Motivation
State-of-the-art Text-to-SQL frameworks prioritize **syntactic and semantic correctness** (does the query output match the intended question?) while completely ignoring **runtime query performance**. In production enterprise systems, non-technical analysts often generate queries with devastating performance flaws:
- Unindexed foreign-key joins causing full sequential table scans (`Seq Scan`).
- Non-SARGable clauses (e.g., `LIKE '%query'`).
- Implicit cross joins producing accidental Cartesian explosions.
- Inefficient nested loop joins on large row subsets.

**NL2SQL Optimizer bridges this gap** by combining:
1. **Schema Introspection**: Live relational schema reflection via SQLAlchemy.
2. **Multi-Model LLM Orchestration**: Side-by-side SQL translation with Gemini, OpenAI, and Claude.
3. **Automated Plan Inspection**: Headless `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` execution in PostgreSQL.
4. **Deterministic Anti-Pattern Engine**: Rule-based detection classifying execution vulnerabilities.
5. **Feedback Loop Rewrite**: Re-prompting the LLM with execution plan bottlenecks to generate an empirically verified optimization rewrite.

---

## 🏗️ System Architecture

```
User (Natural Language Query)
             │
             ▼
    ┌──────────────────┐
    │  React Frontend  │  (Port 3000: Vite + Tailwind CSS + Interactive Studio)
    └────────┬─────────┘
             │ HTTP REST
             ▼
    ┌──────────────────┐
    │  FastAPI Backend │  (Port 8000: SQLAlchemy, Pydantic v2, LLM Clients)
    └────────┬─────────┘
             ├───► [Schema Introspector] ───► Live PostgreSQL DB (Tables, PKs, FKs, Indexes)
             │
             ├───► [Prompt Engine] ──────────► Injects Live Schema & Constraints
             │
             ├───► [LLM Client] ─────────────► Gemini 2.0 Flash / GPT-4o Mini / Claude 3.5 Haiku
             │                                (Generates Raw SQL + Token & Cost Tracking)
             │
             ├───► [SQL Runner] ─────────────► Runs EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
             │
             ├───► [Plan Parser] ────────────► Flattens Plan Tree (Costs, Actual Rows, Timing)
             │
             ├───► [Anti-Pattern Engine] ────► Flags Seq Scans, Missing FK Indexes, Filter Waste
             │
             └───► [Optimizer Pipeline] ─────► Secondary LLM Prompt with Plan Bottlenecks
                                              ──► Generates Optimized Rewrite
                                              ──► Runs 2nd EXPLAIN pass
                                              ──► Computes Delta: Cost %, Time %, Issues Remaining
```

---

## ⚡ Key Features

| Capability | Description |
|---|---|
| **Live Schema Reflection** | Zero hardcoding; point `DATABASE_URL` at any PostgreSQL instance and introspect tables, columns, constraints, and indexes on-the-fly. |
| **Deterministic Detection** | 7 dedicated heuristics detecting full table scans, missing FK indexes, high row filter waste, `SELECT *`, leading wildcard filters, and Cartesian products. |
| **Scale Simulation Mode** | Employs `enable_seqscan = OFF` to force index-path planning on small/moderate development datasets, accurately revealing large-scale query behavior. |
| **Multi-Provider Comparison** | Side-by-side comparison across Google Gemini, OpenAI, and Anthropic, tracking USD cost down to 6 decimals, token throughput, and response latency. |
| **Empirical Delta Verification** | Measures query cost reduction percentage using PostgreSQL planner cost units and actual millisecond execution times. |

---

## 🚀 Quickstart & Setup

### 1. Prerequisites
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running.
- API Key for at least one model provider (Google Gemini, OpenAI, or Anthropic).

### 2. Configure Environment Secrets
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Open `.env` and configure your API key:
```ini
DATABASE_URL=postgresql://nl2sql_user:nl2sql_pass@db:5432/nl2sql
DEFAULT_PROVIDER=gemini
GEMINI_API_KEY=your_actual_gemini_key_here
GEMINI_MODEL=gemini-2.0-flash
```

### 3. Launch Services
Run the full multi-container stack:
```bash
docker compose up --build
```

- **Frontend UI**: [http://localhost:3000](http://localhost:3000)
- **Backend Swagger Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Database**: PostgreSQL 15 on port `5432` (pre-seeded with 7,300+ e-commerce records)

---

## 📊 Evaluation & Benchmarking
The project includes a 10-query benchmark suite assessing filter operations, multi-table joins, subqueries, and date-range aggregations:
```bash
cd evaluation
python run_benchmark.py
```
This logs query performance improvements, anti-patterns caught, and API expenditures to `benchmark_results.json`.

---

## 📂 Project Structure
```
nl2sql-optimizer/
├── backend/
│   ├── antipattern_detector.py # Rule-based AST & plan inspection engine
│   ├── llm_client.py           # Unified client for Gemini, OpenAI & Claude
│   ├── main.py                 # FastAPI application & REST endpoints
│   ├── models.py               # Pydantic v2 data transfer schemas
│   ├── optimizer.py            # End-to-end before/after optimization loop
│   ├── plan_parser.py          # PostgreSQL EXPLAIN JSON tree flattener
│   ├── prompt_builder.py       # Strict schema injection & rewrite prompt builder
│   ├── schema_introspector.py  # SQLAlchemy database reflection
│   └── sql_runner.py           # EXPLAIN ANALYZE executor
├── frontend/
│   ├── src/
│   │   ├── App.jsx             # React 18 interactive optimizer dashboard
│   │   └── main.jsx            # Entry point
│   ├── package.json
│   ├── vite.config.js
│   └── tailwind.config.js
├── db/
│   └── seed.sql                # Synthetic relational schema (7,300+ rows)
├── evaluation/
│   ├── benchmark_queries.json  # 10 test query scenarios
│   └── run_benchmark.py        # Automated benchmarking client
├── docker-compose.yml          # Container configuration
└── .env.example
```
