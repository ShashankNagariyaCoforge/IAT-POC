"""
Pipeline Debug Logger
=====================
Writes a human-readable log.txt (in the backend root) for every pipeline run.
The file is OVERWRITTEN at the start of each case so you always see the latest run.

Usage:
    from pipeline_v2.utils.pipeline_logger import plog
    plog.start_case(case_id)
    plog.log_llm(stage, system_prompt, user_message, response)
    plog.log_stage(stage_name, **data_to_show)
    plog.end_case(duration)
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

# log.txt lives in the backend root directory (next to process_v2.py)
_LOG_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "log.txt")
)


def _safe_json(obj: Any, limit: int = 0) -> str:
    """Serialize obj to indented JSON string, truncate if limit > 0."""
    try:
        text = json.dumps(obj, indent=2, default=str, ensure_ascii=False)
    except Exception:
        text = str(obj)
    if limit and len(text) > limit:
        text = text[:limit] + f"\n... (truncated — total {len(text)} chars)"
    return text


class _PipelineLogger:
    def __init__(self):
        self._f = None
        self._case_id: Optional[str] = None

    # ── public interface ──────────────────────────────────────────────────────

    def start_case(self, case_id: str):
        """Call once at the very start of a pipeline run. Overwrites log.txt."""
        self._close()
        self._case_id = case_id
        self._f = open(_LOG_PATH, "w", encoding="utf-8")
        self._banner(
            f"PIPELINE V2 DEBUG LOG",
            f"Case ID : {case_id}",
            f"Started : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
            f"Log file: {_LOG_PATH}",
        )
        logger.info(f"[PipelineLogger] Debug log → {_LOG_PATH}")

    def log_stage(self, stage_name: str, **kwargs):
        """
        Log a named stage with arbitrary key=value data.
        Values are pretty-printed JSON when they are dicts/lists.
        """
        self._section(f"STAGE: {stage_name.upper()}")
        for key, val in kwargs.items():
            self._write(f"  {key}:")
            if isinstance(val, (dict, list)):
                for line in _safe_json(val, limit=8000).splitlines():
                    self._write(f"    {line}")
            else:
                for line in str(val)[:4000].splitlines():
                    self._write(f"    {line}")
        self._write("")

    def log_llm(
        self,
        stage_name: str,
        system_prompt: str,
        user_message: str,
        response: Any,
        tokens: int = 0,
        finish_reason: str = "",
        duration: float = 0.0,
    ):
        """Log a complete LLM call: full prompt in + full response out."""
        self._section(f"LLM CALL → {stage_name}")
        meta = []
        if tokens:       meta.append(f"tokens={tokens}")
        if duration:     meta.append(f"duration={duration:.1f}s")
        if finish_reason: meta.append(f"finish_reason={finish_reason}")
        if meta:
            self._write(f"  [{' | '.join(meta)}]")
            self._write("")

        self._subsection("SYSTEM PROMPT")
        for line in system_prompt.splitlines():
            self._write(f"  {line}")
        self._write("")

        self._subsection("USER MESSAGE")
        for line in user_message.splitlines():
            self._write(f"  {line}")
        self._write("")

        self._subsection("LLM RESPONSE")
        resp_text = _safe_json(response) if isinstance(response, (dict, list)) else str(response)
        for line in resp_text.splitlines():
            self._write(f"  {line}")
        self._write("")

    def log_extraction(self, source_doc: str, fields_requested: list, extracted: list):
        """
        Log per-document extraction results: what was asked vs what was found.
        Call this once per document after stage7 returns.
        """
        found = [e for e in extracted if e.value]
        self._write(f"  ┌─ EXTRACTION: {source_doc}")
        self._write(f"  │  Requested: {len(fields_requested)} fields   Found: {len(found)}/{len(fields_requested)}")
        self._write(f"  │")
        for e in extracted:
            ok   = "✓" if e.value else "✗"
            val  = (e.value or e.not_found_reason or "(null)")
            conf = f" [{e.confidence:.2f}]" if e.confidence else ""
            self._write(f"  │  {ok}{conf}  {e.field_name}: {str(val)[:120]}")
            if e.raw_text:
                self._write(f"  │        raw_text: \"{str(e.raw_text)[:100]}\"")
            if e.chunk_id:
                self._write(f"  │        chunk_id: {e.chunk_id}")
        self._write(f"  └" + "─" * 60)
        self._write("")

    def log_merge(self, merged_fields: list):
        """Log the final merged field table after stage9."""
        self._section("MERGE RESULTS")
        icons = {"accepted": "✓", "missing": "✗", "conflict": "⚡", "low_confidence": "~"}
        for f in merged_fields:
            icon = icons.get(f.status, "·")
            conf = f"{f.confidence:.2f}" if f.confidence else "0.00"
            val  = str(f.value or "(null)")[:100]
            src  = ""
            if f.primary_source:
                src = f"  ← {f.primary_source.document_name}"
                if f.primary_source.location and f.primary_source.location.page_number:
                    src += f" p.{f.primary_source.location.page_number}"
            self._write(f"  {icon} [{f.status:<14}] [{conf}] {f.field_name}: {val}{src}")
        self._write("")

    def end_case(self, duration: float, routing: str = ""):
        self._banner(
            f"PIPELINE COMPLETED",
            f"Duration : {duration:.1f}s",
            f"Routing  : {routing}" if routing else "",
        )
        self._close()

    # ── private helpers ───────────────────────────────────────────────────────

    def _write(self, line: str):
        if self._f:
            self._f.write(line + "\n")
            self._f.flush()

    def _section(self, title: str):
        self._write("")
        self._write("─" * 80)
        self._write(f"  {title}")
        self._write("─" * 80)

    def _subsection(self, title: str):
        self._write(f"  ── {title} " + "─" * (74 - len(title)))

    def _banner(self, *lines: str):
        self._write("")
        self._write("=" * 80)
        for line in lines:
            if line:
                self._write(f"  {line}")
        self._write("=" * 80)
        self._write("")

    def _close(self):
        if self._f:
            try:
                self._f.close()
            except Exception:
                pass
            self._f = None


# Singleton — import this everywhere
plog = _PipelineLogger()
