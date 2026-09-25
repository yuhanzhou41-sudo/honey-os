from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterable

from honeyos.memory.repository import (
    CognitiveMemoryRepository,
    MemoryNotFoundError,
    MemorySuppressedError,
)

DEFAULT_INPUT = Path.home() / '.honeyos' / 'deepseek_sol_summary_v2_1' / 'run' / 'all_summaries.jsonl'
SOURCE_SYSTEM = 'deepseek'
SOURCE_SCOPE = 'historical_import'
SOURCE_TYPE = 'historical_message_evidence'
IMPORT_FORMAT = 'deepseek_sol_summary_v2_1'


class DeepSeekV21ImportError(ValueError):
    pass


@dataclass
class ImportStats:
    scanned: int = 0
    validated: int = 0
    created: int = 0
    repaired_existing: int = 0
    already_complete: int = 0
    suppressed: int = 0
    invalid: int = 0
    provenance_created: int = 0

    def to_dict(self):
        return asdict(self)


def _episode_id(summary_id: str) -> str:
    return 'me_ds_' + hashlib.sha256(summary_id.encode('utf-8')).hexdigest()[:24]


def _quote_hash(quote: str) -> str:
    return hashlib.sha256(quote.encode('utf-8')).hexdigest()


def _normalize_time(value: Any) -> str | None:
    text = str(value or '').strip()
    if not text:
        return None
    m = re.match(r'^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?)', text)
    return m.group(1) if m else None



def _evidence_time_span(row: dict[str, Any]) -> tuple[str | None, str | None]:
    # Return earliest/latest parseable evidence message_time.
    #
    # A faithful summary may cover a long question/roleplay/story arc.
    # Cognitive Memory has one occurred_at field, so use the END of the
    # evidence span as the representative timestamp while preserving the
    # full start/end span in metadata.
    values: list[str] = []
    for item in row.get("evidence") or []:
        value = _normalize_time(item.get("message_time"))
        if value is not None:
            values.append(value)
    if not values:
        return None, None
    values.sort()
    return values[0], values[-1]


def _validate_row(row: Any, *, line_no: int | None = None) -> dict[str, Any]:
    prefix = f'line {line_no}: ' if line_no is not None else ''
    if not isinstance(row, dict):
        raise DeepSeekV21ImportError(prefix + 'row must be an object')

    required = {'summary_id', 'summary', 'time', 'uncertain', 'evidence', 'stage'}
    missing = required - set(row)
    if missing:
        raise DeepSeekV21ImportError(prefix + 'missing fields: ' + ', '.join(sorted(missing)))

    summary_id = str(row.get('summary_id') or '').strip()
    summary = str(row.get('summary') or '').strip()
    stage = str(row.get('stage') or '').strip()
    if not summary_id:
        raise DeepSeekV21ImportError(prefix + 'empty summary_id')
    if not summary:
        raise DeepSeekV21ImportError(prefix + 'empty summary')
    if stage != 'faithful_summary_unreviewed':
        raise DeepSeekV21ImportError(prefix + f'unexpected stage: {stage!r}')

    evidence = row.get('evidence')
    if not isinstance(evidence, list) or not evidence:
        raise DeepSeekV21ImportError(prefix + 'evidence must be non-empty list')

    req_e = {'key', 'quote', 'conversation_id', 'conversation_index', 'message_time', 'path', 'branch_root'}
    normalized_evidence = []
    for i, item in enumerate(evidence):
        if not isinstance(item, dict):
            raise DeepSeekV21ImportError(prefix + f'evidence[{i}] must be object')
        missing_e = req_e - set(item)
        if missing_e:
            raise DeepSeekV21ImportError(prefix + f'evidence[{i}] missing: ' + ', '.join(sorted(missing_e)))
        if not str(item.get('key') or '').strip():
            raise DeepSeekV21ImportError(prefix + f'evidence[{i}] empty key')
        if not str(item.get('quote') or ''):
            raise DeepSeekV21ImportError(prefix + f'evidence[{i}] empty quote')
        if not str(item.get('conversation_id') or '').strip():
            raise DeepSeekV21ImportError(prefix + f'evidence[{i}] empty conversation_id')
        normalized_evidence.append(dict(item))

    out = dict(row)
    out['summary_id'] = summary_id
    out['summary'] = summary
    out['stage'] = stage
    out['uncertain'] = bool(row.get('uncertain', False))
    out['evidence'] = normalized_evidence
    return out


def _prov_identity(item):
    return (str(item['conversation_id']), str(item['key']), _quote_hash(str(item['quote'])))


class DeepSeekV21Importer:
    def __init__(self, repository: CognitiveMemoryRepository):
        self.repository = repository

    def _existing_episode(self, episode_id):
        try:
            return self.repository.get_episode(episode_id)
        except MemoryNotFoundError:
            return None

    def _assert_not_suppressed(self, row):
        self.repository.assert_not_suppressed(source_system=SOURCE_SYSTEM, source_id=row['summary_id'])
        seen = set()
        for e in row['evidence']:
            cid = str(e['conversation_id'])
            if cid in seen:
                continue
            seen.add(cid)
            self.repository.assert_not_suppressed(source_system=SOURCE_SYSTEM, source_id=cid)

    def _existing_provenance(self, episode_id):
        with self.repository.connect() as db:
            rows = db.execute(
                """
                SELECT source_id, message_id, content_hash
                FROM memory_provenance
                WHERE memory_kind='episode' AND memory_id=?
                  AND source_system=? AND source_type=?
                """,
                (episode_id, SOURCE_SYSTEM, SOURCE_TYPE),
            ).fetchall()
        return {(str(r['source_id'] or ''), str(r['message_id'] or ''), str(r['content_hash'] or '')) for r in rows}

    def import_row(self, raw_row, *, dry_run=True):
        row = _validate_row(raw_row)
        self._assert_not_suppressed(row)
        episode_id = _episode_id(row['summary_id'])
        existing = self._existing_episode(episode_id)

        if existing is not None:
            if (
                existing.memory_origin != 'external'
                or existing.source_system != SOURCE_SYSTEM
                or existing.source_scope != SOURCE_SCOPE
                or existing.source_key != row['summary_id']
                or existing.summary != row['summary']
            ):
                raise DeepSeekV21ImportError(
                    'deterministic episode id collision or imported summary changed: ' + row['summary_id']
                )

        if dry_run:
            return ('would_repair' if existing else 'would_create', 0)

        if existing is None:
            evidence_time_start, evidence_time_end = _evidence_time_span(row)
            episode = self.repository.create_episode(
                episode_id=episode_id,
                episode_type='historical_external',
                summary=row['summary'],
                # Summary represents the completed arc; use its evidence end.
                occurred_at=evidence_time_end or _normalize_time(row.get('time')),
                memory_origin='external',
                source_system=SOURCE_SYSTEM,
                source_scope=SOURCE_SCOPE,
                source_key=row['summary_id'],
                confidence=1.0,
                metadata={
                    'import_format': IMPORT_FORMAT,
                    'summary_id': row['summary_id'],
                    'raw_time': row.get('time'),
                    'evidence_time_start': evidence_time_start,
                    'evidence_time_end': evidence_time_end,
                    'time_mapping_policy': 'evidence_span_end',
                    'uncertain': row['uncertain'],
                    'stage': row['stage'],
                    'source_batch': row.get('source_batch'),
                    'evidence_count': len(row['evidence']),
                    'conversation_ids': sorted({str(e['conversation_id']) for e in row['evidence']}),
                },
            )
        else:
            episode = existing

        existing_ids = self._existing_provenance(episode.episode_id)
        created = 0
        for e in row['evidence']:
            identity = _prov_identity(e)
            if identity in existing_ids:
                continue
            self.repository.add_provenance(
                memory_kind='episode',
                memory_id=episode.episode_id,
                source_system=SOURCE_SYSTEM,
                source_type=SOURCE_TYPE,
                source_id=str(e['conversation_id']),
                session_id=str(e['conversation_id']),
                message_id=str(e['key']),
                evidence_quote=str(e['quote']),
                content_hash=identity[2],
                metadata={
                    'summary_id': row['summary_id'],
                    'source_batch': row.get('source_batch'),
                    'conversation_index': e.get('conversation_index'),
                    'message_time': e.get('message_time'),
                    'path': e.get('path'),
                    'branch_root': e.get('branch_root'),
                },
            )
            existing_ids.add(identity)
            created += 1

        expected = len({_prov_identity(e) for e in row['evidence']})
        actual = len(self._existing_provenance(episode.episode_id))
        if actual < expected:
            raise DeepSeekV21ImportError(f'provenance repair incomplete for {row["summary_id"]}: {actual} < {expected}')

        if existing is None:
            return 'created', created
        if created:
            return 'repaired_existing', created
        return 'already_complete', 0

    def import_rows(self, rows: Iterable[dict[str, Any]], *, dry_run=True, stop_on_invalid=True):
        stats = ImportStats()
        for raw in rows:
            stats.scanned += 1
            try:
                row = _validate_row(raw)
                stats.validated += 1
                state, prov = self.import_row(row, dry_run=dry_run)
                if state in {'created', 'would_create'}:
                    stats.created += 1
                elif state in {'repaired_existing', 'would_repair'}:
                    stats.repaired_existing += 1
                elif state == 'already_complete':
                    stats.already_complete += 1
                stats.provenance_created += prov
            except MemorySuppressedError:
                stats.suppressed += 1
            except DeepSeekV21ImportError:
                stats.invalid += 1
                if stop_on_invalid:
                    raise
        return stats


def load_jsonl(path: Path):
    rows = []
    with path.open('r', encoding='utf-8') as f:
        for line_no, line in enumerate(f, 1):
            text = line.strip()
            if not text:
                continue
            try:
                obj = json.loads(text)
            except json.JSONDecodeError as exc:
                raise DeepSeekV21ImportError(f'line {line_no}: invalid JSON: {exc}') from exc
            rows.append(_validate_row(obj, line_no=line_no))
    return rows


def main():
    p = argparse.ArgumentParser(description='Import DeepSeek V2.1 summaries into Cognitive Memory')
    p.add_argument('--input', type=Path, default=DEFAULT_INPUT)
    p.add_argument('--commit', action='store_true', help='Actually write; default is dry-run')
    p.add_argument('--limit', type=int, default=None)
    args = p.parse_args()

    if not args.input.is_file():
        raise SystemExit(f'Input not found: {args.input}')
    rows = load_jsonl(args.input)
    if args.limit is not None:
        rows = rows[:max(0, args.limit)]

    importer = DeepSeekV21Importer(CognitiveMemoryRepository())
    stats = importer.import_rows(rows, dry_run=not args.commit)
    print('=== DEEPSEEK V2.1 COGNITIVE MEMORY IMPORT ===')
    print('mode:', 'COMMIT' if args.commit else 'DRY-RUN')
    print('input:', args.input)
    print('rows:', len(rows))
    for k, v in stats.to_dict().items():
        print(f'{k}: {v}')
    if not args.commit:
        print('No database writes were performed.')


if __name__ == '__main__':
    main()
