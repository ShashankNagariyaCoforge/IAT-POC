"""Pydantic v2 models for enrichment data extracted via web crawling."""

from typing import Optional, List
from pydantic import BaseModel, Field


class EnrichedField(BaseModel):
    """A single enriched field with value, confidence, and source URL."""
    value: Optional[str] = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source: Optional[str] = None  # URL where the value was found


class EnrichmentResult(BaseModel):
    """Result of the enrichment pipeline — fields extracted from web crawling + AI."""

    # Core entity fields
    entity_type: Optional[EnrichedField] = None
    naics_code: Optional[EnrichedField] = None
    entity_structure: Optional[EnrichedField] = None
    years_in_business: Optional[EnrichedField] = None
    number_of_employees: Optional[EnrichedField] = None
    territory_code: Optional[EnrichedField] = None

    # Insurance-specific fields
    limit_of_liability: Optional[EnrichedField] = None
    deductible: Optional[EnrichedField] = None
    class_mass_action_deductible_retention: Optional[EnrichedField] = None
    pending_or_prior_litigation_date: Optional[EnrichedField] = None
    duty_to_defend_limit: Optional[EnrichedField] = None
    defense_outside_limit: Optional[EnrichedField] = None

    # Employment fields
    employment_category: Optional[EnrichedField] = None
    ec_number_of_employees: Optional[EnrichedField] = None
    employee_compensation: Optional[EnrichedField] = None
    number_of_employees_in_each_band: Optional[EnrichedField] = None
    employee_location: Optional[EnrichedField] = None
    number_of_employees_in_each_location: Optional[EnrichedField] = None

    # Metadata
    source_urls: List[str] = Field(default_factory=list)
    company_name: Optional[str] = None
    website: Optional[str] = None
    enrichment_status: str = "completed"

    # All extractable field keys for iteration
    @classmethod
    def field_keys(cls) -> List[str]:
        """Return the list of extractable field names (excludes metadata)."""
        return [
            "entity_type", "naics_code", "entity_structure",
            "years_in_business", "number_of_employees", "territory_code",
            "limit_of_liability", "deductible",
            "class_mass_action_deductible_retention",
            "pending_or_prior_litigation_date", "duty_to_defend_limit",
            "defense_outside_limit", "employment_category",
            "ec_number_of_employees", "employee_compensation",
            "number_of_employees_in_each_band", "employee_location",
            "number_of_employees_in_each_location",
        ]
