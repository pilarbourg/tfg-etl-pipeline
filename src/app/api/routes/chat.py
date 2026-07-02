import json
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from app.core.rag.generation import get_atlas_stream, get_atlas_stream_atlas
from app.core.rag.retrieval import get_context

router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    query: str


@router.post("/chat")
async def chat_endpoint(request: ChatRequest):
    """
    Streams a RAG-powered response to a research query about PD metabolomics.
    Returns sources followed by streamed text chunks.
    """
    def generate_stream():
        try:
            chunks, context_string = get_context(request.query)
            sources = [
                {"title": c["meta"]["title"], "url": c["meta"]["url"]}
                for c in chunks
            ]
            yield json.dumps({"type": "sources", "data": sources}) + "\n"

            for chunk in get_atlas_stream(request.query, context_string):
                try:
                    content = chunk.text
                except (AttributeError, ValueError):
                    content = ""
                if content:
                    yield json.dumps({"type": "text", "data": content}) + "\n"

        except Exception as e:
            yield json.dumps({"type": "error", "data": str(e)}) + "\n"

    return StreamingResponse(generate_stream(), media_type="application/x-ndjson")


@router.post("/atlas-describe")
async def atlas_describe(request: ChatRequest):
    """
    Streams a brief neuroanatomical description of a metabolite for the 3D brain atlas.
    Returns sources followed by streamed text chunks as newline-delimited JSON.
    """
    def generate_stream():
        try:
            chunks, context_string = get_context(request.query)
            sources = [
                {"title": c["meta"]["title"], "url": c["meta"]["url"]}
                for c in chunks
            ]
            yield json.dumps({"type": "sources", "data": sources}) + "\n"

            for chunk in get_atlas_stream_atlas(request.query, context_string):
                try:
                    content = chunk.text
                except (AttributeError, ValueError):
                    content = ""
                if content:
                    yield json.dumps({"type": "text", "data": content}) + "\n"

        except Exception as e:
            yield json.dumps({"type": "error", "data": str(e)}) + "\n"

    return StreamingResponse(generate_stream(), media_type="application/x-ndjson")