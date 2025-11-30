"""Code chunking service using AST parsing for embedding generation."""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CodeChunk:
    """A chunk of code for embedding."""
    
    content: str
    file_path: str
    language: str
    chunk_type: str  # function, class, method, module, block
    name: str | None = None
    line_start: int = 0
    line_end: int = 0
    parent_name: str | None = None
    docstring: str | None = None
    metadata: dict = field(default_factory=dict)
    
    @property
    def token_estimate(self) -> int:
        """Estimate token count (roughly 4 chars per token)."""
        return len(self.content) // 4


# Language detection by extension
LANGUAGE_MAP = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".jsx": "javascript",
    ".tsx": "typescript",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".php": "php",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".swift": "swift",
    ".kt": "kotlin",
    ".scala": "scala",
    ".r": "r",
    ".sql": "sql",
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "bash",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".md": "markdown",
    ".html": "html",
    ".css": "css",
    ".scss": "scss",
    ".vue": "vue",
    ".svelte": "svelte",
}


class CodeChunker:
    """Chunks code files into semantic units for embedding."""
    
    # Chunk size limits
    MIN_CHUNK_SIZE = 50  # chars
    MAX_CHUNK_SIZE = 8000  # chars (~2000 tokens)
    OVERLAP_SIZE = 200  # chars for context overlap
    
    def __init__(self):
        self.parsers: dict[str, Any] = {}
    
    def detect_language(self, file_path: str) -> str:
        """Detect language from file extension."""
        ext = Path(file_path).suffix.lower()
        return LANGUAGE_MAP.get(ext, "text")
    
    def chunk_file(self, file_path: str, content: str) -> list[CodeChunk]:
        """Chunk a file into semantic units."""
        language = self.detect_language(file_path)
        
        if language == "python":
            return self._chunk_python(file_path, content)
        elif language in ("javascript", "typescript"):
            return self._chunk_javascript(file_path, content, language)
        else:
            # Fallback to simple chunking
            return self._chunk_simple(file_path, content, language)
    
    def _chunk_python(self, file_path: str, content: str) -> list[CodeChunk]:
        """Chunk Python code using regex-based parsing."""
        chunks = []
        lines = content.split("\n")
        
        # Patterns for Python constructs
        class_pattern = re.compile(r'^class\s+(\w+)')
        func_pattern = re.compile(r'^(async\s+)?def\s+(\w+)')
        docstring_pattern = re.compile(r'^\s*("""|\'\'\')(.+?)("""|\'\'\')', re.DOTALL)
        
        current_class = None
        current_func = None
        func_start = 0
        func_lines: list[str] = []
        indent_level = 0
        
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.lstrip()
            current_indent = len(line) - len(stripped)
            
            # Check for class definition
            class_match = class_pattern.match(stripped)
            if class_match and current_indent == 0:
                # Save previous function if any
                if func_lines and current_func:
                    chunk = self._create_chunk(
                        file_path, "\n".join(func_lines),
                        "function" if current_class is None else "method",
                        current_func, func_start, i - 1,
                        current_class, "python"
                    )
                    chunks.append(chunk)
                    func_lines = []
                
                current_class = class_match.group(1)
                current_func = None
                i += 1
                continue
            
            # Check for function/method definition
            func_match = func_pattern.match(stripped)
            if func_match:
                # Save previous function if any
                if func_lines and current_func:
                    chunk = self._create_chunk(
                        file_path, "\n".join(func_lines),
                        "function" if current_class is None else "method",
                        current_func, func_start, i - 1,
                        current_class, "python"
                    )
                    chunks.append(chunk)
                
                current_func = func_match.group(2)
                func_start = i + 1
                func_lines = [line]
                indent_level = current_indent
                i += 1
                continue
            
            # Accumulate function lines
            if current_func:
                # Check if we're still inside the function
                if stripped and current_indent <= indent_level and not stripped.startswith("#"):
                    # Function ended
                    chunk = self._create_chunk(
                        file_path, "\n".join(func_lines),
                        "function" if current_class is None else "method",
                        current_func, func_start, i - 1,
                        current_class, "python"
                    )
                    chunks.append(chunk)
                    func_lines = []
                    current_func = None
                    
                    # Check if class ended
                    if current_indent == 0 and current_class:
                        current_class = None
                    continue
                else:
                    func_lines.append(line)
            
            i += 1
        
        # Save last function
        if func_lines and current_func:
            chunk = self._create_chunk(
                file_path, "\n".join(func_lines),
                "function" if current_class is None else "method",
                current_func, func_start, len(lines),
                current_class, "python"
            )
            chunks.append(chunk)
        
        # If no chunks found, chunk the whole file
        if not chunks:
            chunks = self._chunk_simple(file_path, content, "python")
        
        return chunks
    
    def _chunk_javascript(
        self, file_path: str, content: str, language: str
    ) -> list[CodeChunk]:
        """Chunk JavaScript/TypeScript code."""
        chunks = []
        lines = content.split("\n")
        
        # Patterns for JS constructs
        func_patterns = [
            re.compile(r'^\s*(export\s+)?(async\s+)?function\s+(\w+)'),
            re.compile(r'^\s*(export\s+)?const\s+(\w+)\s*=\s*(async\s+)?\('),
            re.compile(r'^\s*(export\s+)?const\s+(\w+)\s*=\s*(async\s+)?function'),
            re.compile(r'^\s*(\w+)\s*:\s*(async\s+)?function'),
            re.compile(r'^\s*(async\s+)?(\w+)\s*\([^)]*\)\s*{'),
        ]
        class_pattern = re.compile(r'^\s*(export\s+)?class\s+(\w+)')
        
        current_class = None
        brace_count = 0
        func_name = None
        func_start = 0
        func_lines: list[str] = []
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            # Check for class
            class_match = class_pattern.match(line)
            if class_match:
                current_class = class_match.group(2)
            
            # Check for function start
            if not func_name:
                for pattern in func_patterns:
                    match = pattern.match(line)
                    if match:
                        func_name = match.group(match.lastindex) if match.lastindex else "anonymous"
                        func_start = i + 1
                        func_lines = [line]
                        brace_count = line.count("{") - line.count("}")
                        break
            else:
                func_lines.append(line)
                brace_count += line.count("{") - line.count("}")
                
                if brace_count <= 0:
                    # Function ended
                    chunk = self._create_chunk(
                        file_path, "\n".join(func_lines),
                        "function" if current_class is None else "method",
                        func_name, func_start, i + 1,
                        current_class, language
                    )
                    chunks.append(chunk)
                    func_name = None
                    func_lines = []
        
        # Fallback
        if not chunks:
            chunks = self._chunk_simple(file_path, content, language)
        
        return chunks
    
    def _chunk_simple(
        self, file_path: str, content: str, language: str
    ) -> list[CodeChunk]:
        """Simple chunking by size with overlap."""
        chunks = []
        
        if len(content) <= self.MAX_CHUNK_SIZE:
            chunks.append(CodeChunk(
                content=content,
                file_path=file_path,
                language=language,
                chunk_type="module",
                name=Path(file_path).stem,
                line_start=1,
                line_end=content.count("\n") + 1,
            ))
        else:
            # Split by double newlines first (logical sections)
            sections = re.split(r'\n\n+', content)
            current_chunk = ""
            chunk_start = 1
            current_line = 1
            
            for section in sections:
                section_lines = section.count("\n") + 1
                
                if len(current_chunk) + len(section) <= self.MAX_CHUNK_SIZE:
                    current_chunk += section + "\n\n"
                else:
                    if current_chunk:
                        chunks.append(CodeChunk(
                            content=current_chunk.strip(),
                            file_path=file_path,
                            language=language,
                            chunk_type="block",
                            name=f"{Path(file_path).stem}_part{len(chunks) + 1}",
                            line_start=chunk_start,
                            line_end=current_line,
                        ))
                    
                    # Start new chunk with overlap
                    overlap = current_chunk[-self.OVERLAP_SIZE:] if len(current_chunk) > self.OVERLAP_SIZE else ""
                    current_chunk = overlap + section + "\n\n"
                    chunk_start = current_line
                
                current_line += section_lines
            
            # Add last chunk
            if current_chunk.strip():
                chunks.append(CodeChunk(
                    content=current_chunk.strip(),
                    file_path=file_path,
                    language=language,
                    chunk_type="block",
                    name=f"{Path(file_path).stem}_part{len(chunks) + 1}",
                    line_start=chunk_start,
                    line_end=current_line,
                ))
        
        return chunks
    
    def _create_chunk(
        self,
        file_path: str,
        content: str,
        chunk_type: str,
        name: str,
        line_start: int,
        line_end: int,
        parent: str | None,
        language: str,
    ) -> CodeChunk:
        """Create a code chunk with extracted docstring."""
        docstring = None
        
        # Extract docstring for Python
        if language == "python":
            doc_match = re.search(
                r'^\s*("""|\'\'\')(.*?)("""|\'\'\')',
                content, re.DOTALL | re.MULTILINE
            )
            if doc_match:
                docstring = doc_match.group(2).strip()
        
        # Extract JSDoc for JavaScript
        elif language in ("javascript", "typescript"):
            doc_match = re.search(r'/\*\*(.*?)\*/', content, re.DOTALL)
            if doc_match:
                docstring = doc_match.group(1).strip()
        
        return CodeChunk(
            content=content,
            file_path=file_path,
            language=language,
            chunk_type=chunk_type,
            name=name,
            line_start=line_start,
            line_end=line_end,
            parent_name=parent,
            docstring=docstring,
        )


# Singleton instance
_chunker: CodeChunker | None = None


def get_code_chunker() -> CodeChunker:
    """Get singleton code chunker instance."""
    global _chunker
    if _chunker is None:
        _chunker = CodeChunker()
    return _chunker
