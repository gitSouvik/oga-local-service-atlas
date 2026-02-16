from django.contrib.gis.geos import MultiPolygon, Point
from django.test import TestCase

from apps.geography.models import GeographicArea
from apps.infrastructure.models import AssetType, InfrastructureAsset
from apps.reports.models import Report
from apps.reports.services.harmonization import HarmonizationService


class HarmonizationServiceTests(TestCase):
    def setUp(self):
        # Create a test area
        poly = Point(5.0, 5.0).buffer(1.0)  # Buffer creates a polygon
        multipoly = MultiPolygon(poly)

        self.area = GeographicArea.objects.create(
            name="Test Area", country_code="NGA", admin_level="state", geometry=multipoly
        )
        # Create an official asset at (5.0, 5.0)
        self.asset = InfrastructureAsset.objects.create(
            official_name="Official School",
            asset_type=AssetType.SCHOOL,
            location=Point(5.0, 5.0),
            geographic_area=self.area,
            is_active=True,
        )
        self.service = HarmonizationService()

    def test_find_matching_asset_close(self):
        # Create a report very close to the asset (e.g., 10m away)
        # 0.0001 degrees is roughly 11m
        report = Report.objects.create(
            description="School issue",
            location=Point(5.0001, 5.0),
            infrastructure_type=AssetType.SCHOOL,
            reported_status="working",
            reporter_type="citizen",
        )

        matches = self.service.find_potential_matches(report, max_distance_meters=100)
        self.assertEqual(matches.count(), 1)
        self.assertEqual(matches.first(), self.asset)

    def test_find_matching_asset_far(self):
        # Create a report far away (e.g., 0.1 degrees ~11km)
        report = Report.objects.create(
            description="Far away issue",
            location=Point(5.1, 5.0),
            infrastructure_type=AssetType.SCHOOL,
            reported_status="working",
            reporter_type="citizen",
        )

        matches = self.service.find_potential_matches(report, max_distance_meters=100)
        self.assertEqual(matches.count(), 0)

    def test_find_matching_asset_name_similarity(self):
        # Create an asset with a specific name
        named_asset = InfrastructureAsset.objects.create(
            official_name="Lagos Central Hospital",
            asset_type=AssetType.HOSPITAL,
            location=Point(5.0, 5.0),
            geographic_area=self.area,
            is_active=True,
        )

        # Create a report with a description containing the name
        report = Report.objects.create(
            description="Lagos Central Hospital has no power",
            location=Point(5.0001, 5.0),
            infrastructure_type=AssetType.HOSPITAL,
            reported_status="working",
            reporter_type="citizen",
        )

        matches = self.service.find_potential_matches(
            report, max_distance_meters=100, use_name_similarity=True
        )

        # Should be ranked first
        self.assertEqual(matches.first(), named_asset)
        # Check if similarity annotation exists (it should be > 0)
        self.assertTrue(hasattr(matches.first(), "similarity"))
        report = Report.objects.create(
            description="Auto link issue",
            location=Point(5.00005, 5.0),  # ~5.5m
            infrastructure_type=AssetType.SCHOOL,
            reported_status="working",
            reporter_type="citizen",
        )

        asset, linked = self.service.harmonize_report(report, auto_link=True, threshold_meters=50)

        self.assertTrue(linked)
        self.assertEqual(asset, self.asset)

        report.refresh_from_db()
        self.assertEqual(report.infrastructure_asset, self.asset)

    def test_harmonize_report_no_auto_link_if_far(self):
        # Create a report slightly outside threshold (e.g., 60m away)
        # 0.0006 degrees ~66m
        report = Report.objects.create(
            description="No auto link issue",
            location=Point(5.0006, 5.0),
            infrastructure_type=AssetType.SCHOOL,
            reported_status="working",
            reporter_type="citizen",
        )

        asset, linked = self.service.harmonize_report(report, auto_link=True, threshold_meters=50)

        self.assertFalse(linked)
        # It might still find a match candidate, but won't link it
        # Wait, my logic returns (best_match, False) if candidates exist but threshold not met.
        # Let's check what find_potential_matches returns. Default is 100m.
        # 66m is < 100m, so it finds a match.
        self.assertEqual(asset, self.asset)

        report.refresh_from_db()
        self.assertIsNone(report.infrastructure_asset)
