from __future__ import annotations

import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from gateway.service import GatewayModelService, gateway_model_service
from shared import settings
from shared.schemas import (
    ChatMessageRequest,
    KnowledgeCitationResponse,
    KnowledgeQueryRequest,
    KnowledgeQueryResponse,
)


ALLOWED_EXTENSIONS = {".md", ".txt"}
_ASCII_WORD = re.compile(r"[a-zA-Z0-9_.-]{2,}")
_HAN_SEQUENCE = re.compile(r"[\u3400-\u9fff]+")
_CITATION = re.compile(r"\[(S\d+)\]")


@dataclass(frozen=True)
class KnowledgeChunk:
    title: str
    source: str
    section: str
    version: str
    text: str
    tokens: frozenset[str]


class KnowledgeIndex:
    """Read-only lexical index constrained to administrator-approved roots."""

    def __init__(self, roots: Optional[Iterable[str | Path]] = None, *, max_file_bytes: Optional[int] = None):
        raw_roots = list(roots) if roots is not None else _configured_roots(settings.CADCOPILOT_KNOWLEDGE_ROOTS)
        self._roots = tuple(_safe_root(value) for value in raw_roots if str(value).strip())
        self._max_file_bytes = max_file_bytes or settings.CADCOPILOT_KNOWLEDGE_MAX_FILE_BYTES

    @property
    def roots(self) -> tuple[Path, ...]:
        return self._roots

    def search(self, question: str, *, limit: int = 5) -> list[KnowledgeCitationResponse]:
        query_tokens = _tokens(question)
        if not query_tokens:
            return []
        ranked: list[tuple[float, KnowledgeChunk]] = []
        for chunk in self._chunks():
            overlap = query_tokens & chunk.tokens
            if not overlap:
                continue
            score = len(overlap) / max(len(query_tokens), 1)
            if question.strip() and question.strip().lower() in chunk.text.lower():
                score += 1.0
            ranked.append((round(score, 6), chunk))
        ranked.sort(key=lambda item: (-item[0], item[1].source, item[1].section))
        return [
            KnowledgeCitationResponse(
                citation_id=f"S{index}",
                title=chunk.title,
                source=chunk.source,
                section=chunk.section,
                version=chunk.version,
                excerpt=chunk.text[:1200],
                score=score,
            )
            for index, (score, chunk) in enumerate(ranked[: max(1, limit)], start=1)
        ]

    def _chunks(self) -> Iterable[KnowledgeChunk]:
        for root in self._roots:
            if not root.is_dir():
                continue
            for path in sorted(root.rglob("*")):
                if not path.is_file() or path.suffix.lower() not in ALLOWED_EXTENSIONS:
                    continue
                resolved = path.resolve()
                if not _is_within(resolved, root):
                    continue
                try:
                    if resolved.stat().st_size > self._max_file_bytes:
                        continue
                    text = resolved.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
                relative = resolved.relative_to(root).as_posix()
                title, version = _metadata(text, resolved.stem)
                for section, chunk_text in _split_document(text):
                    yield KnowledgeChunk(
                        title=title,
                        source=f"{root.name}/{relative}",
                        section=section,
                        version=version,
                        text=chunk_text,
                        tokens=frozenset(_tokens(chunk_text)),
                    )


class KnowledgeQueryService:
    def __init__(
        self,
        index: Optional[KnowledgeIndex] = None,
        gateway: GatewayModelService = gateway_model_service,
        *,
        max_context_chars: Optional[int] = None,
    ):
        self._index = index or KnowledgeIndex()
        self._gateway = gateway
        self._max_context_chars = max_context_chars or settings.CADCOPILOT_KNOWLEDGE_MAX_CONTEXT_CHARS

    @property
    def configured(self) -> bool:
        return bool(self._index.roots)

    async def query(self, request: KnowledgeQueryRequest) -> KnowledgeQueryResponse:
        trace_id = (request.trace_id or "").strip() or str(uuid.uuid4())
        citations = self._index.search(request.question, limit=request.max_sources)
        if not citations:
            return KnowledgeQueryResponse(
                trace_id=trace_id,
                warning="未在已授权的本地规范资料中找到可引用内容；未调用模型生成无来源答案。",
            )

        context = _build_context(citations, self._max_context_chars)
        system_prompt = (
            "你是企业 CAD 规范查询助手。只能依据提供的本地资料回答。"
            "每个关键结论必须使用 [S1] 形式引用来源；资料不足时明确说不知道。"
            "不得把模型记忆、网络常识或未提供的规范版本当作事实。"
        )
        user_prompt = f"问题：{request.question}\n\n本地资料：\n{context}"
        model_request = ChatMessageRequest(
            message=request.question,
            provider=request.provider,
            model=request.model,
            api_key=request.api_key,
            api_base_url=request.api_base_url,
            protocol=request.protocol,
            capabilities=request.capabilities,
            trace_id=trace_id,
            mode="chat",
        )
        result = await self._gateway.request_text_result(model_request, system_prompt, user_prompt)
        allowed_ids = {item.citation_id for item in citations}
        used_ids = set(_CITATION.findall(result.text))
        invalid_ids = sorted(used_ids - allowed_ids)
        grounded = bool(used_ids) and not invalid_ids
        warning = ""
        if invalid_ids:
            warning = "模型返回了不存在的来源编号：" + ", ".join(invalid_ids)
        elif not used_ids:
            warning = "模型回答未包含来源编号，结果不能视为已核验规范答案。"
        answer = _append_source_list(result.text, citations)
        return KnowledgeQueryResponse(
            answer=answer,
            citations=citations,
            grounded=grounded,
            warning=warning,
            trace_id=trace_id,
            model_provider=result.provider,
            model_name=result.model,
        )


def _configured_roots(value: str) -> list[str]:
    return [item.strip() for item in (value or "").split(os.pathsep) if item.strip()]


def _safe_root(value: str | Path) -> Path:
    return Path(value).expanduser().resolve()


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _tokens(value: str) -> set[str]:
    text = (value or "").lower()
    tokens = {match.group(0) for match in _ASCII_WORD.finditer(text)}
    for match in _HAN_SEQUENCE.finditer(text):
        sequence = match.group(0)
        if len(sequence) == 1:
            tokens.add(sequence)
        else:
            tokens.update(sequence[index : index + 2] for index in range(len(sequence) - 1))
    return tokens


def _metadata(text: str, fallback_title: str) -> tuple[str, str]:
    title = fallback_title
    version = ""
    for line in text.splitlines()[:20]:
        stripped = line.strip()
        if stripped.startswith("# ") and title == fallback_title:
            title = stripped[2:].strip() or title
        lowered = stripped.lower()
        if lowered.startswith("title:"):
            title = stripped.split(":", 1)[1].strip() or title
        if lowered.startswith("version:"):
            version = stripped.split(":", 1)[1].strip()
    return title, version


def _split_document(text: str) -> Iterable[tuple[str, str]]:
    section = ""
    buffer: list[str] = []
    size = 0

    def flush() -> Optional[tuple[str, str]]:
        nonlocal buffer, size
        normalized = "\n".join(buffer).strip()
        buffer = []
        size = 0
        return (section, normalized) if len(normalized) >= 20 else None

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            item = flush()
            if item:
                yield item
            section = stripped.lstrip("#").strip()
            continue
        if not stripped:
            if size >= 500:
                item = flush()
                if item:
                    yield item
            continue
        buffer.append(stripped)
        size += len(stripped)
        if size >= 1200:
            item = flush()
            if item:
                yield item
    item = flush()
    if item:
        yield item


def _build_context(citations: list[KnowledgeCitationResponse], limit: int) -> str:
    parts: list[str] = []
    remaining = max(limit, 1)
    for item in citations:
        header = f"[{item.citation_id}] {item.title} | {item.source}"
        if item.version:
            header += f" | 版本 {item.version}"
        if item.section:
            header += f" | {item.section}"
        excerpt = item.excerpt[: max(0, remaining - len(header) - 2)]
        if not excerpt:
            break
        parts.append(header + "\n" + excerpt)
        remaining -= len(header) + len(excerpt) + 2
        if remaining <= 0:
            break
    return "\n\n".join(parts)


def _append_source_list(answer: str, citations: list[KnowledgeCitationResponse]) -> str:
    source_lines = [
        f"[{item.citation_id}] {item.title}（{item.source}{'，' + item.section if item.section else ''}）"
        for item in citations
    ]
    return (answer or "").strip() + "\n\n来源：\n" + "\n".join(source_lines)


knowledge_query_service = KnowledgeQueryService()
