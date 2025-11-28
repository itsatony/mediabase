"""ClinicalTrials.gov API integration module for Cancer Transcriptome Base.

This module integrates clinical trial data from ClinicalTrials.gov
to enhance transcript records with trial-based publication references.
"""

# Standard library imports
import json
import time
import re
from pathlib import Path
from typing import Dict, List, Optional, Any, Set, Tuple
from datetime import datetime, timedelta

# Third party imports
import requests
from tqdm import tqdm
from rich.console import Console
from rich.table import Table

# Local imports
from .base_processor import BaseProcessor, DownloadError, ProcessingError, DatabaseError
from .publications import Publication, PublicationsProcessor
from ..utils.publication_utils import (
    extract_pmids_from_text,
    extract_clinical_trial_ids_from_text,
    format_pmid_url,
    format_publication_url,
)
from ..utils.logging import get_progress_bar

# Constants
CLINICAL_TRIALS_API_BASE = "https://clinicaltrials.gov/api/v2"
CLINICAL_TRIALS_API_VERSION = "2.0.0"
DEFAULT_RATE_LIMIT = 1.0  # 1 request per second
MAX_RESULTS_PER_REQUEST = 1000
CANCER_RELATED_CONDITIONS = [
    "cancer",
    "carcinoma",
    "tumor",
    "tumour",
    "neoplasm",
    "malignancy",
    "sarcoma",
    "lymphoma",
    "leukemia",
    "melanoma",
    "glioma",
    "adenocarcinoma",
    "oncology",
    "metastasis",
    "chemotherapy",
    "radiation therapy",
]


class ClinicalTrialsProcessor(BaseProcessor):
    """Process clinical trial data from ClinicalTrials.gov and integrate with transcript data."""

    def __init__(self, config: Dict[str, Any]) -> None:
        """Initialize ClinicalTrials processor with configuration.

        Args:
            config: Configuration dictionary containing settings for ClinicalTrials processing
        """
        super().__init__(config)

        # Create ClinicalTrials-specific directory
        self.clinical_trials_dir = self.cache_dir / "clinical_trials"
        self.clinical_trials_dir.mkdir(exist_ok=True)

        # API configuration
        self.api_base_url = config.get(
            "clinical_trials_api_base", CLINICAL_TRIALS_API_BASE
        )
        self.rate_limit = config.get("clinical_trials_rate_limit", DEFAULT_RATE_LIMIT)
        self.max_results = config.get(
            "clinical_trials_max_results", MAX_RESULTS_PER_REQUEST
        )

        # Processing options
        self.cancer_only = config.get("clinical_trials_cancer_only", True)
        self.include_completed_only = config.get(
            "clinical_trials_completed_only", False
        )
        self.max_age_years = config.get("clinical_trials_max_age_years", 10)
        self.include_phase_0 = config.get("clinical_trials_include_phase_0", False)

        # Cache TTL
        self.cache_ttl = config.get(
            "clinical_trials_cache_ttl", 7 * 24 * 60 * 60
        )  # 7 days

        # Track API usage
        self.api_requests_made = 0
        self.last_request_time = 0

    def _make_api_request(
        self, endpoint: str, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Make a rate-limited API request to ClinicalTrials.gov.

        Args:
            endpoint: API endpoint (e.g., 'studies')
            params: Query parameters

        Returns:
            API response as dictionary

        Raises:
            DownloadError: If API request fails
        """
        # Rate limiting
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.rate_limit:
            time.sleep(self.rate_limit - time_since_last)

        url = f"{self.api_base_url}/{endpoint}"

        try:
            # Add standard parameters
            params.update({"format": "json", "countTotal": "true"})

            self.logger.debug(f"Making API request to {url} with params: {params}")

            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()

            self.api_requests_made += 1
            self.last_request_time = time.time()

            return response.json()

        except requests.exceptions.RequestException as e:
            raise DownloadError(
                f"ClinicalTrials.gov API request failed for {endpoint}: {e}"
            )
        except json.JSONDecodeError as e:
            raise DownloadError(
                f"Invalid JSON response from ClinicalTrials.gov API: {e}"
            )

    def search_trials_by_gene(self, gene_symbol: str) -> List[Dict[str, Any]]:
        """Search for clinical trials mentioning a specific gene.

        Args:
            gene_symbol: Gene symbol to search for

        Returns:
            List of trial records
        """
        try:
            # Build search query
            search_terms = [gene_symbol]

            # Add cancer-related filters if enabled
            if self.cancer_only:
                # Use condition search for cancer-related trials
                cancer_condition = " OR ".join(
                    [f'"{condition}"' for condition in CANCER_RELATED_CONDITIONS[:5]]
                )

                params = {
                    "query.term": f'"{gene_symbol}"',
                    "query.cond": cancer_condition,
                    "query.titles": f'"{gene_symbol}"',
                    "query.intr": f'"{gene_symbol}"',
                    "pageSize": min(self.max_results, 1000),
                    "countTotal": "true",
                }
            else:
                params = {
                    "query.term": f'"{gene_symbol}"',
                    "pageSize": min(self.max_results, 1000),
                    "countTotal": "true",
                }

            # Add study status filters
            if self.include_completed_only:
                params["query.status"] = "COMPLETED"
            else:
                params[
                    "query.status"
                ] = "COMPLETED,ACTIVE_NOT_RECRUITING,RECRUITING,ENROLLING_BY_INVITATION"

            # Add date range filter
            if self.max_age_years:
                start_date = datetime.now() - timedelta(days=self.max_age_years * 365)
                params["query.start"] = start_date.strftime("%Y-%m-%d")

            # Make API request
            response = self.search_studies(params)

            trials = []
            for study in response.get("studies", []):
                trial_data = self._extract_trial_data(study, gene_symbol)
                if trial_data:
                    trials.append(trial_data)

            self.logger.debug(f"Found {len(trials)} trials for gene {gene_symbol}")
            return trials

        except Exception as e:
            self.logger.warning(f"Failed to search trials for gene {gene_symbol}: {e}")
            return []

    def search_studies(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Search studies using the ClinicalTrials.gov API.

        Args:
            params: Search parameters

        Returns:
            API response containing studies
        """
        return self._make_api_request("studies", params)

    def _extract_trial_data(
        self, study: Dict[str, Any], gene_symbol: str
    ) -> Optional[Dict[str, Any]]:
        """Extract relevant data from a clinical trial study record.

        Args:
            study: Study record from API response
            gene_symbol: Gene symbol being searched

        Returns:
            Extracted trial data or None if not relevant
        """
        try:
            protocol_section = study.get("protocolSection", {})
            identification_module = protocol_section.get("identificationModule", {})
            status_module = protocol_section.get("statusModule", {})
            design_module = protocol_section.get("designModule", {})
            conditions_module = protocol_section.get("conditionsModule", {})
            interventions_module = protocol_section.get("armsInterventionsModule", {})

            # Extract basic information
            nct_id = identification_module.get("nctId", "")
            title = identification_module.get("briefTitle", "")
            official_title = identification_module.get("officialTitle", "")

            if not nct_id:
                return None

            # Extract study phase
            phases = design_module.get("phases", [])
            phase = phases[0] if phases else "Not Applicable"

            # Skip Phase 0 if not included
            if not self.include_phase_0 and phase == "EARLY_PHASE1":
                return None

            # Extract conditions
            conditions = conditions_module.get("conditions", [])

            # Check if cancer-related (if filtering enabled)
            if self.cancer_only:
                is_cancer_related = any(
                    any(
                        cancer_term.lower() in condition.lower()
                        for cancer_term in CANCER_RELATED_CONDITIONS
                    )
                    for condition in conditions
                )
                if not is_cancer_related:
                    return None

            # Extract interventions
            interventions = []
            for intervention in interventions_module.get("interventions", []):
                interventions.append(
                    {
                        "type": intervention.get("type", ""),
                        "name": intervention.get("name", ""),
                        "description": intervention.get("description", ""),
                    }
                )

            # Extract study status and dates
            status = status_module.get("overallStatus", "")
            start_date = status_module.get("startDateStruct", {}).get("date", "")
            completion_date = status_module.get("completionDateStruct", {}).get(
                "date", ""
            )

            # Extract sponsor information
            sponsor_module = protocol_section.get("sponsorCollaboratorsModule", {})
            lead_sponsor = sponsor_module.get("leadSponsor", {}).get("name", "")

            # Extract outcome measures
            outcomes_module = protocol_section.get("outcomesModule", {})
            primary_outcomes = outcomes_module.get("primaryOutcomes", [])
            secondary_outcomes = outcomes_module.get("secondaryOutcomes", [])

            # Build trial record
            trial_data = {
                "nct_id": nct_id,
                "title": title,
                "official_title": official_title,
                "phase": self._normalize_phase(phase),
                "status": status,
                "conditions": conditions,
                "interventions": interventions,
                "start_date": start_date,
                "completion_date": completion_date,
                "lead_sponsor": lead_sponsor,
                "gene_symbol": gene_symbol,
                "primary_outcomes": len(primary_outcomes),
                "secondary_outcomes": len(secondary_outcomes),
                "url": f"https://clinicaltrials.gov/ct2/show/{nct_id}",
            }

            # Extract publications from results if available
            derived_section = study.get("derivedSection", {})
            publications = self._extract_trial_publications(derived_section, nct_id)
            if publications:
                trial_data["publications"] = publications

            return trial_data

        except Exception as e:
            self.logger.warning(f"Failed to extract trial data from study: {e}")
            return None

    def _normalize_phase(self, phase: str) -> str:
        """Normalize clinical trial phase to standard format.

        Args:
            phase: Raw phase string from API

        Returns:
            Normalized phase string
        """
        phase_mapping = {
            "EARLY_PHASE1": "Phase 0/1",
            "PHASE1": "Phase 1",
            "PHASE1_PHASE2": "Phase 1/2",
            "PHASE2": "Phase 2",
            "PHASE2_PHASE3": "Phase 2/3",
            "PHASE3": "Phase 3",
            "PHASE4": "Phase 4",
            "NOT_APPLICABLE": "Not Applicable",
        }

        return phase_mapping.get(phase, phase)

    def _extract_trial_publications(
        self, derived_section: Dict[str, Any], nct_id: str
    ) -> List[Dict[str, Any]]:
        """Extract publication references from trial results.

        Args:
            derived_section: Derived section from study record
            nct_id: Clinical trial ID

        Returns:
            List of publication references
        """
        publications = []

        try:
            # Look for publications in various sections
            misc_info = derived_section.get("miscInfoModule", {})

            # Check for version holder (sometimes contains publication info)
            version_holder = misc_info.get("versionHolder", "")
            if version_holder:
                pmids = extract_pmids_from_text(version_holder)
                for pmid in pmids:
                    publications.append(
                        {
                            "pmid": pmid,
                            "evidence_type": "clinical_trial_publication",
                            "source_db": "ClinicalTrials.gov",
                            "trial_id": nct_id,
                            "url": format_pmid_url(pmid),
                        }
                    )

            # Check for reference publications in study documents
            # Note: This would require additional API calls to get full study details
            # For now, we focus on what's available in the basic search results

        except Exception as e:
            self.logger.warning(
                f"Failed to extract publications from trial {nct_id}: {e}"
            )

        return publications

    def get_trials_for_genes(
        self, gene_symbols: List[str]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Get clinical trials for a list of genes.

        Args:
            gene_symbols: List of gene symbols to search

        Returns:
            Dictionary mapping gene symbols to their trial records
        """
        gene_trials = {}

        self.logger.info(f"Searching clinical trials for {len(gene_symbols)} genes")

        # Create progress bar
        progress_bar = get_progress_bar(
            total=len(gene_symbols),
            desc="Searching clinical trials",
            module_name="clinical_trials",
        )

        try:
            for gene_symbol in gene_symbols:
                trials = self.search_trials_by_gene(gene_symbol)
                if trials:
                    gene_trials[gene_symbol] = trials

                progress_bar.update(1)

                # Rate limiting between gene searches
                time.sleep(self.rate_limit)

        finally:
            progress_bar.close()

        self.logger.info(
            f"Found trials for {len(gene_trials)} genes, total API requests: {self.api_requests_made}"
        )
        return gene_trials

    def extract_publication_references(
        self, gene_trials: Dict[str, List[Dict[str, Any]]]
    ) -> List[Publication]:
        """Extract publication references from clinical trial data.

        Args:
            gene_trials: Dictionary mapping gene symbols to trial records

        Returns:
            List of Publication objects
        """
        publications = []
        processed_pmids = set()

        self.logger.info("Extracting publication references from clinical trial data")

        for gene_symbol, trials in gene_trials.items():
            for trial in trials:
                # Extract publications from trial if available
                trial_publications = trial.get("publications", [])

                for pub_ref in trial_publications:
                    pmid = pub_ref.get("pmid")
                    if pmid and pmid not in processed_pmids:
                        publication = {
                            "pmid": pmid,
                            "evidence_type": "clinical_trial",
                            "source_db": "ClinicalTrials.gov",
                            "gene_symbol": gene_symbol,
                            "trial_id": trial.get("nct_id"),
                            "trial_title": trial.get("title"),
                            "trial_phase": trial.get("phase"),
                            "trial_status": trial.get("status"),
                            "conditions": trial.get("conditions", []),
                            "url": pub_ref.get("url", format_pmid_url(pmid)),
                        }

                        publications.append(publication)
                        processed_pmids.add(pmid)

                # Also create a reference for the trial itself (even without specific publications)
                nct_id = trial.get("nct_id")
                if nct_id:
                    trial_ref = {
                        "clinical_trial_id": nct_id,
                        "evidence_type": "clinical_trial_record",
                        "source_db": "ClinicalTrials.gov",
                        "gene_symbol": gene_symbol,
                        "trial_title": trial.get("title"),
                        "trial_phase": trial.get("phase"),
                        "trial_status": trial.get("status"),
                        "conditions": trial.get("conditions", []),
                        "interventions": trial.get("interventions", []),
                        "start_date": trial.get("start_date"),
                        "completion_date": trial.get("completion_date"),
                        "lead_sponsor": trial.get("lead_sponsor"),
                        "url": trial.get(
                            "url", format_publication_url(nct_id, "clinical_trial")
                        ),
                    }

                    publications.append(trial_ref)

        self.logger.info(f"Extracted {len(publications)} publication/trial references")
        return publications

    def update_transcript_clinical_trial_data(
        self, gene_trials: Dict[str, List[Dict[str, Any]]]
    ) -> None:
        """Update transcript records with clinical trial data.

        Args:
            gene_trials: Dictionary mapping gene symbols to trial records

        Raises:
            DatabaseError: If database operations fail
        """
        if not self.ensure_connection():
            raise DatabaseError("Database connection failed")

        try:
            self.logger.info("Updating transcript records with clinical trial data")

            # Get all genes in database that match our clinical trial data
            if not self.db_manager.cursor:
                raise DatabaseError("No database cursor available")

            # Find genes in database that match our clinical trial data
            self.db_manager.cursor.execute(
                """
                SELECT DISTINCT gene_symbol 
                FROM cancer_transcript_base 
                WHERE gene_symbol IS NOT NULL
            """
            )

            db_genes = {row[0] for row in self.db_manager.cursor.fetchall()}
            trial_genes = set(gene_trials.keys())
            matching_genes = db_genes.intersection(trial_genes)

            self.logger.info(
                f"Found {len(matching_genes):,} genes in database that have clinical trial data"
            )

            if not matching_genes:
                self.logger.warning(
                    "No gene overlap found between database and clinical trials"
                )
                return

            # Process updates in batches
            update_data = []

            for gene_symbol in matching_genes:
                trials = gene_trials[gene_symbol]

                # Build clinical trial summary
                trial_summary = {
                    "total_trials": len(trials),
                    "phases": list(
                        set(trial.get("phase", "Unknown") for trial in trials)
                    ),
                    "statuses": list(
                        set(trial.get("status", "Unknown") for trial in trials)
                    ),
                    "conditions": list(
                        set().union(*[trial.get("conditions", []) for trial in trials])
                    ),
                    "recent_trials": len(
                        [t for t in trials if self._is_recent_trial(t)]
                    ),
                    "completed_trials": len(
                        [t for t in trials if t.get("status") == "COMPLETED"]
                    ),
                    "active_trials": len(
                        [
                            t
                            for t in trials
                            if "ACTIVE" in t.get("status", "")
                            or "RECRUITING" in t.get("status", "")
                        ]
                    ),
                }

                # Build detailed trial records (limited to most relevant)
                detailed_trials = []
                for trial in sorted(
                    trials,
                    key=lambda x: (x.get("phase", ""), x.get("start_date", "")),
                    reverse=True,
                )[:10]:
                    detailed_trials.append(
                        {
                            "nct_id": trial.get("nct_id"),
                            "title": trial.get("title", "")[
                                :200
                            ],  # Truncate long titles
                            "phase": trial.get("phase"),
                            "status": trial.get("status"),
                            "conditions": trial.get("conditions", [])[
                                :5
                            ],  # Limit conditions
                            "start_date": trial.get("start_date"),
                            "completion_date": trial.get("completion_date"),
                            "lead_sponsor": trial.get("lead_sponsor"),
                            "url": trial.get("url"),
                        }
                    )

                clinical_trial_data = {
                    "summary": trial_summary,
                    "trials": detailed_trials,
                    "last_updated": datetime.now().isoformat(),
                    "source": "ClinicalTrials.gov",
                }

                update_data.append((json.dumps(clinical_trial_data), gene_symbol))

            # Execute batch update
            self.logger.info(
                f"Updating {len(update_data):,} transcript records with clinical trial data"
            )

            try:
                self.db_manager.cursor.executemany(
                    """
                    UPDATE cancer_transcript_base 
                    SET clinical_trials = %s::jsonb
                    WHERE gene_symbol = %s
                """,
                    update_data,
                )

                if self.db_manager.conn:
                    self.db_manager.conn.commit()
            except Exception as e:
                if self.db_manager.conn:
                    self.db_manager.conn.rollback()
                raise e

            # Verify updates
            self.db_manager.cursor.execute(
                """
                SELECT COUNT(*) 
                FROM cancer_transcript_base 
                WHERE clinical_trials IS NOT NULL
                  AND clinical_trials != '{}'::jsonb
            """
            )

            updated_count = self.db_manager.cursor.fetchone()[0]
            self.logger.info(
                f"Successfully updated {updated_count:,} records with clinical trial data"
            )

        except Exception as e:
            raise DatabaseError(f"Failed to update transcript clinical trial data: {e}")

    def _is_recent_trial(self, trial: Dict[str, Any]) -> bool:
        """Check if a trial is recent based on start date.

        Args:
            trial: Trial record

        Returns:
            True if trial is recent
        """
        try:
            start_date_str = trial.get("start_date", "")
            if not start_date_str:
                return False

            # Parse date (format: YYYY-MM-DD or YYYY-MM or YYYY)
            if len(start_date_str) >= 4:
                year = int(start_date_str[:4])
                current_year = datetime.now().year
                return (current_year - year) <= self.max_age_years

            return False
        except (ValueError, TypeError):
            return False

    def run(self) -> None:
        """Run the complete ClinicalTrials.gov integration pipeline.

        Steps:
        1. Get genes from database
        2. Search for clinical trials for each gene
        3. Extract publication references
        4. Update transcript records with trial data
        5. Process publications through publications processor
        """
        try:
            self.logger.info("Starting ClinicalTrials.gov integration pipeline")

            # Ensure database connection
            if not self.ensure_connection():
                raise DatabaseError("Database connection failed")

            # Get sample of genes from database for trial search
            # In production, you might want to be more selective
            self.db_manager.cursor.execute(
                """
                SELECT DISTINCT gene_symbol 
                FROM cancer_transcript_base 
                WHERE gene_symbol IS NOT NULL
                  AND gene_type = 'protein_coding'
                ORDER BY gene_symbol
                LIMIT 100  -- Limit for demonstration
            """
            )

            gene_symbols = [row[0] for row in self.db_manager.cursor.fetchall()]
            self.logger.info(f"Searching clinical trials for {len(gene_symbols)} genes")

            # Search for clinical trials
            gene_trials = self.get_trials_for_genes(gene_symbols)

            if not gene_trials:
                self.logger.warning("No clinical trials found for any genes")
                return

            # Extract publication references
            publications = self.extract_publication_references(gene_trials)

            # Process publications through publications processor
            if publications:
                trial_publications = [pub for pub in publications if pub.get("pmid")]
                if trial_publications:
                    self.logger.info(
                        f"Processing {len(trial_publications)} clinical trial publication references"
                    )
                    publications_processor = PublicationsProcessor(self.config)
                    publications_processor.enrich_publications_bulk(trial_publications)

            # Update transcript records with clinical trial data
            self.update_transcript_clinical_trial_data(gene_trials)

            self.logger.info("ClinicalTrials.gov integration completed successfully")

        except Exception as e:
            self.logger.error(f"ClinicalTrials.gov integration failed: {e}")
            raise
