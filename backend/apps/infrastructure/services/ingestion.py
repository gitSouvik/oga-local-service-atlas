import json
from typing import Any

from django.contrib.gis.geos import GEOSGeometry

from apps.core.models import DataSourceType
from apps.geography.models import GeographicArea
from apps.infrastructure.models import AssetType, InfrastructureAsset


class IngestionError(Exception):
    """Raised when ingestion fails."""

    pass


class InfrastructureIngester:
    """
    Service for ingesting official infrastructure datasets.
    Handles GeoJSON parsing, normalization, and database persistence.
    """

    def __init__(
        self,
        data_owner: str,
        license: str,
        source_url: str = "",
        update_frequency: str = "Unknown",
        default_area: GeographicArea | None = None,
    ):
        self.data_owner = data_owner
        self.license = license
        self.source_url = source_url
        self.update_frequency = update_frequency
        self.default_area = default_area

    def ingest_geojson(
        self, geojson_data: dict[str, Any], mapping: dict[str, str]
    ) -> list[InfrastructureAsset]:
        """
        Ingest a GeoJSON FeatureCollection.

        Args:
            geojson_data: Parsed GeoJSON dictionary.
            mapping: Dictionary mapping internal model fields to source properties.
                     e.g., {"official_name": "NAME", "asset_type": "TYPE"}

        Returns:
            List of created InfrastructureAsset instances.
        """
        created_assets = []
        features = geojson_data.get("features", [])

        # Pre-fetch or cache areas if needed?
        # For now, per-feature lookup is fine for small datasets.

        for feature in features:
            try:
                asset = self._process_feature(feature, mapping)
                if asset:
                    created_assets.append(asset)
            except Exception as e:
                # Log error and continue?
                print(f"Failed to process feature: {e}")
                continue

        return created_assets

    def _process_feature(
        self, feature: dict[str, Any], mapping: dict[str, str]
    ) -> InfrastructureAsset | None:
        properties = feature.get("properties", {})
        geometry = feature.get("geometry")

        if not geometry:
            return None

        # Parse geometry
        try:
            geom_json = json.dumps(geometry)
            geom = GEOSGeometry(geom_json)

            # Ensure we have a Point
            if geom.geom_type != "Point":
                geom = geom.centroid
        except Exception:
            return None

        # Extract fields based on mapping
        source_type_field = mapping.get("asset_type")
        raw_type = properties.get(source_type_field) if source_type_field else None
        asset_type = self._normalize_asset_type(raw_type)

        source_name_field = mapping.get("official_name")
        official_name = properties.get(source_name_field) if source_name_field else "Unknown Asset"

        # Resolve GeographicArea
        # Strategy: Find the smallest administrative area that contains this point.
        # Order by admin_level descending (e.g., Ward -> District -> State -> Country)
        area = None

        # Try spatial lookup first
        spatial_areas = GeographicArea.objects.filter(
            geometry__covers=geom, is_active=True
        ).order_by("-admin_level")

        if spatial_areas.exists():
            area = spatial_areas.first()
        elif self.default_area:
            area = self.default_area
        else:
            # If no area found and no default, we cannot link it.
            # In Phase 1.3, GeographicArea is required.
            # We skip this asset or log a warning.
            return None

        # Create Asset
        asset = InfrastructureAsset(
            asset_type=asset_type,
            official_name=official_name,
            location=geom,
            geographic_area=area,
            data_owner=self.data_owner,
            license=self.license,
            source_url=self.source_url,
            update_frequency=self.update_frequency,
            source_metadata=properties,
            data_source=DataSourceType.OFFICIAL,
            is_verified=True,  # Official data is trusted by default
            is_active=True,
        )
        asset.save()
        return asset

    def _normalize_asset_type(self, raw_type: str | None) -> str:
        """
        Normalize raw source types to internal AssetType choices.
        This uses simple heuristics; could be enhanced with fuzzy matching or a lookup dict.
        """
        if not raw_type:
            return AssetType.OTHER

        raw = str(raw_type).lower()

        if "school" in raw or "education" in raw:
            return AssetType.SCHOOL
        if "clinic" in raw or "health" in raw or "hospital" in raw:
            if "hospital" in raw:
                return AssetType.HOSPITAL
            return AssetType.CLINIC
        if "water" in raw:
            if "borehole" in raw:
                return AssetType.BOREHOLE
            return AssetType.WATER_POINT
        if "road" in raw:
            return AssetType.ROAD
        if "bridge" in raw:
            return AssetType.BRIDGE
        if "market" in raw:
            return AssetType.MARKET
        if "electricity" in raw or "power" in raw:
            return AssetType.ELECTRICITY
        if "sanitation" in raw or "toilet" in raw:
            return AssetType.SANITATION
        if "gov" in raw or "office" in raw:
            return AssetType.GOVERNMENT_OFFICE

        return AssetType.OTHER
