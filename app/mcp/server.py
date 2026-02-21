"""MCP Server — exposes brain tools via Model Context Protocol."""

from __future__ import annotations

import logging
import uuid
import asyncio
from typing import Any

import anyio
from fastmcp import FastMCP
from fastapi import FastAPI, Request
from mcp import types as mcp_types
from pydantic import ValidationError
from starlette.responses import Response

from app.config.settings import get_settings
from app.db.session import _get_session_factory
from app.memory.embeddings import get_embedding_provider
from app.memory.short_term import ShortTermMemory
from app.services.agent_service import AgentService
from app.services.memory_service import MemoryService

logger = logging.getLogger(__name__)

# Shared Redis client — avoids creating new connections per request (#3 fix)
_shared_short_term: ShortTermMemory | None = None
_MCP_CONTEXT_CACHE_KEY = "mcp:active:context"
_MCP_CONTEXT_TTL_SECONDS = 60 * 60 * 24 * 7  # 7 days


def _get_short_term() -> ShortTermMemory:
    """Return the shared ShortTermMemory singleton."""
    global _shared_short_term
    if _shared_short_term is None:
        _shared_short_term = ShortTermMemory()
    return _shared_short_term


async def close_shared_short_term() -> None:
    """Shutdown hook: close the shared Redis client."""
    global _shared_short_term
    if _shared_short_term is not None:
        await _shared_short_term.close()
        _shared_short_term = None


async def _get_active_mcp_context() -> dict[str, Any]:
    """Read active MCP context from Redis cache."""
    short_term = _get_short_term()
    ctx = await short_term.cache_get(_MCP_CONTEXT_CACHE_KEY)
    if isinstance(ctx, dict):
        return ctx
    return {}


async def _set_active_mcp_context(context: dict[str, Any], ttl: int = _MCP_CONTEXT_TTL_SECONDS) -> dict[str, Any]:
    """Persist active MCP context to Redis cache."""
    short_term = _get_short_term()
    cleaned = {
        key: value
        for key, value in context.items()
        if value is not None and value != ""
    }
    if ttl < 60:
        ttl = 60
    await short_term.cache_set(_MCP_CONTEXT_CACHE_KEY, cleaned, ttl=ttl)
    return cleaned


async def _clear_active_mcp_context() -> bool:
    """Clear active MCP context from Redis cache."""
    short_term = _get_short_term()
    return await short_term.cache_delete(_MCP_CONTEXT_CACHE_KEY)


# Whitelist of tables allowed in db_query (#1 fix)
_ALLOWED_TABLES = frozenset({
    "agents", "sessions", "messages", "memories",
    "tools", "tool_calls", "orchestration_runs", "orchestration_steps",
})
_MAX_QUERY_LENGTH = 2000
_MAX_RESULT_ROWS = 100

_DISCONNECT_EXCEPTIONS = (
    anyio.BrokenResourceError,
    anyio.EndOfStream,
    anyio.ClosedResourceError,
    asyncio.CancelledError,
)


def _iter_leaf_exceptions(exc: BaseException):
    """Yield non-group exceptions from nested exception groups."""
    if isinstance(exc, BaseExceptionGroup):
        for inner in exc.exceptions:
            yield from _iter_leaf_exceptions(inner)
        return
    yield exc


def _is_expected_disconnect(exc: BaseException) -> bool:
    """True when all leaf exceptions represent client disconnect/cancel events."""
    leaves = tuple(_iter_leaf_exceptions(exc))
    return bool(leaves) and all(isinstance(leaf, _DISCONNECT_EXCEPTIONS) for leaf in leaves)

# Create the MCP server instance using FastMCP
mcp = FastMCP("agent-brain")


@mcp.tool(name="context_set")
async def context_set(
    agent_id: str | None = None,
    project_id: str | None = None,
    session_id: str | None = None,
    ttl_seconds: int = _MCP_CONTEXT_TTL_SECONDS,
) -> Any:
    """When to use:
    Set or update default IDs for the current MCP workflow.

    Inputs:
    - agent_id: Optional UUID for agent-scoped tools.
    - project_id: Optional project UUID for project/graph tools.
    - session_id: Optional UUID for conversation continuity.
    - ttl_seconds: Context TTL in seconds.

    Returns:
    - context: Stored context dictionary.
    - ttl_seconds: Effective TTL.

    Common mistakes:
    - Passing invalid UUID strings for agent_id/project_id/session_id.
    """
    try:
        if agent_id:
            uuid.UUID(agent_id)
        if project_id:
            uuid.UUID(project_id)
        if session_id:
            uuid.UUID(session_id)
    except ValueError as e:
        return {
            "error": (
                f"Invalid UUID in context: {e}. "
                "Expected UUID format for agent_id/project_id/session_id."
            )
        }

    current = await _get_active_mcp_context()
    current.update(
        {
            "agent_id": agent_id,
            "project_id": project_id,
            "session_id": session_id,
        }
    )
    context = await _set_active_mcp_context(current, ttl=ttl_seconds)
    return {"context": context, "ttl_seconds": ttl_seconds}


@mcp.tool(name="context_get")
async def context_get() -> Any:
    """When to use:
    Inspect current auto-context before tool calls.

    Inputs:
    - None.

    Returns:
    - context: Current context dictionary.

    Common mistakes:
    - Assuming context exists without checking.
    """
    context = await _get_active_mcp_context()
    return {"context": context}


@mcp.tool(name="context_clear")
async def context_clear() -> Any:
    """When to use:
    Reset context when switching to another agent/project.

    Inputs:
    - None.

    Returns:
    - cleared: True if context key was removed.

    Common mistakes:
    - Forgetting to clear context before unrelated tasks.
    """
    deleted = await _clear_active_mcp_context()
    return {"cleared": bool(deleted)}


@mcp.tool(name="memory_store")
async def store_memory(
    content: str,
    memory_type: str = "general",
    agent_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    importance: int = 5,
) -> Any:
    """When to use:
    Save durable facts, decisions, constraints, and outcomes.

    Inputs:
    - content: Memory text to persist.
    - memory_type: Memory category.
    - agent_id: Optional; auto-filled from context if missing.
    - metadata: Optional extra fields; project_id/session_id auto-injected from context.
    - importance: 1..10 priority.

    Returns:
    - Memory record fields including id and created_at.
    - deduplicated/created flags from memory service.

    Common mistakes:
    - Storing low-signal or duplicate noise instead of concise facts.
    - Omitting context and expecting project/session scoping automatically.
    """
    context = await _get_active_mcp_context()
    effective_agent_id = agent_id or context.get("agent_id")
    effective_metadata = dict(metadata or {})
    if "project_id" not in effective_metadata and context.get("project_id"):
        effective_metadata["project_id"] = context["project_id"]
    if "session_id" not in effective_metadata and context.get("session_id"):
        effective_metadata["session_id"] = context["session_id"]

    factory = _get_session_factory()
    short_term = _get_short_term()
    async with factory() as db:
        svc = MemoryService(db, short_term)
        try:
            parsed_agent_id = uuid.UUID(effective_agent_id) if effective_agent_id else None
        except ValueError as e:
            return {"error": f"Invalid agent_id: {e}"}
        result = await svc.store(
            content=content,
            memory_type=memory_type,
            agent_id=parsed_agent_id,
            metadata=effective_metadata,
            importance=importance,
        )
        await db.commit()
        return result


@mcp.tool(name="memory_search")
async def search_memory(
    query: str,
    agent_id: str | None = None,
    memory_type: str | None = None,
    metadata_filters: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    top_k: int = 10,
    min_similarity: float = 0.0,
) -> Any:
    """When to use:
    Retrieve prior memory context before planning or execution.

    Inputs:
    - query: Search text.
    - agent_id: Optional; auto-filled from context.
    - memory_type: Optional filter.
    - metadata_filters/metadata: Optional scope filters.
    - top_k: Max results.
    - min_similarity: Similarity threshold.

    Returns:
    - List of memory hits ordered by relevance.

    Common mistakes:
    - Skipping this call on stateful tasks and losing continuity.
    - Forgetting scope filters for project-specific retrieval.
    """
    context = await _get_active_mcp_context()
    effective_agent_id = agent_id or context.get("agent_id")

    factory = _get_session_factory()
    short_term = _get_short_term()
    async with factory() as db:
        svc = MemoryService(db, short_term)
        scope_filters = dict(metadata_filters or metadata or {})
        if "project_id" not in scope_filters and context.get("project_id"):
            scope_filters["project_id"] = context["project_id"]
        try:
            parsed_agent_id = uuid.UUID(effective_agent_id) if effective_agent_id else None
        except ValueError as e:
            return {"error": f"Invalid agent_id: {e}"}
        return await svc.search(
            query=query,
            agent_id=parsed_agent_id,
            memory_type=memory_type,
            metadata_filters=scope_filters or None,
            top_k=top_k,
            min_similarity=min_similarity,
        )


@mcp.tool(name="memory_get")
async def get_memory(memory_id: str) -> Any:
    """When to use:
    Fetch exact memory content by known ID.

    Inputs:
    - memory_id: Memory UUID.

    Returns:
    - Full memory record or error if not found.

    Common mistakes:
    - Using approximate recall when exact memory text is required.
    """
    factory = _get_session_factory()
    async with factory() as db:
        svc = MemoryService(db)
        result = await svc.get(uuid.UUID(memory_id))
        if result is None:
            return {"error": "Memory not found"}
        return result


@mcp.tool(name="memory_delete")
async def delete_memory(memory_id: str) -> Any:
    """When to use:
    Remove stale, incorrect, or unsafe memory from active use.

    Inputs:
    - memory_id: Memory UUID.

    Returns:
    - deleted: Boolean result.

    Common mistakes:
    - Keeping known-bad memory active after confirming it is wrong.
    """
    factory = _get_session_factory()
    async with factory() as db:
        svc = MemoryService(db)
        deleted = await svc.delete(uuid.UUID(memory_id))
        await db.commit()
        return {"deleted": deleted}


@mcp.tool(name="memory_reindex")
async def reindex_memory(
    limit: int = 100,
    agent_id: str | None = None,
    memory_type: str | None = None,
    metadata_filters: dict[str, Any] | None = None,
    dry_run: bool = False,
) -> Any:
    """When to use:
    Regenerate missing embeddings after outages or degraded search quality.

    Inputs:
    - limit: Max rows to process.
    - agent_id: Optional scope; auto-filled from context.
    - memory_type: Optional scope.
    - metadata_filters: Optional scope; project_id auto-filled from context.
    - dry_run: If true, report candidates without writing.

    Returns:
    - Reindex report with scanned/reindexed/failed counts.

    Common mistakes:
    - Running large writes without dry_run first.
    """
    context = await _get_active_mcp_context()
    effective_agent_id = agent_id or context.get("agent_id")
    effective_filters = dict(metadata_filters or {})
    if "project_id" not in effective_filters and context.get("project_id"):
        effective_filters["project_id"] = context["project_id"]

    factory = _get_session_factory()
    short_term = _get_short_term()
    async with factory() as db:
        svc = MemoryService(db, short_term)
        try:
            parsed_agent_id = uuid.UUID(effective_agent_id) if effective_agent_id else None
        except ValueError as e:
            return {"error": f"Invalid agent_id: {e}"}
        result = await svc.reindex_embeddings(
            limit=limit,
            agent_id=parsed_agent_id,
            memory_type=memory_type,
            metadata_filters=effective_filters or None,
            dry_run=dry_run,
        )
        await db.commit()
        return result


@mcp.tool(name="agent_run")
async def run_agent(
    input: str,
    agent_id: str | None = None,
    session_id: str | None = None,
) -> Any:
    """When to use:
    Execute a real task through the configured agent runtime.

    Inputs:
    - input: User/task instruction.
    - agent_id: Optional; auto-filled from context.
    - session_id: Optional; auto-filled from context.

    Returns:
    - Agent output, message trace, tool calls, and effective session identifiers.

    Common mistakes:
    - Calling without agent_id and without context_set.
    - Treating this as simulation instead of state-mutating execution.
    """
    context = await _get_active_mcp_context()
    effective_agent_id = agent_id or context.get("agent_id")
    if not effective_agent_id:
        return {"error": "agent_id is required (pass explicitly or set via context_set)"}
    effective_session_id = session_id or context.get("session_id")

    factory = _get_session_factory()
    short_term = _get_short_term()
    async with factory() as db:
        svc = AgentService(db, short_term)
        try:
            parsed_agent_id = uuid.UUID(effective_agent_id)
            parsed_session_id = (
                uuid.UUID(effective_session_id) if effective_session_id else None
            )
        except ValueError as e:
            return {"error": f"Invalid UUID: {e}"}
        result = await svc.run_agent(
            agent_id=parsed_agent_id,
            input_text=input,
            session_id=parsed_session_id,
        )
        next_context = await _get_active_mcp_context()
        next_context["agent_id"] = result.get("agent_id")
        next_context["session_id"] = result.get("session_id")
        await _set_active_mcp_context(next_context)
        await db.commit()
        return result


@mcp.tool(name="agent_get_state")
async def get_agent_state(agent_id: str | None = None) -> Any:
    """When to use:
    Read latest agent state before resume, debug, or delegation.

    Inputs:
    - agent_id: Optional; auto-filled from context.

    Returns:
    - Agent state dictionary or not-found error.

    Common mistakes:
    - Assuming last state without reading it first.
    """
    context = await _get_active_mcp_context()
    effective_agent_id = agent_id or context.get("agent_id")
    if not effective_agent_id:
        return {"error": "agent_id is required (pass explicitly or set via context_set)"}

    factory = _get_session_factory()
    async with factory() as db:
        svc = AgentService(db)
        try:
            parsed_agent_id = uuid.UUID(effective_agent_id)
        except ValueError as e:
            return {"error": f"Invalid agent_id: {e}"}
        state = await svc.get_agent_state(parsed_agent_id)
        return state or {"error": "Agent not found"}


@mcp.tool(name="db_query")
async def query_db(sql: str) -> Any:
    """When to use:
    Verify facts directly from database truth.

    Inputs:
    - sql: Read-only SELECT statement.

    Returns:
    - columns/rows/count/truncated payload.

    Common mistakes:
    - Sending non-SELECT SQL or querying non-whitelisted tables.
    - Including multiple statements or blocked clauses.
    """
    import re

    sql = sql.strip()
    if len(sql) > _MAX_QUERY_LENGTH:
        return {"error": f"Query too long (max {_MAX_QUERY_LENGTH} chars)"}

    # Allow optional trailing semicolon(s), but disallow internal statement separators.
    sql = re.sub(r";+\s*$", "", sql).strip()
    if not sql:
        return {"error": "Empty SQL query"}
    if ";" in sql:
        return {
            "error": (
                "Multiple statements are not allowed. "
                "Send exactly one SELECT statement."
            )
        }

    sql_upper = sql.upper()
    if not sql_upper.startswith("SELECT"):
        return {
            "error": (
                "Only SELECT queries are allowed in db_query. "
                "For project data use project_list/project_components/project_analyze/project_graph_* tools."
            )
        }

    # Block dangerous keywords using word boundaries
    dangerous = [
        "DROP", "DELETE", "INSERT", "UPDATE", "ALTER", "CREATE",
        "TRUNCATE", "EXEC", "GRANT", "REVOKE", "COPY",
    ]
    for kw in dangerous:
        if re.search(rf"\b{kw}\b", sql_upper):
            return {
                "error": (
                    f"Forbidden keyword: {kw}. "
                    "db_query supports read-only SELECT checks only."
                )
            }

    # Block subqueries, unions, CTEs.
    for blocked in ["UNION", "INTO", "RETURNING", "WITH"]:
        if re.search(rf"\b{blocked}\b", sql_upper):
            return {
                "error": (
                    f"Forbidden clause: {blocked}. "
                    "Use a simple single-table SELECT or dedicated MCP tools."
                )
            }

    # Table whitelist: extract FROM/JOIN targets
    table_refs = re.findall(
        r'(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_]*)', sql, re.IGNORECASE
    )
    for table in table_refs:
        if table.lower() not in _ALLOWED_TABLES:
            return {
                "error": (
                    f"Table not allowed: {table}. "
                    "Use project_list/project_components/project_analyze/project_graph_* tools for project entities."
                )
            }

    factory = _get_session_factory()
    async with factory() as db:
        from sqlalchemy import text
        result = await db.execute(text(sql))
        rows = result.fetchmany(_MAX_RESULT_ROWS)
        columns = list(result.keys()) if rows else []
        return {
            "columns": columns,
            "rows": [dict(zip(columns, row)) for row in rows],
            "count": len(rows),
            "truncated": len(rows) == _MAX_RESULT_ROWS,
        }


@mcp.tool(name="embeddings_create")
async def create_embeddings(text: str) -> Any:
    """When to use:
    Build semantic vectors for custom matching and ranking workflows.

    Inputs:
    - text: Raw text to embed.

    Returns:
    - embedding vector, dimension, provider.

    Common mistakes:
    - Comparing semantic similarity without vectorizing both sides.
    """
    provider = get_embedding_provider()
    embedding = await provider.embed(text)
    return {
        "embedding": embedding,
        "dimension": len(embedding),
        "provider": get_settings().embedding_provider,
    }


@mcp.tool(name="orchestration_run")
async def run_orchestration(
    input: str,
    workflow: str | None = None,
    auto_route: bool = False,
) -> Any:
    """When to use:
    Run multi-step workflows with routing, retries, and coordination.

    Inputs:
    - input: Workflow task description.
    - workflow: Optional workflow name.
    - auto_route: Let system pick workflow automatically.

    Returns:
    - run_id, status, and workflow result.

    Common mistakes:
    - Manually simulating orchestration in a single agent call.
    """
    from app.orchestration.service import OrchestrationService
    factory = _get_session_factory()
    short_term = _get_short_term()
    async with factory() as db:
        orch_svc = OrchestrationService(db, short_term)
        result = await orch_svc.start_run(
            workflow_name=workflow,
            input_text=input,
            auto_route=auto_route,
        )
        await db.commit()
        return {
            "run_id": result.get("run_id"),
            "status": result.get("status"),
            "result": result.get("result"),
        }


@mcp.tool(name="project_analyze")
async def analyze_project(
    project_path: str,
    project_name: str | None = None,
    force_reindex: bool = False,
) -> Any:
    """When to use:
    Ingest or refresh project structure in Postgres.
    Works in two modes:
    - LOCAL: If project_path is accessible on the server filesystem, indexes directly.
    - REMOTE: If path is not accessible (remote MCP), creates the project record and
      returns instructions to use project_push_files for remote indexing.

    Inputs:
    - project_path: Filesystem path to project root (on your local machine).
    - project_name: Optional display name.
    - force_reindex: Rebuild existing project records.

    Returns:
    - project_id, analysis status/timestamp, summary, metadata.
    - If remote mode: instructions to use project_push_files workflow.

    Common mistakes:
    - Skipping analysis and expecting graph tools to work on an unknown project.
    """
    import os
    from app.paths import resolve_project_path
    from app.services.project_service import ProjectService

    resolved = resolve_project_path(project_path)
    is_local = resolved.resolved_path.exists() and resolved.resolved_path.is_dir()

    if is_local:
        # LOCAL mode: filesystem accessible, use full indexer
        from app.indexing import ProjectIndexer

        factory = _get_session_factory()
        async with factory() as db:
            indexer = ProjectIndexer(db)
            project = await indexer.index_project(
                project_path=project_path,
                project_name=project_name,
                force_reindex=force_reindex,
            )
            ctx = await _get_active_mcp_context()
            ctx["project_id"] = str(project.id)
            await _set_active_mcp_context(ctx)
            summary = await indexer.get_project_summary(str(project.id))
            return {
                "project_id": str(project.id),
                "project_name": project.name,
                "analysis_status": project.analysis_status,
                "analysis_timestamp": project.last_analyzed.isoformat()
                if project.last_analyzed
                else "",
                "summary": summary,
                "metadata": {
                    "total_files": project.total_files,
                    "total_lines": project.total_lines,
                    "architecture_type": project.architecture_type,
                    "tech_stack": project.tech_stack,
                    "frameworks": project.frameworks,
                    "languages": project.languages,
                    "databases": project.databases,
                    "build_tools": project.build_tools,
                },
            }
    else:
        # REMOTE mode: path not accessible, create record and guide client
        factory = _get_session_factory()
        async with factory() as db:
            svc = ProjectService(db)
            result = await svc.create_project(
                name=project_name or os.path.basename(project_path.rstrip("/ ")),
                path=project_path,
            )
            await db.commit()

            pid = result.get("project_id", "")
            ctx = await _get_active_mcp_context()
            ctx["project_id"] = pid
            await _set_active_mcp_context(ctx)

            return {
                "project_id": pid,
                "project_name": result.get("name", ""),
                "analysis_status": "pending_remote_push",
                "mode": "remote",
                "message": (
                    "Project path is not accessible on the MCP server filesystem. "
                    "Project record created. To index your project remotely, use these tools:\n"
                    "1. project_push_files(files=[{path, content}, ...]) — send file batches (10-30 files each)\n"
                    "2. project_push_structure(tech_stack, frameworks, ...) — send project metadata\n"
                    "3. project_finalize_push() — finalize indexing"
                ),
            }


@mcp.tool(name="project_list")
async def list_projects(
    limit: int = 50,
    offset: int = 0,
) -> Any:
    """When to use:
    Discover available projects and obtain project_id values.

    Inputs:
    - limit: Max rows.
    - offset: Pagination offset.

    Returns:
    - List of project records.

    Common mistakes:
    - Hardcoding project_id instead of resolving it first.
    """
    from sqlalchemy import select
    from app.core.models import Project

    if limit < 1:
        limit = 1
    if limit > 200:
        limit = 200
    if offset < 0:
        offset = 0

    factory = _get_session_factory()
    async with factory() as db:
        stmt = (
            select(Project)
            .order_by(Project.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await db.execute(stmt)
        projects = result.scalars().all()
        return [
            {
                "id": str(project.id),
                "name": project.name,
                "path": project.path,
                "analysis_status": project.analysis_status,
                "last_analyzed": project.last_analyzed.isoformat()
                if project.last_analyzed
                else None,
                "total_files": project.total_files,
                "total_lines": project.total_lines,
                "architecture_type": project.architecture_type,
                "languages": project.languages,
            }
            for project in projects
        ]


@mcp.tool(name="project_components")
async def list_project_components(
    project_id: str | None = None,
    query: str = "",
    component_type: str | None = None,
    language: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> Any:
    """When to use:
    Resolve component IDs for graph impact/path/neighbors calls.

    Inputs:
    - project_id: Optional; auto-filled from context.
    - query: Name/path search text.
    - component_type/language: Optional filters.
    - limit/offset: Pagination.

    Returns:
    - List of component records with IDs and metrics.

    Common mistakes:
    - Running graph queries with unknown component IDs.
    """
    from app.indexing import ProjectIndexer

    context = await _get_active_mcp_context()
    effective_project_id = project_id or context.get("project_id")
    if not effective_project_id:
        return {"error": "project_id is required (pass explicitly or set via context_set/project_analyze)"}

    if limit < 1:
        limit = 1
    if limit > 500:
        limit = 500
    if offset < 0:
        offset = 0

    factory = _get_session_factory()
    async with factory() as db:
        indexer = ProjectIndexer(db)
        components = await indexer.search_components(
            project_id=effective_project_id,
            query=query,
            component_type=component_type,
            language=language,
            limit=limit,
            offset=offset,
        )
        return [
            {
                "id": str(comp.id),
                "name": comp.name,
                "type": comp.type,
                "path": comp.relative_path,
                "language": comp.language,
                "line_count": comp.line_count,
                "complexity_score": comp.complexity_score,
                "dependencies": comp.dependencies,
                "exports": comp.exports,
            }
            for comp in components
        ]


@mcp.tool(name="project_dependencies_analyze")
async def analyze_project_dependencies(
    project_id: str | None = None,
    include_impact_analysis: bool = True,
    component_id: str | None = None,
) -> Any:
    """When to use:
    Run structural dependency diagnostics for a project.

    Inputs:
    - project_id: Optional; auto-filled from context.
    - include_impact_analysis: Include component impact section.
    - component_id: Target component for impact.

    Returns:
    - Dependency statistics, layers, SCC/cycle signals, optional impact.

    Common mistakes:
    - Expecting component impact without passing component_id.
    """
    from app.dependencies import GraphDependencyService

    context = await _get_active_mcp_context()
    effective_project_id = project_id or context.get("project_id")
    if not effective_project_id:
        return {"error": "project_id is required (pass explicitly or set via context_set/project_analyze)"}

    factory = _get_session_factory()
    async with factory() as db:
        svc = GraphDependencyService(db)
        return await svc.dependencies_analyze_compat(
            project_id=effective_project_id,
            include_impact_analysis=include_impact_analysis,
            component_id=component_id,
        )


@mcp.tool(name="project_graph_sync")
async def sync_project_graph(
    project_id: str | None = None,
    changed_files: list[str] | None = None,
) -> Any:
    """When to use:
    Refresh graph read-model from Postgres source-of-truth.

    Inputs:
    - project_id: Optional; auto-filled from context.
    - changed_files: Optional list for incremental sync.

    Returns:
    - Sync report: mode, nodes/edges, timestamps, backend.

    Common mistakes:
    - Querying graph endpoints before first sync.
    """
    from app.dependencies import GraphDependencyService

    context = await _get_active_mcp_context()
    effective_project_id = project_id or context.get("project_id")
    if not effective_project_id:
        return {"error": "project_id is required (pass explicitly or set via context_set/project_analyze)"}

    factory = _get_session_factory()
    async with factory() as db:
        svc = GraphDependencyService(db)
        result = await svc.sync_project_graph(
            project_id=effective_project_id,
            changed_files=changed_files or [],
        )
        await db.commit()
        context["project_id"] = effective_project_id
        await _set_active_mcp_context(context)
        return result


@mcp.tool(name="project_graph_impact")
async def project_graph_impact(
    component_id: str,
    project_id: str | None = None,
) -> Any:
    """When to use:
    Estimate blast radius of changing one component.

    Inputs:
    - component_id: Target component.
    - project_id: Optional; auto-filled from context.

    Returns:
    - Direct/indirect impact counts and affected components.

    Common mistakes:
    - Running before sync or with unresolved component_id.
    """
    from app.dependencies import GraphDependencyService

    context = await _get_active_mcp_context()
    effective_project_id = project_id or context.get("project_id")
    if not effective_project_id:
        return {"error": "project_id is required (pass explicitly or set via context_set/project_analyze)"}

    factory = _get_session_factory()
    async with factory() as db:
        svc = GraphDependencyService(db)
        return await svc.graph_impact(project_id=effective_project_id, component_id=component_id)


@mcp.tool(name="project_graph_path")
async def project_graph_path(
    from_component_id: str,
    to_component_id: str,
    max_depth: int = 15,
    project_id: str | None = None,
) -> Any:
    """When to use:
    Explain why two components are connected.

    Inputs:
    - from_component_id: Source component.
    - to_component_id: Destination component.
    - max_depth: Path depth bound.
    - project_id: Optional; auto-filled from context.

    Returns:
    - Path payload and found/not-found flags.

    Common mistakes:
    - Using too small max_depth for distant dependencies.
    """
    from app.dependencies import GraphDependencyService

    context = await _get_active_mcp_context()
    effective_project_id = project_id or context.get("project_id")
    if not effective_project_id:
        return {"error": "project_id is required (pass explicitly or set via context_set/project_analyze)"}

    factory = _get_session_factory()
    async with factory() as db:
        svc = GraphDependencyService(db)
        return await svc.graph_path(
            project_id=effective_project_id,
            from_component_id=from_component_id,
            to_component_id=to_component_id,
            max_depth=max_depth,
        )


@mcp.tool(name="project_graph_neighbors")
async def project_graph_neighbors(
    component_id: str,
    project_id: str | None = None,
    depth: int = 1,
) -> Any:
    """When to use:
    Explore local dependency neighborhood around a component.

    Inputs:
    - component_id: Target component.
    - project_id: Optional; auto-filled from context.
    - depth: Traversal radius.

    Returns:
    - Neighbor summary at requested depth.

    Common mistakes:
    - Using large depth by default and overfetching.
    """
    from app.dependencies import GraphDependencyService

    context = await _get_active_mcp_context()
    effective_project_id = project_id or context.get("project_id")
    if not effective_project_id:
        return {"error": "project_id is required (pass explicitly or set via context_set/project_analyze)"}

    factory = _get_session_factory()
    async with factory() as db:
        svc = GraphDependencyService(db)
        return await svc.graph_neighbors(
            project_id=effective_project_id,
            component_id=component_id,
            depth=depth,
        )


# ============================================================================
# NEW: Enhanced Project & IDE Tools
# ============================================================================

@mcp.tool(name="project_create")
async def create_project(
    name: str,
    path: str,
    description: str | None = None,
) -> Any:
    """When to use:
    Create a new project record before indexing.

    Inputs:
    - name: Project display name.
    - path: Filesystem path to project root.
    - description: Optional project description.

    Returns:
    - project_id, status, message.

    Common mistakes:
    - Creating duplicate projects for the same path.
    """
    from app.services.project_service import ProjectService

    factory = _get_session_factory()
    async with factory() as db:
        svc = ProjectService(db)
        result = await svc.create_project(name=name, path=path, description=description)
        await db.commit()
        
        # Set context to new project
        if "project_id" in result:
            context = await _get_active_mcp_context()
            context["project_id"] = result["project_id"]
            await _set_active_mcp_context(context)
        
        return result


@mcp.tool(name="project_full_index")
async def full_index_project(
    project_id: str | None = None,
    include_content: bool = True,
    generate_embeddings: bool = True,
    max_file_size: int = 500000,
) -> Any:
    """When to use:
    Deep index entire project: all files, functions, classes with embeddings.

    Inputs:
    - project_id: Optional; auto-filled from context.
    - include_content: Store full file content (default true).
    - generate_embeddings: Generate semantic embeddings (default true).
    - max_file_size: Skip files larger than this (bytes).

    Returns:
    - Indexing stats: modules, files, functions, lines, languages.

    Common mistakes:
    - Running on huge projects without limiting file size.
    - Forgetting to create project first.
    """
    from app.services.project_service import ProjectService

    context = await _get_active_mcp_context()
    effective_project_id = project_id or context.get("project_id")
    if not effective_project_id:
        return {"error": "project_id is required (pass explicitly or set via context_set/project_create)"}

    factory = _get_session_factory()
    async with factory() as db:
        svc = ProjectService(db)
        result = await svc.full_index_project(
            project_id=effective_project_id,
            include_content=include_content,
            generate_embeddings=generate_embeddings,
            max_file_size=max_file_size,
        )
        await db.commit()
        return result


@mcp.tool(name="project_push_files")
async def push_project_files(
    project_id: str | None = None,
    files: list[dict] | None = None,
    generate_embeddings: bool = True,
) -> Any:
    """When to use:
    Push file contents from your local machine to the remote MCP server for indexing.
    Use this instead of project_full_index when the MCP server cannot access your filesystem
    (i.e., remote/cloud MCP). The IDE reads files locally and sends content via this tool.

    Inputs:
    - project_id: Optional; auto-filled from context.
    - files: List of file dicts, each with {path: str, content: str, language?: str}.
      Send files in batches of 10-30 at a time to avoid timeouts.
    - generate_embeddings: Generate semantic embeddings (default true).

    Returns:
    - Batch stats and updated project totals.

    Typical workflow:
    1. project_create(name, path)
    2. project_push_files(files=[...])  ← repeat in batches
    3. project_push_structure(tech_stack, frameworks, ...)
    4. project_finalize_push()

    Common mistakes:
    - Sending too many files at once (keep batches under 30 files).
    - Forgetting to call project_create first.
    - Sending binary files (only send text/code files).
    """
    from app.services.project_service import ProjectService

    context = await _get_active_mcp_context()
    effective_project_id = project_id or context.get("project_id")
    if not effective_project_id:
        return {"error": "project_id is required (pass explicitly or set via context_set/project_create)"}
    if not files:
        return {"error": "files list is required. Each item: {path: str, content: str, language?: str}"}

    factory = _get_session_factory()
    async with factory() as db:
        svc = ProjectService(db)
        result = await svc.push_files(
            project_id=effective_project_id,
            files=files,
            generate_embeddings=generate_embeddings,
        )
        await db.commit()
        return result


@mcp.tool(name="project_push_structure")
async def push_project_structure(
    project_id: str | None = None,
    tech_stack: list[str] | None = None,
    frameworks: list[str] | None = None,
    languages: list[str] | None = None,
    databases: list[str] | None = None,
    build_tools: list[str] | None = None,
    architecture_type: str | None = None,
    description: str | None = None,
    modules: list[dict] | None = None,
) -> Any:
    """When to use:
    Push project metadata and structure from your local analysis.
    The IDE analyses the local project and sends metadata to the remote MCP server.
    No filesystem access required on the server.

    Inputs:
    - project_id: Optional; auto-filled from context.
    - tech_stack: e.g. ["node", "docker"].
    - frameworks: e.g. ["react", "fastapi", "express"].
    - languages: e.g. ["python", "typescript"].
    - databases: e.g. ["postgresql", "redis"].
    - build_tools: e.g. ["docker", "webpack"].
    - architecture_type: e.g. "monolith", "microservices", "monorepo".
    - description: Free-text project description.
    - modules: List of module dicts [{name, type, path, tech_stack?, frameworks?, languages?}].

    Returns:
    - Confirmation with modules created count.

    Common mistakes:
    - Not calling project_create first.
    """
    from app.services.project_service import ProjectService

    context = await _get_active_mcp_context()
    effective_project_id = project_id or context.get("project_id")
    if not effective_project_id:
        return {"error": "project_id is required (pass explicitly or set via context_set/project_create)"}

    factory = _get_session_factory()
    async with factory() as db:
        svc = ProjectService(db)
        result = await svc.push_structure(
            project_id=effective_project_id,
            tech_stack=tech_stack,
            frameworks=frameworks,
            languages=languages,
            databases=databases,
            build_tools=build_tools,
            architecture_type=architecture_type,
            description=description,
            modules=modules,
        )
        await db.commit()
        return result


@mcp.tool(name="project_finalize_push")
async def finalize_project_push(
    project_id: str | None = None,
) -> Any:
    """When to use:
    Call after all project_push_files batches are sent to finalize indexing.
    Recomputes project stats and marks analysis as completed.

    Inputs:
    - project_id: Optional; auto-filled from context.

    Returns:
    - Final project stats (total_files, total_lines, languages).

    Common mistakes:
    - Calling before all file batches are pushed.
    """
    from app.services.project_service import ProjectService

    context = await _get_active_mcp_context()
    effective_project_id = project_id or context.get("project_id")
    if not effective_project_id:
        return {"error": "project_id is required (pass explicitly or set via context_set/project_create)"}

    factory = _get_session_factory()
    async with factory() as db:
        svc = ProjectService(db)
        result = await svc.finalize_push(project_id=effective_project_id)
        await db.commit()
        return result


@mcp.tool(name="project_get_context")
async def get_project_context(
    project_id: str | None = None,
    include_files: bool = True,
    include_functions: bool = True,
) -> Any:
    """When to use:
    Get full project context for AI: structure, modules, files, functions.

    Inputs:
    - project_id: Optional; auto-filled from context.
    - include_files: Include file list (default true).
    - include_functions: Include function list (default true).

    Returns:
    - Complete project context with all indexed data.

    Common mistakes:
    - Calling before project is indexed.
    """
    from app.services.project_service import ProjectService

    context = await _get_active_mcp_context()
    effective_project_id = project_id or context.get("project_id")
    if not effective_project_id:
        return {"error": "project_id is required (pass explicitly or set via context_set/project_create)"}

    factory = _get_session_factory()
    async with factory() as db:
        svc = ProjectService(db)
        return await svc.get_project_context(
            project_id=effective_project_id,
            include_files=include_files,
            include_functions=include_functions,
        )


@mcp.tool(name="project_search_code")
async def search_project_code(
    query: str,
    project_id: str | None = None,
    search_type: str = "all",
    top_k: int = 10,
) -> Any:
    """When to use:
    Semantic search across project code: find files and functions by meaning.

    Inputs:
    - query: Natural language search query.
    - project_id: Optional; auto-filled from context.
    - search_type: "all" | "files" | "functions".
    - top_k: Max results per type.

    Returns:
    - Matching files and functions with similarity scores.

    Common mistakes:
    - Searching before embeddings are generated.
    """
    from app.services.project_service import ProjectService

    context = await _get_active_mcp_context()
    effective_project_id = project_id or context.get("project_id")
    if not effective_project_id:
        return {"error": "project_id is required (pass explicitly or set via context_set/project_create)"}

    factory = _get_session_factory()
    async with factory() as db:
        svc = ProjectService(db)
        return await svc.search_code(
            project_id=effective_project_id,
            query=query,
            search_type=search_type,
            top_k=top_k,
        )


@mcp.tool(name="project_get_file")
async def get_project_file(
    file_path: str,
    project_id: str | None = None,
    include_content: bool = True,
    include_functions: bool = True,
) -> Any:
    """When to use:
    Get detailed information about a specific file.

    Inputs:
    - file_path: Relative path within project.
    - project_id: Optional; auto-filled from context.
    - include_content: Include file content.
    - include_functions: Include extracted functions.

    Returns:
    - File details with content and functions.

    Common mistakes:
    - Using absolute path instead of relative.
    """
    from sqlalchemy import select, and_
    from app.core.models import ProjectFile, ProjectFunction

    context = await _get_active_mcp_context()
    effective_project_id = project_id or context.get("project_id")
    if not effective_project_id:
        return {"error": "project_id is required"}

    factory = _get_session_factory()
    async with factory() as db:
        stmt = select(ProjectFile).where(
            and_(
                ProjectFile.project_id == uuid.UUID(effective_project_id),
                ProjectFile.relative_path == file_path
            )
        )
        result = await db.execute(stmt)
        file_record = result.scalar_one_or_none()
        
        if not file_record:
            return {"error": f"File not found: {file_path}"}
        
        response = {
            "id": str(file_record.id),
            "name": file_record.name,
            "path": file_record.relative_path,
            "language": file_record.language,
            "line_count": file_record.line_count,
            "size_bytes": file_record.size_bytes,
            "imports": file_record.imports,
            "summary": file_record.summary,
            "last_indexed": file_record.last_indexed.isoformat() if file_record.last_indexed else None,
        }
        
        if include_content:
            response["content"] = file_record.content
        
        if include_functions:
            stmt = select(ProjectFunction).where(ProjectFunction.file_id == file_record.id)
            result = await db.execute(stmt)
            functions = result.scalars().all()
            response["functions"] = [
                {
                    "id": str(f.id),
                    "name": f.name,
                    "type": f.type,
                    "signature": f.signature,
                    "docstring": f.docstring,
                    "line_start": f.line_start,
                    "line_end": f.line_end,
                    "is_async": f.is_async,
                    "is_exported": f.is_exported,
                }
                for f in functions
            ]
        
        return response


@mcp.tool(name="project_get_modules")
async def get_project_modules(
    project_id: str | None = None,
) -> Any:
    """When to use:
    Get project modules (backend, frontend, mobile, bot, etc.).

    Inputs:
    - project_id: Optional; auto-filled from context.

    Returns:
    - List of modules with their tech stacks.

    Common mistakes:
    - Calling before project is indexed.
    """
    from sqlalchemy import select
    from app.core.models import ProjectModule

    context = await _get_active_mcp_context()
    effective_project_id = project_id or context.get("project_id")
    if not effective_project_id:
        return {"error": "project_id is required"}

    factory = _get_session_factory()
    async with factory() as db:
        stmt = select(ProjectModule).where(
            ProjectModule.project_id == uuid.UUID(effective_project_id)
        )
        result = await db.execute(stmt)
        modules = result.scalars().all()
        
        return [
            {
                "id": str(m.id),
                "name": m.name,
                "type": m.module_type,
                "path": m.path,
                "tech_stack": m.tech_stack,
                "frameworks": m.frameworks,
                "languages": m.languages,
                "total_files": m.total_files,
                "total_lines": m.total_lines,
            }
            for m in modules
        ]


# ============================================================================
# IDE Session & Change Tracking Tools
# ============================================================================

@mcp.tool(name="ide_session_start")
async def start_ide_session(
    ide_name: str,
    project_id: str | None = None,
    model_name: str | None = None,
    model_provider: str | None = None,
    ide_version: str | None = None,
    user_id: str | None = None,
    machine_id: str | None = None,
) -> Any:
    """When to use:
    Start tracking an IDE session (Cursor, Windsurf, VSCode, etc.).

    Inputs:
    - ide_name: IDE identifier (cursor, windsurf, vscode, antigravity).
    - project_id: Optional; auto-filled from context.
    - model_name: AI model being used (gpt-4, claude-3, llama3.2).
    - model_provider: Provider (openai, anthropic, ollama).
    - ide_version: IDE version string.
    - user_id: Optional user identifier.
    - machine_id: Optional machine identifier.

    Returns:
    - session_id for tracking changes.

    Common mistakes:
    - Forgetting to end session when done.
    """
    from app.services.project_service import IDESessionService

    context = await _get_active_mcp_context()
    effective_project_id = project_id or context.get("project_id")

    factory = _get_session_factory()
    async with factory() as db:
        svc = IDESessionService(db)
        result = await svc.start_session(
            ide_name=ide_name,
            project_id=effective_project_id,
            model_name=model_name,
            model_provider=model_provider,
            ide_version=ide_version,
            user_id=user_id,
            machine_id=machine_id,
        )
        await db.commit()
        
        # Store session in context
        context["ide_session_id"] = result["session_id"]
        context["ide_name"] = ide_name
        context["model_name"] = model_name
        await _set_active_mcp_context(context)
        
        return result


@mcp.tool(name="ide_session_end")
async def end_ide_session(
    session_id: str | None = None,
) -> Any:
    """When to use:
    End an IDE session.

    Inputs:
    - session_id: Optional; auto-filled from context.

    Returns:
    - Session end confirmation.

    Common mistakes:
    - Ending wrong session.
    """
    from app.services.project_service import IDESessionService

    context = await _get_active_mcp_context()
    effective_session_id = session_id or context.get("ide_session_id")
    if not effective_session_id:
        return {"error": "session_id is required"}

    factory = _get_session_factory()
    async with factory() as db:
        svc = IDESessionService(db)
        result = await svc.end_session(effective_session_id)
        await db.commit()
        return result


@mcp.tool(name="changes_log")
async def log_code_change(
    file_path: str,
    change_type: str,
    project_id: str | None = None,
    session_id: str | None = None,
    old_content: str | None = None,
    new_content: str | None = None,
    diff: str | None = None,
    ide_name: str | None = None,
    model_name: str | None = None,
    model_provider: str | None = None,
    prompt_used: str | None = None,
    reason: str | None = None,
) -> Any:
    """When to use:
    Log a code change with full context.

    Inputs:
    - file_path: Path to changed file.
    - change_type: create | update | delete | rename | move.
    - project_id: Optional; auto-filled from context.
    - session_id: Optional; auto-filled from context.
    - old_content: Previous file content.
    - new_content: New file content.
    - diff: Unified diff.
    - ide_name: IDE that made the change.
    - model_name: AI model that made the change.
    - model_provider: AI provider.
    - prompt_used: Prompt that triggered the change.
    - reason: Why the change was made.

    Returns:
    - change_id and stats.

    Common mistakes:
    - Not providing enough context for future reference.
    """
    from app.services.project_service import IDESessionService

    context = await _get_active_mcp_context()
    effective_project_id = project_id or context.get("project_id")
    if not effective_project_id:
        return {"error": "project_id is required"}
    
    effective_session_id = session_id or context.get("ide_session_id")
    effective_ide = ide_name or context.get("ide_name")
    effective_model = model_name or context.get("model_name")

    factory = _get_session_factory()
    async with factory() as db:
        svc = IDESessionService(db)
        result = await svc.log_change(
            project_id=effective_project_id,
            file_path=file_path,
            change_type=change_type,
            session_id=effective_session_id,
            old_content=old_content,
            new_content=new_content,
            diff=diff,
            ide_name=effective_ide,
            model_name=effective_model,
            model_provider=model_provider,
            prompt_used=prompt_used,
            reason=reason,
        )
        await db.commit()
        return result


@mcp.tool(name="changes_get")
async def get_changes(
    project_id: str | None = None,
    since_hours: int | None = None,
    limit: int = 50,
) -> Any:
    """When to use:
    Get recent changes for a project.

    Inputs:
    - project_id: Optional; auto-filled from context.
    - since_hours: Get changes from last N hours.
    - limit: Max changes to return.

    Returns:
    - List of changes with metadata.

    Common mistakes:
    - Requesting too many changes at once.
    """
    from datetime import timedelta
    from app.services.project_service import IDESessionService

    context = await _get_active_mcp_context()
    effective_project_id = project_id or context.get("project_id")
    if not effective_project_id:
        return {"error": "project_id is required"}

    since = None
    if since_hours:
        since = datetime.now(timezone.utc) - timedelta(hours=since_hours)

    factory = _get_session_factory()
    async with factory() as db:
        svc = IDESessionService(db)
        return await svc.get_changes_since(
            project_id=effective_project_id,
            since=since,
            limit=limit,
        )


@mcp.tool(name="changes_sync_git")
async def sync_changes_from_git(
    project_id: str | None = None,
    project_path: str | None = None,
) -> Any:
    """When to use:
    Sync change history from git commits.

    Inputs:
    - project_id: Optional; auto-filled from context.
    - project_path: Project filesystem path.

    Returns:
    - Sync stats: commits processed, changes synced.

    Common mistakes:
    - Running on non-git repository.
    """
    from sqlalchemy import select
    from app.core.models import Project
    from app.services.project_service import IDESessionService

    context = await _get_active_mcp_context()
    effective_project_id = project_id or context.get("project_id")
    if not effective_project_id:
        return {"error": "project_id is required"}

    factory = _get_session_factory()
    async with factory() as db:
        # Get project path if not provided
        if not project_path:
            stmt = select(Project).where(Project.id == uuid.UUID(effective_project_id))
            result = await db.execute(stmt)
            project = result.scalar_one_or_none()
            if not project:
                return {"error": "Project not found"}
            project_path = project.path
        
        svc = IDESessionService(db)
        result = await svc.sync_from_git(
            project_id=effective_project_id,
            project_path=project_path,
        )
        await db.commit()
        return result


def configure_mcp(app: FastAPI) -> None:
    """Register MCP routes directly on the FastAPI application with robust handlers."""
    from mcp.server.sse import SseServerTransport
    from starlette.responses import Response

    # Initialize transport with the advertised message path
    sse_transport = SseServerTransport("/mcp/messages")
    # Per-session guard to preserve request ordering semantics for clients
    # that pipeline requests over multiple concurrent HTTP POSTs.
    _session_send_locks: dict[uuid.UUID, anyio.Lock] = {}
    _session_initialized: set[uuid.UUID] = set()

    async def mcp_sse_handler(scope, receive, send):
        """Handle GET /mcp/sse — starts the SSE stream."""
        try:
            async with sse_transport.connect_sse(scope, receive, send) as streams:
                await mcp._mcp_server.run(
                    streams[0],
                    streams[1],
                    mcp._mcp_server.create_initialization_options(),
                )
        except _DISCONNECT_EXCEPTIONS:
            logger.debug("MCP SSE connection closed gracefully")
        except Exception as e:
            if _is_expected_disconnect(e):
                logger.debug("MCP SSE connection closed gracefully (grouped)")
                return
            logger.error(f"MCP SSE unexpected error: {e}", exc_info=True)

    async def mcp_messages_handler(scope, receive, send):
        """Handle POST /mcp/messages — receives client messages for a session."""
        try:
            request = Request(scope, receive)
            session_id_param = request.query_params.get("session_id")
            if session_id_param is None:
                logger.warning("Received request without session_id")
                response = Response("session_id is required", status_code=400)
                await response(scope, receive, send)
                return

            try:
                session_id = uuid.UUID(hex=session_id_param)
            except ValueError:
                logger.warning("Received invalid session_id: %s", session_id_param)
                response = Response("Invalid session ID", status_code=400)
                await response(scope, receive, send)
                return

            writer = sse_transport._read_stream_writers.get(session_id)
            if writer is None:
                logger.warning("Could not find session for ID: %s", session_id)
                response = Response("Could not find session", status_code=404)
                await response(scope, receive, send)
                return

            payload = await request.json()
            try:
                message = mcp_types.JSONRPCMessage.model_validate(payload)
            except ValidationError as err:
                logger.error("Failed to parse MCP message: %s", err)
                response = Response("Could not parse message", status_code=400)
                await response(scope, receive, send)
                await writer.send(err)
                return

            lock = _session_send_locks.setdefault(session_id, anyio.Lock())
            async with lock:
                # Enforce initialization ordering to avoid session task-group
                # failures when clients issue concurrent pipelined requests.
                if isinstance(message.root, mcp_types.JSONRPCRequest):
                    if message.root.method == "initialize":
                        _session_initialized.discard(session_id)
                    elif session_id not in _session_initialized:
                        logger.warning(
                            "Rejected pre-initialize MCP request: method=%s session_id=%s",
                            message.root.method,
                            session_id.hex,
                        )
                        response = Response("Initialize required", status_code=409)
                        await response(scope, receive, send)
                        return

                # Keep HTTP-level compatibility for clients that do not accept 202.
                response = Response("Accepted", status_code=200)
                await response(scope, receive, send)
                await writer.send(message)

                # Compatibility shim: synthesize initialized notification right
                # after initialize, before any queued follow-up request.
                if (
                    isinstance(message.root, mcp_types.JSONRPCRequest)
                    and message.root.method == "initialize"
                ):
                    await writer.send(
                        mcp_types.JSONRPCMessage(
                            root=mcp_types.JSONRPCNotification(
                                jsonrpc="2.0",
                                method="notifications/initialized",
                                params={},
                            )
                        )
                    )
                    _session_initialized.add(session_id)
                elif (
                    isinstance(message.root, mcp_types.JSONRPCNotification)
                    and message.root.method == "notifications/initialized"
                ):
                    _session_initialized.add(session_id)
        except _DISCONNECT_EXCEPTIONS:
            logger.debug("MCP message connection closed gracefully")
        except Exception as e:
            if _is_expected_disconnect(e):
                logger.debug("MCP message connection closed gracefully (grouped)")
                return
            logger.error(f"MCP Message handler error: {e}", exc_info=True)

    async def mcp_options_handler(scope, receive, send):
        """Handle OPTIONS for MCP endpoints (CORS)."""
        resp = Response(status_code=204)
        await resp(scope, receive, send)

    class ASGIMCPHandler:
        """Wrapper to force Starlette to treat the handler as a raw ASGI app."""
        def __init__(self, handler):
            self.handler = handler
        async def __call__(self, scope, receive, send):
            await self.handler(scope, receive, send)

    # Register using explicit Starlette Routes with the ASGI wrapper
    # This avoids TypeError (introspection) and 307 (redirects)
    # We allow POST on BOTH paths to accommodate various client behaviors
    app.router.add_route("/mcp/sse", ASGIMCPHandler(mcp_sse_handler), methods=["GET"])
    app.router.add_route("/mcp/sse", ASGIMCPHandler(mcp_messages_handler), methods=["POST"])
    app.router.add_route("/mcp/messages", ASGIMCPHandler(mcp_messages_handler), methods=["POST"])
    
    # Global OPTIONS and even DELETE (seen in logs) handlers
    app.router.add_route("/mcp/sse", ASGIMCPHandler(mcp_options_handler), methods=["OPTIONS", "DELETE"])
    app.router.add_route("/mcp/messages", ASGIMCPHandler(mcp_options_handler), methods=["OPTIONS", "DELETE"])


def create_mcp_app() -> Any:
    """
    Deprecated: MCP is now mounted directly via configure_mcp.
    Kept for backward compatibility during migration.
    """
    # Return a dummy Starlette app that just warns
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse
    return Starlette(routes=[], on_startup=[lambda: logger.warning("create_mcp_app is deprecated, use configure_mcp")])
