from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.measure import D
from django.contrib.postgres.search import TrigramSimilarity
from django.db.models import QuerySet

from apps.infrastructure.models import InfrastructureAsset
from apps.reports.models import Report


class HarmonizationService:
    """
    Service to harmonize citizen reports with official infrastructure assets.
    """

    def find_potential_matches(
        self,
        report: Report,
        max_distance_meters: float = 100.0,
        match_type: bool = True,
        use_name_similarity: bool = False,
    ) -> QuerySet[InfrastructureAsset]:
        """
        Find potential official assets matching a citizen report.

        Args:
            report: The citizen report to match.
            max_distance_meters: Maximum distance to search (default 100m).
            match_type: Whether to filter by matching infrastructure type (default True).
            use_name_similarity: Whether to rank by name similarity to report description (default False).

        Returns:
            QuerySet of InfrastructureAsset, ordered by proximity.
        """
        if not report.location:
            return InfrastructureAsset.objects.none()

        # Base query: active assets within distance
        candidates = (
            InfrastructureAsset.objects.filter(is_active=True)
            .annotate(distance=Distance("location", report.location))
            .filter(distance__lte=D(m=max_distance_meters))
        )

        # Filter by type if requested and report has a type
        if match_type and report.infrastructure_type:
            candidates = candidates.filter(asset_type=report.infrastructure_type)

        # Name similarity (Trigram)
        # Note: Report description is used as a proxy for name since reports don't have a name field.
        if use_name_similarity and report.description:
            candidates = candidates.annotate(
                similarity=TrigramSimilarity("official_name", report.description)
            ).order_by("-similarity", "distance")
        else:
            # Order by closest
            candidates = candidates.order_by("distance")

        return candidates

    def harmonize_report(
        self, report: Report, auto_link: bool = False, threshold_meters: float = 50.0
    ) -> tuple[InfrastructureAsset | None, bool]:
        """
        Attempt to harmonize a single report.

        Args:
            report: The report to process.
            auto_link: If True, automatically link the report to the best match if very close.
            threshold_meters: Distance threshold for auto-linking.

        Returns:
            Tuple (Matched Asset or None, Boolean indicating if linked)
        """
        matches = self.find_potential_matches(report, max_distance_meters=100.0)
        best_match = matches.first()

        if not best_match:
            return None, False

        # If auto-link enabled and match is within strict threshold
        if auto_link and best_match.distance.m <= threshold_meters:  # type: ignore
            report.infrastructure_asset = best_match
            report.save(update_fields=["infrastructure_asset", "updated_at"])
            return best_match, True

        return best_match, False
