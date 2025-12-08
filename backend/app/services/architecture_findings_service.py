"""Architecture Findings Service.

Handles persistence of architecture findings (dead code, hot spots)
to PostgreSQL database.

Requirements: 7.1, 7.2
"""

import logging
from uuid import UUID

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models.dead_code import DeadCode
from app.models.file_churn import FileChurn
from app.schemas.architecture_llm import DeadCodeFinding, HotSpotFinding, LLMReadyArchitectureData

logger = logging.getLogger(__name__)


class ArchitectureFindingsService:
    """Service for persisting architecture findings to PostgreSQL.

    Handles:
    - Dead code findings from call graph analysis
    - Hot spot findings from git churn analysis

    Requirements: 7.1, 7.2
    """

    def persist_findings(
        self,
        db: Session,
        repository_id: UUID,
        analysis_id: UUID,
        architecture_data: LLMReadyArchitectureData,
    ) -> dict:
        """Persist architecture findings to PostgreSQL.

        Clears existing findings for the analysis and inserts new ones.

        Args:
            db: Database session
            repository_id: UUID of the repository
            analysis_id: UUID of the analysis
            architecture_data: LLM-ready architecture data with findings

        Returns:
            Dict with counts of persisted findings

        Requirements: 7.1, 7.2
        """
        # Clear existing findings for this analysis
        self._clear_existing_findings(db, analysis_id)

        # Persist dead code findings
        dead_code_count = self._persist_dead_code(
            db=db,
            repository_id=repository_id,
            analysis_id=analysis_id,
            findings=architecture_data.dead_code,
        )

        # Persist hot spot findings
        hot_spot_count = self._persist_hot_spots(
            db=db,
            repository_id=repository_id,
            analysis_id=analysis_id,
            findings=architecture_data.hot_spots,
        )

        db.commit()

        logger.info(
            f"Persisted {dead_code_count} dead code and {hot_spot_count} hot spot "
            f"findings for analysis {analysis_id}"
        )

        return {
            "dead_code_count": dead_code_count,
            "hot_spot_count": hot_spot_count,
        }

    def _clear_existing_findings(self, db: Session, analysis_id: UUID) -> None:
        """Clear existing findings for an analysis.

        Args:
            db: Database session
            analysis_id: UUID of the analysis
        """
        db.execute(delete(DeadCode).where(DeadCode.analysis_id == analysis_id))
        db.execute(delete(FileChurn).where(FileChurn.analysis_id == analysis_id))

    def _persist_dead_code(
        self,
        db: Session,
        repository_id: UUID,
        analysis_id: UUID,
        findings: list[DeadCodeFinding],
    ) -> int:
        """Persist dead code findings to database.

        Args:
            db: Database session
            repository_id: UUID of the repository
            analysis_id: UUID of the analysis
            findings: List of dead code findings

        Returns:
            Number of findings persisted

        Requirements: 7.1
        """
        for finding in findings:
            dead_code = DeadCode(
                analysis_id=analysis_id,
                repository_id=repository_id,
                file_path=finding.file_path,
                function_name=finding.function_name,
                line_start=finding.line_start,
                line_end=finding.line_end,
                line_count=finding.line_count,
                confidence=finding.confidence,
                evidence=finding.evidence,
                suggested_action=finding.suggested_action,
            )
            db.add(dead_code)

        return len(findings)

    def _persist_hot_spots(
        self,
        db: Session,
        repository_id: UUID,
        analysis_id: UUID,
        findings: list[HotSpotFinding],
    ) -> int:
        """Persist hot spot findings to database.

        Args:
            db: Database session
            repository_id: UUID of the repository
            analysis_id: UUID of the analysis
            findings: List of hot spot findings

        Returns:
            Number of findings persisted

        Requirements: 7.2
        """
        for finding in findings:
            file_churn = FileChurn(
                analysis_id=analysis_id,
                file_path=finding.file_path,
                changes_90d=finding.churn_count,
                coverage_rate=finding.coverage_rate,
                unique_authors=finding.unique_authors,
                risk_factors=finding.risk_factors,
                suggested_action=finding.suggested_action,
            )
            db.add(file_churn)

        return len(findings)


def get_architecture_findings_service() -> ArchitectureFindingsService:
    """Get architecture findings service instance."""
    return ArchitectureFindingsService()
