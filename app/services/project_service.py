"""Project service for deep code indexing and analysis."""

from __future__ import annotations

import hashlib
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import (
    Project, ProjectModule, ProjectFile, ProjectFunction,
    IDESession, ChangeLog, Component
)
from app.memory.embeddings import get_embedding_provider
from app.paths import resolve_project_path


def translate_path(path: str) -> str:
    """Translate host path to container path if needed."""
    result = resolve_project_path(path)
    return str(result.resolved_path)

logger = logging.getLogger(__name__)

# File extensions to index
CODE_EXTENSIONS = {
    '.py', '.js', '.ts', '.tsx', '.jsx', '.java', '.go', '.rs', '.rb',
    '.php', '.swift', '.kt', '.scala', '.c', '.cpp', '.h', '.hpp',
    '.cs', '.vue', '.svelte', '.astro', '.html', '.css', '.scss', '.sass',
    '.sql', '.graphql', '.proto', '.yaml', '.yml', '.json', '.toml', '.xml',
    '.md', '.mdx', '.txt', '.sh', '.bash', '.zsh', '.dockerfile', '.env'
}

# Directories to skip
SKIP_DIRS = {
    'node_modules', '.git', '__pycache__', '.venv', 'venv', 'env',
    '.next', '.nuxt', 'dist', 'build', 'target', '.idea', '.vscode',
    'coverage', '.pytest_cache', '.mypy_cache', '.tox', 'eggs',
    '*.egg-info', '.cache', 'vendor', 'bower_components'
}

# Module type detection patterns
MODULE_PATTERNS = {
    'backend': ['api', 'server', 'backend', 'app', 'src/api', 'src/server'],
    'frontend': ['frontend', 'client', 'web', 'ui', 'src/client', 'src/web', 'pages', 'components'],
    'mobile': ['mobile', 'ios', 'android', 'app', 'react-native', 'flutter'],
    'bot': ['bot', 'telegram', 'discord', 'slack', 'chatbot'],
    'shared': ['shared', 'common', 'lib', 'utils', 'helpers', 'core'],
    'infra': ['infra', 'infrastructure', 'deploy', 'docker', 'k8s', 'terraform'],
    'docs': ['docs', 'documentation', 'wiki'],
}

# Language detection by extension
LANG_BY_EXT = {
    '.py': 'python', '.js': 'javascript', '.ts': 'typescript',
    '.tsx': 'typescript', '.jsx': 'javascript', '.java': 'java',
    '.go': 'go', '.rs': 'rust', '.rb': 'ruby', '.php': 'php',
    '.swift': 'swift', '.kt': 'kotlin', '.scala': 'scala',
    '.c': 'c', '.cpp': 'cpp', '.h': 'c', '.hpp': 'cpp',
    '.cs': 'csharp', '.vue': 'vue', '.svelte': 'svelte',
    '.html': 'html', '.css': 'css', '.scss': 'scss',
    '.sql': 'sql', '.graphql': 'graphql', '.proto': 'protobuf',
    '.yaml': 'yaml', '.yml': 'yaml', '.json': 'json',
    '.md': 'markdown', '.sh': 'shell', '.dockerfile': 'dockerfile',
}


class ProjectService:
    """Service for deep project indexing and management."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self._embedding_provider = None

    @property
    def embedding_provider(self):
        if self._embedding_provider is None:
            self._embedding_provider = get_embedding_provider()
        return self._embedding_provider

    async def create_project(
        self,
        name: str,
        path: str,
        description: str | None = None,
    ) -> dict[str, Any]:
        """Create a new project record."""
        # Translate path for Docker environment
        resolved_path = translate_path(path)
        
        # Check if project exists
        stmt = select(Project).where(Project.path == path)
        result = await self.db.execute(stmt)
        existing = result.scalar_one_or_none()
        
        if existing:
            return {
                "project_id": str(existing.id),
                "name": existing.name,
                "path": existing.path,
                "status": "exists",
                "message": "Project already exists"
            }
        
        project = Project(
            name=name,
            path=path,
            description=description,
            analysis_status="pending"
        )
        self.db.add(project)
        await self.db.flush()
        
        return {
            "project_id": str(project.id),
            "name": project.name,
            "path": project.path,
            "status": "created",
            "message": "Project created successfully"
        }

    async def full_index_project(
        self,
        project_id: str,
        include_content: bool = True,
        generate_embeddings: bool = True,
        max_file_size: int = 500000,  # 500KB
    ) -> dict[str, Any]:
        """Perform deep indexing of entire project."""
        stmt = select(Project).where(Project.id == UUID(project_id))
        result = await self.db.execute(stmt)
        project = result.scalar_one_or_none()
        
        if not project:
            return {"error": f"Project {project_id} not found"}
        
        project.analysis_status = "analyzing"
        await self.db.flush()
        
        resolved_path = translate_path(project.path)
        if not os.path.exists(resolved_path):
            project.analysis_status = "error"
            project.analysis_error = f"Path not found: {resolved_path}"
            return {"error": f"Project path not found: {resolved_path}"}
        
        stats = {
            "modules_created": 0,
            "files_indexed": 0,
            "functions_extracted": 0,
            "total_lines": 0,
            "languages": set(),
            "errors": []
        }
        
        try:
            # Detect and create modules
            modules = await self._detect_modules(project, resolved_path)
            stats["modules_created"] = len(modules)
            
            # Index all files
            for root, dirs, files in os.walk(resolved_path):
                # Skip unwanted directories
                dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith('.')]
                
                for filename in files:
                    ext = Path(filename).suffix.lower()
                    if ext not in CODE_EXTENSIONS:
                        continue
                    
                    file_path = os.path.join(root, filename)
                    rel_path = os.path.relpath(file_path, resolved_path)
                    
                    try:
                        file_stat = os.stat(file_path)
                        if file_stat.st_size > max_file_size:
                            continue
                        
                        # Find module for this file
                        module = self._find_module_for_file(modules, rel_path)
                        
                        # Index file
                        file_record = await self._index_file(
                            project=project,
                            module=module,
                            file_path=file_path,
                            rel_path=rel_path,
                            include_content=include_content,
                            generate_embeddings=generate_embeddings,
                        )
                        
                        if file_record:
                            stats["files_indexed"] += 1
                            stats["total_lines"] += file_record.line_count
                            if file_record.language:
                                stats["languages"].add(file_record.language)
                            
                            # Extract functions
                            funcs = await self._extract_functions(
                                project=project,
                                file_record=file_record,
                                generate_embeddings=generate_embeddings,
                            )
                            stats["functions_extracted"] += len(funcs)
                    
                    except Exception as e:
                        stats["errors"].append(f"{rel_path}: {str(e)}")
                        logger.warning(f"Error indexing {rel_path}: {e}")
            
            # Update project stats
            project.total_files = stats["files_indexed"]
            project.total_lines = stats["total_lines"]
            project.languages = list(stats["languages"])
            project.analysis_status = "completed"
            project.last_analyzed = datetime.now(timezone.utc)
            
            await self.db.flush()
            
            return {
                "project_id": str(project.id),
                "status": "completed",
                "stats": {
                    "modules": stats["modules_created"],
                    "files": stats["files_indexed"],
                    "functions": stats["functions_extracted"],
                    "lines": stats["total_lines"],
                    "languages": list(stats["languages"]),
                    "errors_count": len(stats["errors"]),
                }
            }
        
        except Exception as e:
            project.analysis_status = "error"
            project.analysis_error = str(e)
            logger.error(f"Error indexing project: {e}")
            return {"error": str(e)}

    async def _detect_modules(
        self,
        project: Project,
        resolved_path: str
    ) -> list[ProjectModule]:
        """Detect and create project modules (backend, frontend, etc.)."""
        modules = []
        
        # Check root level directories
        for item in os.listdir(resolved_path):
            item_path = os.path.join(resolved_path, item)
            if not os.path.isdir(item_path) or item in SKIP_DIRS or item.startswith('.'):
                continue
            
            item_lower = item.lower()
            module_type = "shared"  # default
            
            for mtype, patterns in MODULE_PATTERNS.items():
                if any(p in item_lower for p in patterns):
                    module_type = mtype
                    break
            
            # Detect tech stack for module
            tech_stack, frameworks, languages = self._detect_tech_stack(item_path)
            
            module = ProjectModule(
                project_id=project.id,
                name=item,
                module_type=module_type,
                path=item,
                tech_stack=tech_stack,
                frameworks=frameworks,
                languages=languages,
            )
            self.db.add(module)
            modules.append(module)
        
        # If no modules detected, create a single "main" module
        if not modules:
            tech_stack, frameworks, languages = self._detect_tech_stack(resolved_path)
            module = ProjectModule(
                project_id=project.id,
                name="main",
                module_type="shared",
                path=".",
                tech_stack=tech_stack,
                frameworks=frameworks,
                languages=languages,
            )
            self.db.add(module)
            modules.append(module)
        
        await self.db.flush()
        return modules

    def _detect_tech_stack(self, path: str) -> tuple[list, list, list]:
        """Detect tech stack from config files."""
        tech_stack = []
        frameworks = []
        languages = []
        
        config_files = {
            'package.json': ('javascript', ['node']),
            'requirements.txt': ('python', []),
            'pyproject.toml': ('python', []),
            'Cargo.toml': ('rust', []),
            'go.mod': ('go', []),
            'pom.xml': ('java', ['maven']),
            'build.gradle': ('java', ['gradle']),
            'Gemfile': ('ruby', []),
            'composer.json': ('php', []),
        }
        
        for filename, (lang, stack) in config_files.items():
            if os.path.exists(os.path.join(path, filename)):
                if lang not in languages:
                    languages.append(lang)
                tech_stack.extend(stack)
        
        # Detect frameworks from package.json
        pkg_json = os.path.join(path, 'package.json')
        if os.path.exists(pkg_json):
            try:
                import json
                with open(pkg_json, 'r') as f:
                    pkg = json.load(f)
                deps = {**pkg.get('dependencies', {}), **pkg.get('devDependencies', {})}
                
                framework_map = {
                    'react': 'react', 'next': 'nextjs', 'vue': 'vue',
                    'nuxt': 'nuxt', 'svelte': 'svelte', 'angular': 'angular',
                    'express': 'express', 'fastify': 'fastify', 'nest': 'nestjs',
                }
                for dep, fw in framework_map.items():
                    if any(dep in d for d in deps.keys()):
                        if fw not in frameworks:
                            frameworks.append(fw)
            except:
                pass
        
        # Detect Python frameworks
        req_txt = os.path.join(path, 'requirements.txt')
        if os.path.exists(req_txt):
            try:
                with open(req_txt, 'r') as f:
                    content = f.read().lower()
                py_frameworks = {
                    'fastapi': 'fastapi', 'django': 'django', 'flask': 'flask',
                    'sqlalchemy': 'sqlalchemy', 'celery': 'celery',
                }
                for pkg, fw in py_frameworks.items():
                    if pkg in content and fw not in frameworks:
                        frameworks.append(fw)
            except:
                pass
        
        return tech_stack, frameworks, languages

    def _find_module_for_file(
        self,
        modules: list[ProjectModule],
        rel_path: str
    ) -> ProjectModule | None:
        """Find which module a file belongs to."""
        for module in modules:
            if rel_path.startswith(module.path) or module.path == ".":
                return module
        return modules[0] if modules else None

    async def _index_file(
        self,
        project: Project,
        module: ProjectModule | None,
        file_path: str,
        rel_path: str,
        include_content: bool,
        generate_embeddings: bool,
    ) -> ProjectFile | None:
        """Index a single file."""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        except Exception as e:
            logger.warning(f"Cannot read {file_path}: {e}")
            return None
        
        ext = Path(file_path).suffix.lower()
        language = LANG_BY_EXT.get(ext)
        lines = content.count('\n') + 1
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        
        # Check if file already indexed with same hash
        stmt = select(ProjectFile).where(
            and_(
                ProjectFile.project_id == project.id,
                ProjectFile.relative_path == rel_path
            )
        )
        result = await self.db.execute(stmt)
        existing = result.scalar_one_or_none()
        
        if existing and existing.content_hash == content_hash:
            return existing  # No changes
        
        # Extract imports
        imports = self._extract_imports(content, language)
        
        # Create or update file record
        if existing:
            file_record = existing
            file_record.content = content if include_content else None
            file_record.content_hash = content_hash
            file_record.line_count = lines
            file_record.size_bytes = len(content.encode())
            file_record.imports = imports
            file_record.last_indexed = datetime.now(timezone.utc)
        else:
            file_record = ProjectFile(
                project_id=project.id,
                module_id=module.id if module else None,
                name=Path(file_path).name,
                path=file_path,
                relative_path=rel_path,
                language=language,
                file_extension=ext,
                content=content if include_content else None,
                content_hash=content_hash,
                size_bytes=len(content.encode()),
                line_count=lines,
                imports=imports,
                last_indexed=datetime.now(timezone.utc),
            )
            self.db.add(file_record)
        
        # Generate embedding for file
        if generate_embeddings and content:
            try:
                # Use first 2000 chars for embedding
                embed_text = f"{rel_path}\n{content[:2000]}"
                embedding = await self.embedding_provider.embed(embed_text)
                file_record.embedding = embedding
            except Exception as e:
                logger.warning(f"Embedding failed for {rel_path}: {e}")
        
        await self.db.flush()
        return file_record

    def _extract_imports(self, content: str, language: str | None) -> list[str]:
        """Extract import statements from code."""
        imports = []
        
        if language == 'python':
            # Python imports
            patterns = [
                r'^import\s+([\w.]+)',
                r'^from\s+([\w.]+)\s+import',
            ]
            for pattern in patterns:
                imports.extend(re.findall(pattern, content, re.MULTILINE))
        
        elif language in ('javascript', 'typescript'):
            # JS/TS imports
            patterns = [
                r'import\s+.*?\s+from\s+[\'"]([^\'"]+)[\'"]',
                r'require\s*\(\s*[\'"]([^\'"]+)[\'"]\s*\)',
            ]
            for pattern in patterns:
                imports.extend(re.findall(pattern, content))
        
        elif language == 'go':
            # Go imports
            imports.extend(re.findall(r'import\s+["\']([^"\']+)["\']', content))
            # Multi-line imports
            multi = re.findall(r'import\s*\((.*?)\)', content, re.DOTALL)
            for block in multi:
                imports.extend(re.findall(r'["\']([^"\']+)["\']', block))
        
        return list(set(imports))

    async def _extract_functions(
        self,
        project: Project,
        file_record: ProjectFile,
        generate_embeddings: bool,
    ) -> list[ProjectFunction]:
        """Extract functions/classes from file."""
        if not file_record.content:
            return []
        
        functions = []
        content = file_record.content
        language = file_record.language
        
        if language == 'python':
            functions = await self._extract_python_functions(
                project, file_record, content, generate_embeddings
            )
        elif language in ('javascript', 'typescript'):
            functions = await self._extract_js_functions(
                project, file_record, content, generate_embeddings
            )
        
        return functions

    async def _extract_python_functions(
        self,
        project: Project,
        file_record: ProjectFile,
        content: str,
        generate_embeddings: bool,
    ) -> list[ProjectFunction]:
        """Extract Python functions and classes."""
        functions = []
        lines = content.split('\n')
        
        # Simple regex-based extraction
        patterns = [
            (r'^(\s*)def\s+(\w+)\s*\((.*?)\).*?:', 'function'),
            (r'^(\s*)async\s+def\s+(\w+)\s*\((.*?)\).*?:', 'function'),
            (r'^(\s*)class\s+(\w+).*?:', 'class'),
        ]
        
        for i, line in enumerate(lines):
            for pattern, func_type in patterns:
                match = re.match(pattern, line)
                if match:
                    indent = len(match.group(1))
                    name = match.group(2)
                    is_async = 'async' in line
                    
                    # Find end of function/class
                    end_line = i + 1
                    for j in range(i + 1, len(lines)):
                        if lines[j].strip() and not lines[j].startswith(' ' * (indent + 1)):
                            if not lines[j].startswith(' ' * indent + ' '):
                                end_line = j
                                break
                    else:
                        end_line = len(lines)
                    
                    # Extract body
                    body = '\n'.join(lines[i:end_line])
                    
                    # Extract docstring
                    docstring = None
                    doc_match = re.search(r'"""(.*?)"""', body, re.DOTALL)
                    if doc_match:
                        docstring = doc_match.group(1).strip()
                    
                    # Extract decorators
                    decorators = []
                    for k in range(i - 1, max(0, i - 5), -1):
                        if lines[k].strip().startswith('@'):
                            decorators.append(lines[k].strip())
                        elif lines[k].strip():
                            break
                    
                    func = ProjectFunction(
                        file_id=file_record.id,
                        project_id=project.id,
                        name=name,
                        type=func_type,
                        signature=line.strip(),
                        docstring=docstring,
                        body=body,
                        line_start=i + 1,
                        line_end=end_line,
                        decorators=decorators,
                        is_async=is_async,
                        is_exported=not name.startswith('_'),
                    )
                    
                    if generate_embeddings:
                        try:
                            embed_text = f"{name}\n{docstring or ''}\n{body[:1000]}"
                            embedding = await self.embedding_provider.embed(embed_text)
                            func.embedding = embedding
                        except:
                            pass
                    
                    self.db.add(func)
                    functions.append(func)
        
        await self.db.flush()
        return functions

    async def _extract_js_functions(
        self,
        project: Project,
        file_record: ProjectFile,
        content: str,
        generate_embeddings: bool,
    ) -> list[ProjectFunction]:
        """Extract JavaScript/TypeScript functions."""
        functions = []
        lines = content.split('\n')
        
        patterns = [
            (r'^\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)', 'function'),
            (r'^\s*(?:export\s+)?const\s+(\w+)\s*=\s*(?:async\s+)?\(', 'function'),
            (r'^\s*(?:export\s+)?class\s+(\w+)', 'class'),
            (r'^\s*(?:export\s+)?interface\s+(\w+)', 'interface'),
            (r'^\s*(?:export\s+)?type\s+(\w+)', 'type'),
        ]
        
        for i, line in enumerate(lines):
            for pattern, func_type in patterns:
                match = re.match(pattern, line)
                if match:
                    name = match.group(1)
                    is_async = 'async' in line
                    is_exported = 'export' in line
                    
                    # Simple end detection (count braces)
                    brace_count = 0
                    end_line = i
                    for j in range(i, len(lines)):
                        brace_count += lines[j].count('{') - lines[j].count('}')
                        if brace_count <= 0 and j > i:
                            end_line = j + 1
                            break
                    else:
                        end_line = len(lines)
                    
                    body = '\n'.join(lines[i:end_line])
                    
                    func = ProjectFunction(
                        file_id=file_record.id,
                        project_id=project.id,
                        name=name,
                        type=func_type,
                        signature=line.strip(),
                        body=body,
                        line_start=i + 1,
                        line_end=end_line,
                        is_async=is_async,
                        is_exported=is_exported,
                    )
                    
                    if generate_embeddings:
                        try:
                            embed_text = f"{name}\n{body[:1000]}"
                            embedding = await self.embedding_provider.embed(embed_text)
                            func.embedding = embedding
                        except:
                            pass
                    
                    self.db.add(func)
                    functions.append(func)
        
        await self.db.flush()
        return functions

    async def get_project_context(
        self,
        project_id: str,
        include_files: bool = True,
        include_functions: bool = True,
    ) -> dict[str, Any]:
        """Get full project context for AI."""
        stmt = select(Project).where(Project.id == UUID(project_id))
        result = await self.db.execute(stmt)
        project = result.scalar_one_or_none()
        
        if not project:
            return {"error": f"Project {project_id} not found"}
        
        context = {
            "project": {
                "id": str(project.id),
                "name": project.name,
                "path": project.path,
                "description": project.description,
                "tech_stack": project.tech_stack,
                "frameworks": project.frameworks,
                "languages": project.languages,
                "total_files": project.total_files,
                "total_lines": project.total_lines,
            },
            "modules": [],
            "files": [],
            "functions": [],
        }
        
        # Get modules
        stmt = select(ProjectModule).where(ProjectModule.project_id == project.id)
        result = await self.db.execute(stmt)
        modules = result.scalars().all()
        
        context["modules"] = [
            {
                "id": str(m.id),
                "name": m.name,
                "type": m.module_type,
                "path": m.path,
                "tech_stack": m.tech_stack,
                "frameworks": m.frameworks,
                "languages": m.languages,
            }
            for m in modules
        ]
        
        if include_files:
            stmt = select(ProjectFile).where(ProjectFile.project_id == project.id)
            result = await self.db.execute(stmt)
            files = result.scalars().all()
            
            context["files"] = [
                {
                    "id": str(f.id),
                    "name": f.name,
                    "path": f.relative_path,
                    "language": f.language,
                    "lines": f.line_count,
                    "imports": f.imports,
                    "summary": f.summary,
                }
                for f in files
            ]
        
        if include_functions:
            stmt = select(ProjectFunction).where(ProjectFunction.project_id == project.id)
            result = await self.db.execute(stmt)
            functions = result.scalars().all()
            
            context["functions"] = [
                {
                    "id": str(fn.id),
                    "name": fn.name,
                    "type": fn.type,
                    "signature": fn.signature,
                    "docstring": fn.docstring,
                    "line_start": fn.line_start,
                    "line_end": fn.line_end,
                    "is_async": fn.is_async,
                    "is_exported": fn.is_exported,
                }
                for fn in functions
            ]
        
        return context

    async def search_code(
        self,
        project_id: str,
        query: str,
        search_type: str = "all",  # all | files | functions
        top_k: int = 10,
    ) -> dict[str, Any]:
        """Semantic search across project code."""
        try:
            query_embedding = await self.embedding_provider.embed(query)
        except Exception as e:
            return {"error": f"Embedding failed: {e}"}
        
        results = {"files": [], "functions": []}
        
        if search_type in ("all", "files"):
            from sqlalchemy import text
            stmt = text("""
                SELECT id, name, relative_path, language, line_count, summary,
                       1 - (embedding <=> :embedding) as similarity
                FROM project_files
                WHERE project_id = :project_id AND embedding IS NOT NULL
                ORDER BY embedding <=> :embedding
                LIMIT :limit
            """)
            result = await self.db.execute(stmt, {
                "project_id": project_id,
                "embedding": str(query_embedding),
                "limit": top_k
            })
            rows = result.fetchall()
            results["files"] = [
                {
                    "id": str(r[0]),
                    "name": r[1],
                    "path": r[2],
                    "language": r[3],
                    "lines": r[4],
                    "summary": r[5],
                    "similarity": float(r[6]) if r[6] else 0,
                }
                for r in rows
            ]
        
        if search_type in ("all", "functions"):
            from sqlalchemy import text
            stmt = text("""
                SELECT id, name, type, signature, docstring, line_start, line_end,
                       1 - (embedding <=> :embedding) as similarity
                FROM project_functions
                WHERE project_id = :project_id AND embedding IS NOT NULL
                ORDER BY embedding <=> :embedding
                LIMIT :limit
            """)
            result = await self.db.execute(stmt, {
                "project_id": project_id,
                "embedding": str(query_embedding),
                "limit": top_k
            })
            rows = result.fetchall()
            results["functions"] = [
                {
                    "id": str(r[0]),
                    "name": r[1],
                    "type": r[2],
                    "signature": r[3],
                    "docstring": r[4],
                    "line_start": r[5],
                    "line_end": r[6],
                    "similarity": float(r[7]) if r[7] else 0,
                }
                for r in rows
            ]
        
        return results


    # ─── Remote-first methods (no filesystem access needed) ───

    async def push_files(
        self,
        project_id: str,
        files: list[dict[str, Any]],
        generate_embeddings: bool = True,
    ) -> dict[str, Any]:
        """Push file contents from remote client.

        Each file dict: {path: str, content: str, language?: str}
        Server stores in DB, extracts functions, generates embeddings.
        No filesystem access required.
        """
        stmt = select(Project).where(Project.id == UUID(project_id))
        result = await self.db.execute(stmt)
        project = result.scalar_one_or_none()

        if not project:
            return {"error": f"Project {project_id} not found"}

        project.analysis_status = "analyzing"
        await self.db.flush()

        stats = {
            "files_pushed": 0,
            "files_skipped": 0,
            "functions_extracted": 0,
            "total_lines": 0,
            "languages": set(),
            "errors": [],
        }

        for file_data in files:
            rel_path = file_data.get("path", "")
            content = file_data.get("content", "")
            if not rel_path or content is None:
                stats["files_skipped"] += 1
                continue

            ext = Path(rel_path).suffix.lower()
            if ext not in CODE_EXTENSIONS:
                stats["files_skipped"] += 1
                continue

            language = file_data.get("language") or LANG_BY_EXT.get(ext)

            try:
                file_record = await self._push_single_file(
                    project=project,
                    rel_path=rel_path,
                    content=content,
                    language=language,
                    generate_embeddings=generate_embeddings,
                )
                if file_record:
                    stats["files_pushed"] += 1
                    stats["total_lines"] += file_record.line_count
                    if file_record.language:
                        stats["languages"].add(file_record.language)

                    funcs = await self._extract_functions(
                        project=project,
                        file_record=file_record,
                        generate_embeddings=generate_embeddings,
                    )
                    stats["functions_extracted"] += len(funcs)
            except Exception as e:
                stats["errors"].append(f"{rel_path}: {str(e)}")
                logger.warning("Error pushing file %s: %s", rel_path, e)

        # Recompute project-wide totals from DB
        await self._recompute_project_stats(project)
        await self.db.flush()

        return {
            "project_id": str(project.id),
            "status": "ok",
            "batch_stats": {
                "files_pushed": stats["files_pushed"],
                "files_skipped": stats["files_skipped"],
                "functions_extracted": stats["functions_extracted"],
                "lines_in_batch": stats["total_lines"],
                "languages": list(stats["languages"]),
                "errors_count": len(stats["errors"]),
            },
            "project_totals": {
                "total_files": project.total_files,
                "total_lines": project.total_lines,
                "languages": project.languages,
            },
        }

    async def push_structure(
        self,
        project_id: str,
        *,
        tech_stack: list[str] | None = None,
        frameworks: list[str] | None = None,
        languages: list[str] | None = None,
        databases: list[str] | None = None,
        build_tools: list[str] | None = None,
        architecture_type: str | None = None,
        description: str | None = None,
        modules: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Push project structure/metadata from remote client.

        Client analyses its local project and sends metadata.
        No filesystem access required on server side.
        """
        stmt = select(Project).where(Project.id == UUID(project_id))
        result = await self.db.execute(stmt)
        project = result.scalar_one_or_none()

        if not project:
            return {"error": f"Project {project_id} not found"}

        if tech_stack is not None:
            project.tech_stack = tech_stack
        if frameworks is not None:
            project.frameworks = frameworks
        if languages is not None:
            project.languages = languages
        if databases is not None:
            project.databases = databases
        if build_tools is not None:
            project.build_tools = build_tools
        if architecture_type is not None:
            project.architecture_type = architecture_type
        if description is not None:
            project.description = description

        # Create modules if provided
        modules_created = 0
        if modules:
            for mod in modules:
                mod_name = mod.get("name", "")
                if not mod_name:
                    continue
                # Upsert: skip if exists
                existing = await self.db.execute(
                    select(ProjectModule).where(
                        ProjectModule.project_id == project.id,
                        ProjectModule.name == mod_name,
                    )
                )
                if existing.scalar_one_or_none():
                    continue
                m = ProjectModule(
                    project_id=project.id,
                    name=mod_name,
                    module_type=mod.get("type", "shared"),
                    path=mod.get("path", mod_name),
                    tech_stack=mod.get("tech_stack", []),
                    frameworks=mod.get("frameworks", []),
                    languages=mod.get("languages", []),
                )
                self.db.add(m)
                modules_created += 1

        project.analysis_status = "completed"
        project.last_analyzed = datetime.now(timezone.utc)
        await self.db.flush()

        return {
            "project_id": str(project.id),
            "status": "ok",
            "modules_created": modules_created,
            "message": "Project structure updated",
        }

    async def finalize_push(self, project_id: str) -> dict[str, Any]:
        """Mark push-based indexing as completed and recompute stats."""
        stmt = select(Project).where(Project.id == UUID(project_id))
        result = await self.db.execute(stmt)
        project = result.scalar_one_or_none()

        if not project:
            return {"error": f"Project {project_id} not found"}

        await self._recompute_project_stats(project)
        project.analysis_status = "completed"
        project.last_analyzed = datetime.now(timezone.utc)
        await self.db.flush()

        return {
            "project_id": str(project.id),
            "status": "completed",
            "total_files": project.total_files,
            "total_lines": project.total_lines,
            "languages": project.languages,
        }

    async def _push_single_file(
        self,
        project: Project,
        rel_path: str,
        content: str,
        language: str | None,
        generate_embeddings: bool,
    ) -> ProjectFile | None:
        """Store a single file from pushed content (no filesystem access)."""
        ext = Path(rel_path).suffix.lower()
        lines = content.count("\n") + 1
        content_hash = hashlib.sha256(content.encode()).hexdigest()

        # Check if already indexed with same hash
        stmt = select(ProjectFile).where(
            and_(
                ProjectFile.project_id == project.id,
                ProjectFile.relative_path == rel_path,
            )
        )
        result = await self.db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing and existing.content_hash == content_hash:
            return existing  # unchanged

        imports = self._extract_imports(content, language)

        if existing:
            file_record = existing
            file_record.content = content
            file_record.content_hash = content_hash
            file_record.line_count = lines
            file_record.size_bytes = len(content.encode())
            file_record.language = language
            file_record.imports = imports
            file_record.last_indexed = datetime.now(timezone.utc)
        else:
            file_record = ProjectFile(
                project_id=project.id,
                name=Path(rel_path).name,
                path=rel_path,
                relative_path=rel_path,
                language=language,
                file_extension=ext,
                content=content,
                content_hash=content_hash,
                size_bytes=len(content.encode()),
                line_count=lines,
                imports=imports,
                last_indexed=datetime.now(timezone.utc),
            )
            self.db.add(file_record)

        if generate_embeddings and content:
            try:
                embed_text = f"{rel_path}\n{content[:2000]}"
                embedding = await self.embedding_provider.embed(embed_text)
                file_record.embedding = embedding
            except Exception as e:
                logger.warning("Embedding failed for %s: %s", rel_path, e)

        await self.db.flush()
        return file_record

    async def _recompute_project_stats(self, project: Project) -> None:
        """Recompute project-wide stats from project_files table."""
        from sqlalchemy import func as sa_func

        row = (
            await self.db.execute(
                select(
                    sa_func.count(ProjectFile.id),
                    sa_func.coalesce(sa_func.sum(ProjectFile.line_count), 0),
                ).where(ProjectFile.project_id == project.id)
            )
        ).one()

        project.total_files = row[0]
        project.total_lines = row[1]

        # Collect unique languages
        lang_rows = (
            await self.db.execute(
                select(ProjectFile.language)
                .where(
                    ProjectFile.project_id == project.id,
                    ProjectFile.language.isnot(None),
                )
                .distinct()
            )
        ).scalars().all()
        project.languages = [l for l in lang_rows if l]


class IDESessionService:
    """Service for IDE session tracking."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def start_session(
        self,
        ide_name: str,
        project_id: str | None = None,
        model_name: str | None = None,
        model_provider: str | None = None,
        ide_version: str | None = None,
        user_id: str | None = None,
        machine_id: str | None = None,
    ) -> dict[str, Any]:
        """Start a new IDE session."""
        session = IDESession(
            project_id=UUID(project_id) if project_id else None,
            ide_name=ide_name,
            ide_version=ide_version,
            model_name=model_name,
            model_provider=model_provider,
            user_id=user_id,
            machine_id=machine_id,
            is_active=True,
        )
        self.db.add(session)
        await self.db.flush()
        
        return {
            "session_id": str(session.id),
            "ide_name": session.ide_name,
            "model_name": session.model_name,
            "started_at": session.started_at.isoformat(),
        }

    async def end_session(self, session_id: str) -> dict[str, Any]:
        """End an IDE session."""
        stmt = select(IDESession).where(IDESession.id == UUID(session_id))
        result = await self.db.execute(stmt)
        session = result.scalar_one_or_none()
        
        if not session:
            return {"error": "Session not found"}
        
        session.is_active = False
        session.ended_at = datetime.now(timezone.utc)
        await self.db.flush()
        
        return {
            "session_id": str(session.id),
            "ended_at": session.ended_at.isoformat(),
        }

    async def log_change(
        self,
        project_id: str,
        file_path: str,
        change_type: str,
        session_id: str | None = None,
        old_content: str | None = None,
        new_content: str | None = None,
        diff: str | None = None,
        ide_name: str | None = None,
        model_name: str | None = None,
        model_provider: str | None = None,
        prompt_used: str | None = None,
        reason: str | None = None,
        commit_hash: str | None = None,
        commit_message: str | None = None,
        branch_name: str | None = None,
    ) -> dict[str, Any]:
        """Log a code change."""
        lines_added = 0
        lines_removed = 0
        
        if old_content and new_content:
            old_lines = set(old_content.split('\n'))
            new_lines = set(new_content.split('\n'))
            lines_added = len(new_lines - old_lines)
            lines_removed = len(old_lines - new_lines)
        
        change = ChangeLog(
            project_id=UUID(project_id),
            ide_session_id=UUID(session_id) if session_id else None,
            change_type=change_type,
            file_path=file_path,
            old_content=old_content,
            new_content=new_content,
            diff=diff,
            lines_added=lines_added,
            lines_removed=lines_removed,
            ide_name=ide_name,
            model_name=model_name,
            model_provider=model_provider,
            prompt_used=prompt_used,
            reason=reason,
            commit_hash=commit_hash,
            commit_message=commit_message,
            branch_name=branch_name,
        )
        self.db.add(change)
        await self.db.flush()
        
        return {
            "change_id": str(change.id),
            "change_type": change.change_type,
            "file_path": change.file_path,
            "lines_added": lines_added,
            "lines_removed": lines_removed,
            "created_at": change.created_at.isoformat(),
        }

    async def get_changes_since(
        self,
        project_id: str,
        since: datetime | None = None,
        commit_hash: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Get changes since a point in time or commit."""
        conditions = [ChangeLog.project_id == UUID(project_id)]
        
        if since:
            conditions.append(ChangeLog.created_at >= since)
        
        stmt = (
            select(ChangeLog)
            .where(and_(*conditions))
            .order_by(ChangeLog.created_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        changes = result.scalars().all()
        
        return {
            "project_id": project_id,
            "changes_count": len(changes),
            "changes": [
                {
                    "id": str(c.id),
                    "type": c.change_type,
                    "file_path": c.file_path,
                    "lines_added": c.lines_added,
                    "lines_removed": c.lines_removed,
                    "ide_name": c.ide_name,
                    "model_name": c.model_name,
                    "reason": c.reason,
                    "commit_hash": c.commit_hash,
                    "created_at": c.created_at.isoformat(),
                }
                for c in changes
            ]
        }

    async def sync_from_git(
        self,
        project_id: str,
        project_path: str,
    ) -> dict[str, Any]:
        """Sync changes from git history."""
        import subprocess
        
        resolved_path = translate_path(project_path)
        
        try:
            # Get recent commits
            result = subprocess.run(
                ['git', 'log', '--oneline', '-20', '--format=%H|%s|%an|%ai'],
                cwd=resolved_path,
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                return {"error": "Git command failed", "details": result.stderr}
            
            commits = []
            for line in result.stdout.strip().split('\n'):
                if '|' in line:
                    parts = line.split('|')
                    if len(parts) >= 4:
                        commits.append({
                            "hash": parts[0],
                            "message": parts[1],
                            "author": parts[2],
                            "date": parts[3],
                        })
            
            # Get changed files for each commit
            synced = 0
            for commit in commits[:10]:  # Limit to 10 commits
                diff_result = subprocess.run(
                    ['git', 'diff-tree', '--no-commit-id', '--name-status', '-r', commit['hash']],
                    cwd=resolved_path,
                    capture_output=True,
                    text=True
                )
                
                for line in diff_result.stdout.strip().split('\n'):
                    if '\t' in line:
                        status, filepath = line.split('\t', 1)
                        change_type = {
                            'A': 'create', 'M': 'update', 'D': 'delete',
                            'R': 'rename', 'C': 'create'
                        }.get(status[0], 'update')
                        
                        # Check if already logged
                        stmt = select(ChangeLog).where(
                            and_(
                                ChangeLog.project_id == UUID(project_id),
                                ChangeLog.commit_hash == commit['hash'],
                                ChangeLog.file_path == filepath
                            )
                        )
                        result = await self.db.execute(stmt)
                        if not result.scalar_one_or_none():
                            change = ChangeLog(
                                project_id=UUID(project_id),
                                change_type=change_type,
                                file_path=filepath,
                                commit_hash=commit['hash'],
                                commit_message=commit['message'],
                            )
                            self.db.add(change)
                            synced += 1
            
            await self.db.flush()
            
            return {
                "project_id": project_id,
                "commits_processed": len(commits),
                "changes_synced": synced,
            }
        
        except Exception as e:
            return {"error": str(e)}
