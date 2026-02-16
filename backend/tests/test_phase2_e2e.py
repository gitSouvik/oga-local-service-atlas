import pytest
from django.contrib.gis.geos import Point, Polygon

from apps.geography.models import GeographicArea
from apps.infrastructure.models import AssetType
from apps.infrastructure.services.ingestion import InfrastructureIngester
from apps.reports.models import Report
from apps.reports.services.harmonization import HarmonizationService


@pytest.mark.django_db
class TestPhase2Features:
    """
    End-to-end test suite for Phase 2: Ingestion & Harmonization.
    Verifies the full flow:
    1. Ingest official data (GeoJSON) -> InfrastructureAsset
    2. Create Citizen Report
    3. Harmonize (Link Report -> Asset)
    """

    def test_full_ingestion_and_harmonization_flow(self):
        # ------------------------------------------------------------------
        # 1. SETUP: Create a Geographic Area
        # ------------------------------------------------------------------
        from django.contrib.gis.geos import MultiPolygon

        # Create a Polygon and wrap it in MultiPolygon since the model expects MultiPolygon
        poly = Polygon.from_bbox((0, 0, 10, 10))
        multipoly = MultiPolygon(poly)

        area = GeographicArea.objects.create(
            name="Test State", country_code="NGA", admin_level="state", geometry=multipoly
        )
        assert area.pk is not None

        # ------------------------------------------------------------------
        # 2. INGESTION: Simulate Official Data Import
        # ------------------------------------------------------------------
        ingester = InfrastructureIngester(
            data_owner="Ministry of Health",
            license="Open Government License",
            source_url="https://data.gov.ng/hospitals.json",
            update_frequency="Quarterly",
        )

        # Simulated GeoJSON for a Hospital at (5, 5)
        geojson_data = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [5.0, 5.0]},
                    "properties": {
                        "OfficialName": "General Hospital Lagos",
                        "Category": "Hospital",
                        "Beds": 250,
                    },
                }
            ],
        }

        # Map source fields to our model
        mapping = {"official_name": "OfficialName", "asset_type": "Category"}

        assets = ingester.ingest_geojson(geojson_data, mapping)

        # Verify Ingestion
        assert len(assets) == 1
        hospital = assets[0]
        assert hospital.official_name == "General Hospital Lagos"
        assert hospital.asset_type == AssetType.HOSPITAL
        assert hospital.data_owner == "Ministry of Health"
        assert hospital.source_url == "https://data.gov.ng/hospitals.json"
        assert hospital.geographic_area == area
        assert hospital.location.x == 5.0
        assert hospital.location.y == 5.0

        # ------------------------------------------------------------------
        # 3. REPORTING: Citizen submits a report nearby
        # ------------------------------------------------------------------
        # Report is 10 meters away from the hospital
        # (0.0001 degrees is approx 11 meters)
        report = Report.objects.create(
            description="Power outage at the general hospital",
            location=Point(5.0001, 5.0),
            infrastructure_type=AssetType.HOSPITAL,
            reported_status="working",
            reporter_type="citizen",
        )

        # ------------------------------------------------------------------
        # 4. HARMONIZATION: Link Report to Asset
        # ------------------------------------------------------------------
        harmonizer = HarmonizationService()

        # Check potential matches
        matches = harmonizer.find_potential_matches(report, max_distance_meters=100)
        assert matches.count() == 1
        assert matches.first() == hospital

        # Execute Auto-Link
        linked_asset, is_linked = harmonizer.harmonize_report(
            report, auto_link=True, threshold_meters=50
        )

        # Verify Linkage
        assert is_linked is True
        assert linked_asset == hospital

        # Verify Database State
        report.refresh_from_db()
        assert report.infrastructure_asset == hospital
