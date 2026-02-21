"""Chat API endpoints with streaming support."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import get_settings
from app.db.session import get_db
from app.services.memory_service import MemoryService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    """Request model for chat."""
    message: str = Field(..., description="User message")
    project_id: Optional[str] = Field(None, description="Project ID for context")
    session_id: Optional[str] = Field(None, description="Session ID for continuity")
    model: str = Field("qwen2.5:7b", description="Model name")
    temperature: float = Field(0.7, description="Temperature")
    max_tokens: int = Field(4096, description="Max tokens")
    use_memory: bool = Field(True, description="Use memory search")
    use_project_context: bool = Field(True, description="Use project context")
    use_orchestration: bool = Field(False, description="Use orchestration mode")
    images: Optional[List[str]] = Field(None, description="Base64 images for vision")


class ChatMessage(BaseModel):
    """Chat message model."""
    id: str
    role: str
    content: str
    timestamp: str
    metadata: Optional[Dict[str, Any]] = None


def _get_memory_service(db: AsyncSession = Depends(get_db)) -> MemoryService:
    return MemoryService(db)


async def _search_memory_context(svc: MemoryService, query: str) -> str:
    """Search memory for relevant context."""
    try:
        results = await svc.search(
            query=query,
            top_k=5,
            min_similarity=0.3,
        )
        if not results:
            return ""
        context_parts = []
        for r in results:
            content = r.get("content", "") if isinstance(r, dict) else str(r)
            context_parts.append(content)
        return "\n---\n".join(context_parts)
    except Exception as e:
        logger.warning("Memory search failed: %s", e)
        return ""


async def _search_project_context(db: AsyncSession, project_id: str, query: str) -> str:
    """Search project code for relevant context."""
    try:
        from app.indexing import ProjectIndexer
        indexer = ProjectIndexer(db)
        components = await indexer.search_components(
            project_id=project_id,
            query=query,
            limit=5,
        )
        if not components:
            return ""
        context_parts = []
        for comp in components:
            part = f"[{comp.type}] {comp.name} ({comp.relative_path})"
            if hasattr(comp, "content") and comp.content:
                part += f"\n```\n{comp.content[:500]}\n```"
            context_parts.append(part)
        return "\n---\n".join(context_parts)
    except Exception as e:
        logger.warning("Project context search failed: %s", e)
        return ""


def _build_system_prompt(memory_context: str, project_context: str) -> str:
    """Build system prompt with gathered context."""
    parts = [
        "You are an expert AI programming assistant with access to project memory and codebase context.",
        "Provide clear, accurate, and helpful responses.",
        "When suggesting code changes, use markdown code blocks with language tags.",
    ]
    if memory_context:
        parts.append(f"\n## Relevant Memory\n{memory_context}")
    if project_context:
        parts.append(f"\n## Project Context\n{project_context}")
    return "\n\n".join(parts)


async def _stream_ollama(
    model: str,
    messages: List[Dict[str, Any]],
    temperature: float,
    max_tokens: int,
    images: Optional[List[str]] = None,
):
    """Stream response from Ollama."""
    import httpx

    settings = get_settings()
    base_url = settings.ollama_base_url

    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": True,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        },
    }

    async with httpx.AsyncClient(timeout=300.0) as client:
        async with client.stream(
            "POST",
            f"{base_url}/api/chat",
            json=payload,
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                try:
                    chunk = json.loads(line)
                    token = chunk.get("message", {}).get("content", "")
                    done = chunk.get("done", False)
                    if token:
                        yield token
                    if done:
                        break
                except json.JSONDecodeError:
                    continue


@router.post("/stream")
async def chat_stream(
    body: ChatRequest,
    db: AsyncSession = Depends(get_db),
    svc: MemoryService = Depends(_get_memory_service),
):
    """Stream chat response with memory and project context pipeline."""

    async def event_generator():
        full_response = ""

        # Phase 1: Memory search
        memory_context = ""
        if body.use_memory:
            yield f"data: {json.dumps({'type': 'status', 'content': 'Searching memory...'})}\n\n"
            memory_context = await _search_memory_context(svc, body.message)

        # Phase 2: Project context search
        project_context = ""
        if body.use_project_context and body.project_id:
            yield f"data: {json.dumps({'type': 'status', 'content': 'Searching project...'})}\n\n"
            project_context = await _search_project_context(db, body.project_id, body.message)

        # Phase 3: Build prompt and stream from Ollama
        yield f"data: {json.dumps({'type': 'status', 'content': 'Generating...'})}\n\n"

        system_prompt = _build_system_prompt(memory_context, project_context)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": body.message},
        ]

        try:
            async for token in _stream_ollama(
                model=body.model,
                messages=messages,
                temperature=body.temperature,
                max_tokens=body.max_tokens,
                images=body.images,
            ):
                full_response += token
                yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
        except Exception as e:
            logger.error("Ollama streaming error: %s", e)
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
            return

        # Phase 4: Save to memory
        if body.use_memory and full_response:
            try:
                await svc.store(
                    content=f"Q: {body.message}\nA: {full_response[:500]}",
                    memory_type="episode",
                    metadata={"project_id": body.project_id, "session_id": body.session_id},
                    importance=3,
                )
            except Exception as e:
                logger.warning("Failed to store chat memory: %s", e)

        yield f"data: {json.dumps({'type': 'done', 'content': ''})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/send")
async def chat_send(
    body: ChatRequest,
    db: AsyncSession = Depends(get_db),
    svc: MemoryService = Depends(_get_memory_service),
) -> Dict[str, Any]:
    """Non-streaming chat endpoint."""
    import httpx

    # Gather context
    memory_context = ""
    if body.use_memory:
        memory_context = await _search_memory_context(svc, body.message)

    project_context = ""
    if body.use_project_context and body.project_id:
        project_context = await _search_project_context(db, body.project_id, body.message)

    system_prompt = _build_system_prompt(memory_context, project_context)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": body.message},
    ]

    settings = get_settings()
    payload: Dict[str, Any] = {
        "model": body.model,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": body.temperature,
            "num_predict": body.max_tokens,
        },
    }

    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            resp = await client.post(
                f"{settings.ollama_base_url}/api/chat",
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            content = data.get("message", {}).get("content", "")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Ollama error: {e}")

    # Save to memory
    if body.use_memory and content:
        try:
            await svc.store(
                content=f"Q: {body.message}\nA: {content[:500]}",
                memory_type="episode",
                metadata={"project_id": body.project_id},
                importance=3,
            )
        except Exception:
            pass

    return {
        "id": str(uuid.uuid4()),
        "role": "assistant",
        "content": content,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "metadata": {
            "model": body.model,
            "memory_used": bool(memory_context),
            "project_context_used": bool(project_context),
        },
    }


@router.get("/models")
async def list_ollama_models() -> Dict[str, Any]:
    """List available Ollama models."""
    import httpx

    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{settings.ollama_base_url}/api/tags")
            resp.raise_for_status()
            data = resp.json()
            models = [
                {
                    "name": m.get("name", ""),
                    "size": m.get("size", 0),
                    "modified_at": m.get("modified_at", ""),
                    "details": m.get("details", {}),
                }
                for m in data.get("models", [])
            ]
            return {"models": models, "count": len(models)}
    except Exception as e:
        logger.error("Failed to list Ollama models: %s", e)
        return {"models": [], "count": 0, "error": str(e)}
