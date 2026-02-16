from django.contrib.gis.geos import MultiPolygon, Point, Polygon
from django.core.management.base import BaseCommand

from apps.geography.models import GeographicArea
from apps.infrastructure.models import AssetType, InfrastructureAsset
from apps.infrastructure.services.ingestion import InfrastructureIngester
from apps.reports.models import Report
from apps.reports.services.harmonization import HarmonizationService


class Command(BaseCommand):
    help = "Demonstrates Phase 2 Ingestion and Harmonization features"

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("=== Starting Phase 2 Demo ==="))

        # 1. Setup Area
        self.stdout.write("1. Setting up Geographic Area...")
        # Clear existing demo data to avoid duplicates if run multiple times
        # Delete dependent assets first due to PROTECT
        InfrastructureAsset.objects.filter(geographic_area__name="Demo State").delete()
        GeographicArea.objects.filter(name="Demo State").delete()

        poly = Polygon.from_bbox((0, 0, 10, 10))
        multipoly = MultiPolygon(poly)
        area = GeographicArea.objects.create(
            name="Demo State", country_code="NGA", admin_level="state", geometry=multipoly
        )
        self.stdout.write(f"   Created Area: {area.name}")

        # 2. Ingestion
        self.stdout.write("\n2. Ingesting Official Data...")
        ingester = InfrastructureIngester(
            data_owner="Ministry of Health",
            license="Open Data",
            source_url="http://example.com/data.json",
        )

        geojson_data = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [5.0, 5.0]},
                    "properties": {
                        "OfficialName": "Central Hospital",
                        "Category": "Hospital",
                        "Beds": 100,
                    },
                },
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [2.0, 2.0]},
                    "properties": {"OfficialName": "Rural Clinic", "Category": "Clinic"},
                },
            ],
        }
        mapping = {"official_name": "OfficialName", "asset_type": "Category"}

        assets = ingester.ingest_geojson(geojson_data, mapping)
        self.stdout.write(f"   Ingested {len(assets)} assets:")
        for asset in assets:
            self.stdout.write(
                f"   - {asset.official_name} ({asset.asset_type}) at {asset.location}"
            )

        # 3. Create Report
        self.stdout.write("\n3. Creating Citizen Report...")
        # Report is very close to Central Hospital (5.0, 5.0)
        report_loc = Point(5.0001, 5.0001)
        report = Report.objects.create(
            description="Power outage at the hospital",
            location=report_loc,
            infrastructure_type=AssetType.HOSPITAL,
            reported_status="working",
        )
        self.stdout.write(f"   Created Report: '{report.description}' at {report.location}")

        # 4. Harmonization
        self.stdout.write("\n4. Running Harmonization...")
        service = HarmonizationService()

        # Check potential matches
        matches = service.find_potential_matches(report, max_distance_meters=100)
        self.stdout.write(f"   Found {matches.count()} potential matches within 100m.")

        # Auto-link
        match, linked = service.harmonize_report(report, auto_link=True, threshold_meters=50)

        if linked and match:
            self.stdout.write(
                self.style.SUCCESS(
                    f"   SUCCESS: Report automatically linked to: {match.official_name}"
                )
            )
        else:
            self.stdout.write(self.style.WARNING("   No auto-link established."))

        # Verify DB
        report.refresh_from_db()
        if report.infrastructure_asset:
            self.stdout.write(
                f"   DB Verification: Report.infrastructure_asset_id = {report.infrastructure_asset.id}"
            )

        self.stdout.write(self.style.SUCCESS("\n=== Demo Complete ==="))
