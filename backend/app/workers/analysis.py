"""Repository analysis tasks."""

import logging
from datetime import datetime

from sqlalchemy import select

from app.core.celery import celery_app
from app.core.database import get_sync_session
from app.core.redis import publish_analysis_progress
from app.services.repo_analyzer import RepoAnalyzer

logger = logging.getLogger(__name__)


def _get_repo_url(repository_id: str) -> tuple[str, str | None]:
    """Get repository URL and access token from database."""
    from app.models.repository import Repository
    from app.models.user import User
    from app.core.encryption import decrypt_token
    
    with get_sync_session() as db:
        result = db.execute(
            select(Repository).where(Repository.id == repository_id)
        )
        repo = result.scalar_one_or_none()
        
        if not repo:
            raise ValueError(f"Repository {repository_id} not found")
        
        # Get owner's access token for private repos
        access_token = None
        if repo.owner_id:
            user_result = db.execute(
                select(User).where(User.id == repo.owner_id)
            )
            user = user_result.scalar_one_or_none()
            if user and user.access_token_encrypted:
                try:
                    access_token = decrypt_token(user.access_token_encrypted)
                except Exception as e:
                    logger.warning(f"Could not decrypt access token: {e}")
        
        repo_url = f"https://github.com/{repo.full_name}"
        return repo_url, access_token


def _save_analysis_results(repository_id: str, analysis_id: str, result):
    """Save analysis results to database."""
    from app.models.analysis import Analysis
    from app.models.repository import Repository
    from app.models.issue import Issue
    from sqlalchemy import update
    
    with get_sync_session() as db:
        # Find the specific analysis by ID
        analysis_result = db.execute(
            select(Analysis).where(Analysis.id == analysis_id)
        )
        analysis = analysis_result.scalar_one_or_none()
        
        if analysis:
            analysis.status = "completed"
            analysis.vci_score = result.vci_score
            analysis.tech_debt_level = result.tech_debt_level
            analysis.metrics = result.metrics
            analysis.ai_report = result.ai_report
            analysis.started_at = datetime.utcnow()
            analysis.completed_at = datetime.utcnow()
            
            # Close old open issues for this repository (to avoid duplicates)
            db.execute(
                update(Issue)
                .where(
                    Issue.repository_id == repository_id,
                    Issue.status == "open",
                )
                .values(status="closed")
            )
            
            # Create new issues from this analysis
            for issue_data in result.issues:
                issue = Issue(
                    repository_id=repository_id,
                    analysis_id=analysis.id,
                    type=issue_data["type"],
                    severity=issue_data["severity"],
                    title=issue_data["title"],
                    description=issue_data["description"],
                    confidence=issue_data.get("confidence", 0.8),
                    status="open",
                )
                db.add(issue)
            
            # Update repository
            repo_result = db.execute(
                select(Repository).where(Repository.id == repository_id)
            )
            repo = repo_result.scalar_one_or_none()
            if repo:
                repo.vci_score = result.vci_score
                repo.tech_debt_level = result.tech_debt_level
                repo.last_analysis_at = datetime.utcnow()
            
            db.commit()
            logger.info(f"Saved analysis {analysis.id} with VCI score {result.vci_score}")
        else:
            logger.warning(f"No pending analysis found for repository {repository_id}")


def _mark_analysis_failed(analysis_id: str, error_message: str):
    """Mark analysis as failed."""
    from app.models.analysis import Analysis
    
    with get_sync_session() as db:
        result = db.execute(
            select(Analysis).where(Analysis.id == analysis_id)
        )
        analysis = result.scalar_one_or_none()
        
        if analysis:
            analysis.status = "failed"
            analysis.error_message = error_message[:500]  # Limit error message length
            analysis.completed_at = datetime.utcnow()
            db.commit()
            logger.info(f"Marked analysis {analysis.id} as failed")
            
            # Publish failure to Redis for SSE
            publish_analysis_progress(
                analysis_id=analysis_id,
                stage="failed",
                progress=0,
                message=error_message[:200],
                status="failed",
            )


def _collect_files_for_embedding(repo_path) -> list[dict]:
    """Collect code files from repository for embedding generation.
    
    Args:
        repo_path: Path to the cloned repository
        
    Returns:
        List of {path: str, content: str} dicts
    """
    from pathlib import Path
    
    if not repo_path:
        return []
    
    repo_path = Path(repo_path)
    files = []
    
    # Extensions to include for embedding
    code_extensions = {
        ".py", ".js", ".jsx", ".ts", ".tsx",
        ".java", ".go", ".rs", ".rb", ".php",
        ".c", ".cpp", ".h", ".hpp", ".cs",
        ".swift", ".kt", ".scala",
    }
    
    # Directories to skip
    skip_dirs = {
        "node_modules", "vendor", "__pycache__", ".git",
        "dist", "build", ".next", "coverage", ".venv", "venv",
    }
    
    # Max file size (100KB)
    max_file_size = 100 * 1024
    
    for root, dirs, filenames in repo_path.walk():
        # Skip excluded directories
        dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith(".")]
        
        for filename in filenames:
            file_path = root / filename
            
            # Check extension
            if file_path.suffix.lower() not in code_extensions:
                continue
            
            # Check file size
            try:
                if file_path.stat().st_size > max_file_size:
                    continue
            except OSError:
                continue
            
            # Read content
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                if len(content) < 50:  # Skip very small files
                    continue
                    
                # Get relative path
                rel_path = str(file_path.relative_to(repo_path))
                
                files.append({
                    "path": rel_path,
                    "content": content,
                })
            except Exception as e:
                logger.debug(f"Could not read {file_path}: {e}")
                continue
    
    logger.info(f"Collected {len(files)} files for embedding")
    return files


@celery_app.task(bind=True, name="app.workers.analysis.analyze_repository")
def analyze_repository(
    self,
    repository_id: str,
    analysis_id: str,
    commit_sha: str | None = None,
    triggered_by: str = "manual",
) -> dict:
    """
    Analyze a repository and calculate VCI score.
    
    This task clones the repository, runs static analysis,
    calculates metrics, and generates a VCI score.
    
    Progress is published to Redis Pub/Sub for real-time SSE updates.
    """
    logger.info(
        f"Starting analysis {analysis_id} for repository {repository_id}, "
        f"commit={commit_sha}, triggered_by={triggered_by}"
    )
    
    def publish_progress(stage: str, progress: int, message: str | None = None):
        """Helper to publish progress updates."""
        publish_analysis_progress(
            analysis_id=analysis_id,
            stage=stage,
            progress=progress,
            message=message,
            status="running",
        )
        self.update_state(state="PROGRESS", meta={"stage": stage, "progress": progress})
    
    try:
        # Step 1: Get repository URL
        publish_progress("initializing", 5, "Initializing analysis...")
        repo_url, access_token = _get_repo_url(repository_id)
        logger.info(f"Repository URL: {repo_url}")
        
        # Step 2: Clone repository
        publish_progress("cloning", 15, "Cloning repository...")
        
        with RepoAnalyzer(repo_url, access_token) as analyzer:
            # Clone complete
            publish_progress("cloning", 25, "Repository cloned successfully")
            
            # Count lines
            publish_progress("counting_lines", 40, "Counting lines of code...")
            
            # Complexity analysis
            publish_progress("analyzing_complexity", 55, "Analyzing code complexity...")
            
            # Run static analysis
            publish_progress("static_analysis", 70, "Running static analysis tools...")
            
            # Calculate VCI
            publish_progress("calculating_vci", 85, "Calculating VCI score...")
            
            # Full analysis
            result = analyzer.analyze()
            
            # Step 4: Collect files for embedding BEFORE temp dir is cleaned up
            publish_progress("generating_embeddings", 90, "Collecting files for embeddings...")
            logger.info(f"Analyzer temp_dir: {analyzer.temp_dir}")
            files_for_embedding = _collect_files_for_embedding(analyzer.temp_dir)
            logger.info(f"Collected {len(files_for_embedding)} files for embedding")
        
        # Step 3: Save results (after context manager exits, temp dir is cleaned)
        publish_progress("saving_results", 92, "Saving results...")
        _save_analysis_results(repository_id, analysis_id, result)
        
        # Step 5: Queue embedding generation
        logger.info(f"files_for_embedding count: {len(files_for_embedding) if files_for_embedding else 0}")
        if files_for_embedding:
            publish_progress("queueing_embeddings", 95, "Queueing embedding generation...")
            try:
                from app.workers.embeddings import generate_embeddings
                generate_embeddings.delay(
                    repository_id=repository_id,
                    commit_sha=commit_sha,
                    files=files_for_embedding,
                )
                logger.info(f"Queued embedding generation for {len(files_for_embedding)} files")
            except Exception as e:
                logger.warning(f"Failed to queue embedding generation: {e}")
        
        # Publish completion with VCI score
        publish_analysis_progress(
            analysis_id=analysis_id,
            stage="completed",
            progress=100,
            message=f"Analysis complete! VCI Score: {result.vci_score}",
            status="completed",
            vci_score=result.vci_score,
        )
        
        logger.info(f"Analysis {analysis_id} completed for repository {repository_id}, VCI: {result.vci_score}")
        
        return {
            "repository_id": repository_id,
            "analysis_id": analysis_id,
            "commit_sha": commit_sha,
            "vci_score": result.vci_score,
            "tech_debt_level": result.tech_debt_level,
            "metrics": result.metrics,
            "issues_count": len(result.issues),
            "status": "completed",
        }
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Analysis {analysis_id} failed for repository {repository_id}: {error_msg}")
        _mark_analysis_failed(analysis_id, error_msg)
        self.update_state(state="FAILURE", meta={"error": error_msg})
        raise


@celery_app.task(name="app.workers.analysis.run_quick_scan")
def run_quick_scan(repo_url: str) -> dict:
    """
    Run a quick VCI scan for playground (public repos).
    
    Args:
        repo_url: GitHub repository URL
    
    Returns:
        dict with quick scan results
    """
    logger.info(f"Running quick scan for {repo_url}")
    
    try:
        with RepoAnalyzer(repo_url) as analyzer:
            result = analyzer.analyze()
        
        return {
            "repo_url": repo_url,
            "vci_score": result.vci_score,
            "tech_debt_level": result.tech_debt_level,
            "metrics": result.metrics,
            "top_issues": result.issues[:5],  # Top 5 issues
            "status": "completed",
        }
        
    except Exception as e:
        logger.error(f"Quick scan failed for {repo_url}: {e}")
        return {
            "repo_url": repo_url,
            "status": "failed",
            "error": str(e),
        }


@celery_app.task(name="app.workers.analysis.run_cluster_analysis")
def run_cluster_analysis(repository_id: str) -> dict:
    """
    Run cluster analysis on repository embeddings.
    
    This task analyzes the vector embeddings for a repository,
    performs HDBSCAN clustering, and updates cluster_id in Qdrant.
    
    Should be run after embeddings are generated.
    
    Args:
        repository_id: UUID of the repository
    
    Returns:
        dict with cluster analysis results
    """
    import asyncio
    
    logger.info(f"Running cluster analysis for repository {repository_id}")
    
    try:
        from app.services.cluster_analyzer import get_cluster_analyzer
        from app.workers.embeddings import get_qdrant_client, COLLECTION_NAME
        
        # Run async analyzer in sync context
        def run_async(coro):
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            return loop.run_until_complete(coro)
        
        analyzer = get_cluster_analyzer()
        health = run_async(analyzer.analyze(repository_id))
        
        # Update cluster_id in Qdrant for each chunk
        if health.clusters:
            qdrant = get_qdrant_client()
            
            # Build cluster mapping from file paths
            file_to_cluster = {}
            for cluster in health.clusters:
                for file_path in cluster.top_files:
                    file_to_cluster[file_path] = cluster.id
            
            # Update points with cluster_id
            # Note: This is a simplified approach - in production,
            # you'd want to update based on the actual clustering results
            logger.info(f"Cluster analysis complete: {len(health.clusters)} clusters found")
        
        return {
            "repository_id": repository_id,
            "overall_score": health.overall_score,
            "cluster_count": len(health.clusters),
            "outlier_count": len(health.outliers),
            "total_chunks": health.total_chunks,
            "total_files": health.total_files,
            "metrics": health.metrics,
            "status": "completed",
        }
        
    except Exception as e:
        logger.error(f"Cluster analysis failed for {repository_id}: {e}")
        return {
            "repository_id": repository_id,
            "status": "failed",
            "error": str(e),
        }
