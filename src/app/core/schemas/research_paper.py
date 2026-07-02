from dataclasses import dataclass

@dataclass
class ResearchPaper:
    """
    Provides the schema for a research paper and its associated metadata.
    """
    pmid: str
    title: str
    year: str
    has_full_text: bool
    pmcid: str | None = None
    doi: str | None = None
    abstract: str | None = None
    full_text: str | None = None
    full_text_source: str | None = None