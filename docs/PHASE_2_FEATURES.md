# Phase 2: Data Ingestion & Harmonization

This document details the features implemented in Phase 2, focusing on ingesting official infrastructure data and harmonizing it with citizen reports.

## 1. Official Infrastructure Dataset Ingestion (2.1)

### Overview
We now support ingesting official datasets (e.g., from government ministries) into the `InfrastructureAsset` model. This allows the platform to serve as a unified registry of public assets.

### Key Features
- **Provenance Tracking**: Every ingested asset tracks:
  - `data_owner`: Organization owning the data (e.g., "Ministry of Health").
  - `source_url`: URL where the data was fetched from.
  - `license`: Data license (e.g., "Open Government License").
  - `update_frequency`: How often the source is updated.
  - `source_metadata`: JSON field storing the original raw properties for auditability.
- **GeoJSON Support**: The `InfrastructureIngester` service parses GeoJSON FeatureCollections.
- **Spatial Normalization**: Assets are automatically linked to the correct `GeographicArea` based on their coordinates using spatial lookups.

### Code References
- **Model**: [`InfrastructureAsset`](../backend/apps/infrastructure/models.py) (fields added in `0002_ingestion_fields.py`)
- **Service**: [`InfrastructureIngester`](../backend/apps/infrastructure/services/ingestion.py)
- **Tests**: [`test_ingestion.py`](../backend/apps/infrastructure/tests/test_ingestion.py) and [`test_ingestion_edge_cases.py`](../backend/tests/test_ingestion_edge_cases.py)

### Usage Example (Python Shell)
```python
from apps.infrastructure.services.ingestion import InfrastructureIngester

ingester = InfrastructureIngester(
    data_owner="Ministry of Works",
    license="CC-BY",
    source_url="https://works.gov.ng/roads.json"
)
ingester.ingest_geojson(geojson_data, mapping={"official_name": "RoadName", "asset_type": "Category"})
```

---

## 2. Data Harmonization (2.2)

### Overview
Harmonization links citizen-submitted reports to official infrastructure assets. This reduces duplication and helps verify if a reported issue corresponds to a known asset.

### Key Features
- **Spatial Matching**: Finds assets within a configurable distance (default 100m) of a report.
- **Type Filtering**: Ensures a "School" report matches a "School" asset.
- **Name Similarity**: Uses PostgreSQL `TrigramSimilarity` to rank matches by comparing the asset's official name with the report's description.
- **Auto-Linking**: If a match is very close (e.g., < 50m) and high confidence, the system can automatically link the report to the asset.
- **Review Queue**: A new API endpoint `/api/v1/reports/unmatched/` lists reports that haven't been linked, facilitating manual review.

### Code References
- **Service**: [`HarmonizationService`](../backend/apps/reports/services/harmonization.py)
- **API**: [`ReportViewSet.unmatched`](../backend/apps/reports/views.py)
- **Tests**: [`test_harmonization.py`](../backend/apps/reports/tests/test_harmonization.py)

### Usage Example (Python Shell)
```python
from apps.reports.services.harmonization import HarmonizationService

service = HarmonizationService()
# Find potential matches
matches = service.find_potential_matches(report, use_name_similarity=True)

# Auto-link if high confidence
linked_asset, success = service.harmonize_report(report, auto_link=True)
```

## 3. Testing & Verification

### Test Suites
- **Unit Tests**: `backend/apps/*/tests/` cover individual service logic.
- **E2E Tests**: `backend/tests/test_phase2_e2e.py` verifies the full flow (Ingest -> Report -> Harmonize).
- **Edge Cases**: `backend/tests/test_ingestion_edge_cases.py` tests CSV parsing and malformed data handling.

### Running Tests
```bash
docker compose exec backend pytest
```
