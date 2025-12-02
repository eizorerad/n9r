"""Cluster Analyzer Service for Semantic Architecture Analysis.

Uses HDBSCAN clustering on code embeddings to:
- Detect natural module boundaries
- Find outliers (dead/misplaced code)
- Identify coupling hotspots (god files)
- Calculate cohesion metrics
"""

import logging
from dataclasses import dataclass, field
from collections import defaultdict

import numpy as np
from sklearn.cluster import HDBSCAN
from sklearn.metrics.pairwise import cosine_distances
from qdrant_client import QdrantClient

from app.core.config import settings

logger = logging.getLogger(__name__)

COLLECTION_NAME = "code_embeddings"


@dataclass
class ClusterInfo:
    """Information about a detected cluster."""
    id: int
    name: str  # Auto-generated from file paths
    file_count: int
    chunk_count: int
    cohesion: float  # 0-1, higher = more related
    top_files: list[str] = field(default_factory=list)
    dominant_language: str | None = None
    status: str = "healthy"  # healthy, moderate, scattered


@dataclass
class OutlierInfo:
    """Information about an outlier (potential dead/misplaced code)."""
    file_path: str
    chunk_name: str | None
    chunk_type: str | None
    nearest_similarity: float
    nearest_file: str | None
    suggestion: str


@dataclass
class CouplingHotspot:
    """A file that bridges multiple clusters."""
    file_path: str
    clusters_connected: int
    cluster_names: list[str]
    suggestion: str


@dataclass
class ArchitectureHealth:
    """Complete architecture health analysis."""
    overall_score: int  # 0-100
    clusters: list[ClusterInfo]
    outliers: list[OutlierInfo]
    coupling_hotspots: list[CouplingHotspot]
    total_chunks: int
    total_files: int
    metrics: dict = field(default_factory=dict)


class ClusterAnalyzer:
    """Analyzes code architecture using vector clustering."""
    
    def __init__(self, qdrant_client: QdrantClient | None = None):
        self.qdrant = qdrant_client or QdrantClient(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
        )
    
    async def analyze(self, repo_id: str) -> ArchitectureHealth:
        """Run full architecture analysis on a repository."""
        logger.info(f"Starting cluster analysis for repo {repo_id}")
        
        # Fetch all vectors
        vectors, payloads = self._fetch_vectors(repo_id)
        
        if len(vectors) < 5:
            logger.warning(f"Not enough vectors for clustering: {len(vectors)}")
            return self._empty_health(len(vectors))
        
        # Run clustering
        labels = self._run_clustering(vectors)
        
        # Analyze results
        clusters = self._analyze_clusters(vectors, labels, payloads)
        outliers = self._find_outliers(vectors, labels, payloads)
        hotspots = self._find_coupling_hotspots(labels, payloads)
        
        # Calculate overall score
        overall_score = self._calculate_overall_score(clusters, outliers, len(vectors))
        
        # Count unique files
        unique_files = set(p.get("file_path") for p in payloads if p.get("file_path"))
        
        return ArchitectureHealth(
            overall_score=overall_score,
            clusters=clusters,
            outliers=outliers,
            coupling_hotspots=hotspots,
            total_chunks=len(vectors),
            total_files=len(unique_files),
            metrics={
                "avg_cohesion": np.mean([c.cohesion for c in clusters]) if clusters else 0,
                "outlier_percentage": len(outliers) / len(vectors) * 100 if len(vectors) > 0 else 0,
                "cluster_count": len(clusters),
            }
        )
    
    def _fetch_vectors(self, repo_id: str) -> tuple[np.ndarray, list[dict]]:
        """Fetch all vectors and payloads for a repository."""
        vectors = []
        payloads = []
        
        # Scroll through all points
        offset = None
        while True:
            results, offset = self.qdrant.scroll(
                collection_name=COLLECTION_NAME,
                scroll_filter={
                    "must": [
                        {"key": "repository_id", "match": {"value": repo_id}}
                    ]
                },
                limit=100,
                offset=offset,
                with_vectors=True,
            )
            
            for point in results:
                if point.vector:
                    vectors.append(point.vector)
                    payloads.append(point.payload or {})
            
            if offset is None:
                break
        
        logger.info(f"Fetched {len(vectors)} vectors for repo {repo_id}")
        return np.array(vectors) if vectors else np.array([]), payloads
    
    def _run_clustering(self, vectors: np.ndarray) -> np.ndarray:
        """Run HDBSCAN clustering on vectors."""
        if len(vectors) < 5:
            return np.array([-1] * len(vectors))
        
        # HDBSCAN with cosine metric
        clusterer = HDBSCAN(
            min_cluster_size=max(3, len(vectors) // 20),  # At least 5% of points
            min_samples=2,
            metric="euclidean",  # Use euclidean on normalized vectors
            cluster_selection_epsilon=0.0,
        )
        
        # Normalize vectors for better clustering
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        normalized = vectors / np.maximum(norms, 1e-10)
        
        labels = clusterer.fit_predict(normalized)
        
        n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
        n_outliers = np.sum(labels == -1)
        logger.info(f"Clustering: {n_clusters} clusters, {n_outliers} outliers")
        
        return labels
    
    def _analyze_clusters(
        self, 
        vectors: np.ndarray, 
        labels: np.ndarray, 
        payloads: list[dict]
    ) -> list[ClusterInfo]:
        """Analyze each cluster for cohesion and naming."""
        clusters = []
        unique_labels = set(labels) - {-1}  # Exclude outliers
        
        for cluster_id in sorted(unique_labels):
            mask = labels == cluster_id
            cluster_vectors = vectors[mask]
            cluster_payloads = [p for p, m in zip(payloads, mask) if m]
            
            # Calculate cohesion (1 - avg pairwise distance)
            if len(cluster_vectors) > 1:
                distances = cosine_distances(cluster_vectors)
                avg_distance = np.mean(distances[np.triu_indices(len(distances), k=1)])
                cohesion = 1 - avg_distance
            else:
                cohesion = 1.0
            
            # Get file paths and count
            file_paths = [p.get("file_path", "") for p in cluster_payloads]
            unique_files = list(set(file_paths))
            
            # Auto-generate cluster name from common path prefix
            name = self._generate_cluster_name(unique_files, cluster_id)
            
            # Get dominant language
            languages = [p.get("language") for p in cluster_payloads if p.get("language")]
            dominant_lang = max(set(languages), key=languages.count) if languages else None
            
            # Determine status
            if cohesion >= 0.7:
                status = "healthy"
            elif cohesion >= 0.5:
                status = "moderate"
            else:
                status = "scattered"
            
            clusters.append(ClusterInfo(
                id=int(cluster_id),
                name=name,
                file_count=len(unique_files),
                chunk_count=len(cluster_payloads),
                cohesion=round(cohesion, 3),
                top_files=unique_files[:5],
                dominant_language=dominant_lang,
                status=status,
            ))
        
        # Sort by chunk count descending
        clusters.sort(key=lambda c: c.chunk_count, reverse=True)
        return clusters
    
    def _generate_cluster_name(self, file_paths: list[str], cluster_id: int) -> str:
        """Generate a human-readable name for a cluster."""
        if not file_paths:
            return f"cluster_{cluster_id}"
        
        # Find common directory prefix
        parts_list = [p.split("/") for p in file_paths if p]
        if not parts_list:
            return f"cluster_{cluster_id}"
        
        # Find common prefix
        common_parts = []
        for parts in zip(*parts_list):
            if len(set(parts)) == 1:
                common_parts.append(parts[0])
            else:
                break
        
        if common_parts:
            # Use the last meaningful directory
            name = common_parts[-1] if common_parts[-1] else common_parts[-2] if len(common_parts) > 1 else f"cluster_{cluster_id}"
            return name.replace("_", " ").replace("-", " ").title().replace(" ", "_").lower()
        
        # Fallback: use most common directory
        dirs = [p.split("/")[0] for p in file_paths if "/" in p]
        if dirs:
            return max(set(dirs), key=dirs.count)
        
        return f"cluster_{cluster_id}"
    
    def _find_outliers(
        self, 
        vectors: np.ndarray, 
        labels: np.ndarray, 
        payloads: list[dict]
    ) -> list[OutlierInfo]:
        """Find outliers and generate suggestions."""
        outliers = []
        outlier_mask = labels == -1
        
        if not np.any(outlier_mask):
            return outliers
        
        # For each outlier, find nearest non-outlier
        non_outlier_mask = labels != -1
        non_outlier_vectors = vectors[non_outlier_mask]
        non_outlier_payloads = [p for p, m in zip(payloads, non_outlier_mask) if m]
        
        for i, (is_outlier, vector, payload) in enumerate(zip(outlier_mask, vectors, payloads)):
            if not is_outlier:
                continue
            
            # Find nearest neighbor
            if len(non_outlier_vectors) > 0:
                distances = cosine_distances([vector], non_outlier_vectors)[0]
                nearest_idx = np.argmin(distances)
                nearest_similarity = 1 - distances[nearest_idx]
                nearest_file = non_outlier_payloads[nearest_idx].get("file_path")
            else:
                nearest_similarity = 0
                nearest_file = None
            
            # Generate suggestion
            if nearest_similarity < 0.3:
                suggestion = "Review for deletion — appears unused or orphaned"
            elif nearest_similarity < 0.5:
                suggestion = f"Consider moving closer to {nearest_file}" if nearest_file else "Review placement"
            else:
                suggestion = "Minor outlier — may be a utility or edge case"
            
            outliers.append(OutlierInfo(
                file_path=payload.get("file_path", "unknown"),
                chunk_name=payload.get("name"),
                chunk_type=payload.get("chunk_type"),
                nearest_similarity=round(nearest_similarity, 3),
                nearest_file=nearest_file,
                suggestion=suggestion,
            ))
        
        # Sort by similarity (most isolated first)
        outliers.sort(key=lambda o: o.nearest_similarity)
        return outliers[:20]  # Limit to top 20
    
    def _find_coupling_hotspots(
        self, 
        labels: np.ndarray, 
        payloads: list[dict]
    ) -> list[CouplingHotspot]:
        """Find files that bridge multiple clusters (god files)."""
        # Group chunks by file
        file_clusters: dict[str, set[int]] = defaultdict(set)
        
        for label, payload in zip(labels, payloads):
            if label == -1:  # Skip outliers
                continue
            file_path = payload.get("file_path", "")
            if file_path:
                file_clusters[file_path].add(int(label))
        
        # Find files in multiple clusters
        hotspots = []
        for file_path, clusters in file_clusters.items():
            if len(clusters) >= 3:  # Bridges 3+ clusters
                hotspots.append(CouplingHotspot(
                    file_path=file_path,
                    clusters_connected=len(clusters),
                    cluster_names=[f"cluster_{c}" for c in sorted(clusters)],
                    suggestion="Consider splitting — this file has too many responsibilities",
                ))
        
        # Sort by clusters connected
        hotspots.sort(key=lambda h: h.clusters_connected, reverse=True)
        return hotspots[:10]  # Limit to top 10
    
    def _calculate_overall_score(
        self, 
        clusters: list[ClusterInfo], 
        outliers: list[OutlierInfo],
        total_chunks: int
    ) -> int:
        """Calculate overall architecture health score (0-100)."""
        if total_chunks == 0:
            return 0
        
        # Cohesion component (40%)
        if clusters:
            avg_cohesion = np.mean([c.cohesion for c in clusters])
            cohesion_score = avg_cohesion * 40
        else:
            cohesion_score = 20  # Neutral if no clusters
        
        # Outlier component (30%)
        outlier_ratio = len(outliers) / total_chunks
        outlier_score = max(0, 30 - outlier_ratio * 100)
        
        # Cluster balance component (30%)
        if len(clusters) >= 2:
            sizes = [c.chunk_count for c in clusters]
            # Gini coefficient for balance
            sorted_sizes = sorted(sizes)
            n = len(sorted_sizes)
            cumsum = np.cumsum(sorted_sizes)
            gini = (2 * np.sum((np.arange(1, n + 1) * sorted_sizes))) / (n * np.sum(sorted_sizes)) - (n + 1) / n
            balance_score = (1 - abs(gini)) * 30
        else:
            balance_score = 15  # Neutral
        
        return int(min(100, max(0, cohesion_score + outlier_score + balance_score)))
    
    def _empty_health(self, chunk_count: int) -> ArchitectureHealth:
        """Return empty health result for repos with insufficient data."""
        return ArchitectureHealth(
            overall_score=0,
            clusters=[],
            outliers=[],
            coupling_hotspots=[],
            total_chunks=chunk_count,
            total_files=0,
            metrics={
                "avg_cohesion": 0,
                "outlier_percentage": 0,
                "cluster_count": 0,
                "warning": "Insufficient data for clustering (need at least 5 chunks)",
            }
        )


def get_cluster_analyzer() -> ClusterAnalyzer:
    """Get cluster analyzer instance."""
    return ClusterAnalyzer()
