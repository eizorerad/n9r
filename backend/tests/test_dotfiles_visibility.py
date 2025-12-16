
from pathlib import Path
from tempfile import TemporaryDirectory
from app.services.repo_content import RepoContentService

def test_dotfiles_visibility():
    """Test that dotfiles are visible but .git and .DS_Store are hidden."""
    with TemporaryDirectory() as temp_dir:
        repo_path = Path(temp_dir)
        
        # Create test files and directories
        (repo_path / ".git").mkdir()
        (repo_path / ".github").mkdir()
        (repo_path / ".vscode").mkdir()
        (repo_path / "__pycache__").mkdir()
        
        (repo_path / ".gitignore").touch()
        (repo_path / ".env").touch()
        (repo_path / ".DS_Store").touch()
        (repo_path / "README.md").touch()
        
        # Run collection
        service = RepoContentService()
        entries = service.collect_full_tree(repo_path)
        paths = [e["path"] for e in entries]
        names = [e["name"] for e in entries]
        
        # Verify visibility
        assert ".github" in names
        assert ".vscode" in names
        assert ".gitignore" in names
        assert ".env" in names
        assert "README.md" in names
        
        # Verify exclusions
        assert ".git" not in names
        assert "__pycache__" not in names
        assert ".DS_Store" not in names
        
        # Verify types
        github_entry = next(e for e in entries if e["name"] == ".github")
        assert github_entry["type"] == "directory"
        
        gitignore_entry = next(e for e in entries if e["name"] == ".gitignore")
        assert gitignore_entry["type"] == "file"
