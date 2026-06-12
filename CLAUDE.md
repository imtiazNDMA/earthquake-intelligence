# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 📚 High-Level Architecture Overview

The project, `eqMonitoring2`, is structured as a spatial environmental monitoring platform. The architecture follows a clear separation of concerns: **Data Ingestion & Processing** $\rightarrow$ **Core Domain Logic** $\rightarrow$ **API/Service Layer**.

### Data Flow
1.  **Input:** Raw data (e.g., boundary shapefiles, event catalogs) are ingested and managed by specialized scripts found in the `scripts/` directory (e.g., `load_boundaries.py`, `build_tiles.py`).
2.  **Persistence:** Data persistence is heavily reliant on **PostGIS** integration (indicated by the context of geospatial features). Core models and schema definitions can be found within files like `src/eqmon/db.py` or associated test fixtures.
3.  **Processing:** The `src/eqmon/` directory contains the primary business logic modules (e.g., calculating impacts, managing boundaries). These services read from the persistent store and perform complex spatial and temporal calculations.

### Key Modules/Responsibilities
*   `scripts/`: **Build and ETL Scripts.** This is the operational entry point for preparing assets. Use these scripts to generate necessary data artifacts like vector tiles (`build_tiles.py`) or rasterizations (`rasterize_vs30.py`). *These run prior to any testing or serving.*
*   `src/eqmon/`: **Core Library.** Contains reusable business logic (e.g., `boundaries.py`, event handling, projection utilities). This is where most functional code changes will occur.
*   `tests/`: **Test Suite.** The project uses a highly test-driven approach. All new functionality must be accompanied by tests written here. Specific components have dedicated test files (e.g., `test_boundaries.py`, `test_events_api.py`).

## 🛠️ Common Development Tasks & Commands

### 🚀 Getting Started / Setup
1.  **Dependencies:** Installation should be managed via environment management scripts/files, referencing `requirements*.txt`. Check the project root or `.venv` for explicit installation instructions.
2.  **Environment Variables:** Configuration (e.g., database credentials, API keys) must be managed through environment variables, typically referenced in a `.env` file example located near entry points.

### ⚙️ Lifecycle Commands
| Command | Purpose | Notes |
| :--- | :--- | :--- |
| `python scripts/load_boundaries.py` | Loads and validates boundary data into the database. | A prerequisite for most features involving geopolitical boundaries. |
| `python scripts/build_tiles.py` | Generates necessary vector tiles (PMTiles) from source geometries. | Critical step for frontend consumption of boundary layers. |
| `python scripts/rasterize_vs30.py` | Runs the spatial rasterization process, e.g., for Vs30 data. | Updates derived spatial datasets used by the system. |
| `pytest` or `python -m pytest tests/*` | Runs the entire suite of unit and integration tests. | The standard way to verify functionality. For isolated testing, use `pytest <path/to/test_file.py>`. |

### 🐞 Developing a New Feature (The Pattern)
1.  **Define/Sketch:** Determine the required new data/logic component.
2.  **Implement Scripts:** If asset generation is needed, update or create scripts in `scripts/` and test them manually.
3.  **Write Code:** Implement business logic in an appropriate module within `src/eqmon/`.
4.  **Test-Driven Development (TDD):** *Before* committing the code change, write a new test case in the corresponding `tests/` directory to fail on the current implementation, then implement the minimal code fix to make it pass. This ensures test coverage and correctness immediately.

## ✨ Specific Guidance Notes
*   **Geospatial Focus:** All spatial operations (e.g., impact calculation) should prioritize PostGIS capabilities for performance. Be mindful of **rasterization alignment**, especially when sub-kilometer precision is required, as this might require revisiting half-cell grid dilation logic in `data/Vs30.tif`.
*   **API Interception:** If working on the API layer, pay close attention to how data flows between `src/eqmon/events/sources.py` and the database module (`src/eqmon/db.py`) to ensure correct event deduplication and state management are maintained across different sources (USGS, MET).