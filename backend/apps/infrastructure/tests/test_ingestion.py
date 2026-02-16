from django.contrib.gis.geos import MultiPolygon
from django.test import TestCase

from apps.geography.models import GeographicArea
from apps.infrastructure.models import AssetType
from apps.infrastructure.services.ingestion import InfrastructureIngester


class InfrastructureIngesterTests(TestCase):
    def setUp(self):
        # Create a test area covering (0,0) to (10,10)
        # Assuming Polygon for simplicity, or just an area we can link to.
        # Since ingestion logic does a spatial lookup, we need a valid area.
        # Let's create a dummy area with a polygon covering our points.
        from django.contrib.gis.geos import Polygon

        poly = Polygon.from_bbox((0, 0, 10, 10))
        multipoly = MultiPolygon(poly)

        self.area = GeographicArea.objects.create(
            name="Test Area", country_code="NGA", admin_level="state", geometry=multipoly
        )
        self.ingester = InfrastructureIngester(
            data_owner="Ministry of Health", license="Open Data", update_frequency="Annual"
        )

    def test_ingest_valid_geojson(self):
        geojson_data = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [5.0, 5.0]},
                    "properties": {"Name": "Central Hospital", "Type": "Hospital", "Capacity": 100},
                }
            ],
        }

        mapping = {"official_name": "Name", "asset_type": "Type"}

        assets = self.ingester.ingest_geojson(geojson_data, mapping)

        self.assertEqual(len(assets), 1)
        asset = assets[0]
        self.assertEqual(asset.official_name, "Central Hospital")
        self.assertEqual(
            asset.asset_type, AssetType.HOSPITAL
        )  # Should normalize 'Hospital' -> 'hospital' or 'clinic' depending on logic
        self.assertEqual(asset.data_owner, "Ministry of Health")
        self.assertEqual(asset.source_metadata["Capacity"], 100)
        self.assertEqual(asset.geographic_area, self.area)

    def test_ingest_outside_area(self):
        # Point outside (0,0,10,10)
        geojson_data = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [20.0, 20.0]},
                    "properties": {"Name": "Far Away Clinic", "Type": "Clinic"},
                }
            ],
        }
        mapping = {"official_name": "Name", "asset_type": "Type"}

        assets = self.ingester.ingest_geojson(geojson_data, mapping)
        self.assertEqual(len(assets), 0)
