import pytest

from honeyos.memory import CognitiveMemoryRepository
from honeyos.memory.importers.deepseek_v21 import DeepSeekV21Importer, DeepSeekV21ImportError


def sample_row(summary_id='dss_test_001', conversation_id='conversation-1'):
    return {
        'summary_id': summary_id,
        'summary': '用户曾经明确表达过一个历史事实。',
        'time': '2025-03-06T11:09:40.325000+08:00',
        'uncertain': False,
        'stage': 'faithful_summary_unreviewed',
        'source_batch': 7,
        'evidence': [{
            'key': '7/4/0',
            'quote': '我之前明确说过这件事情',
            'conversation_id': conversation_id,
            'conversation_index': 7,
            'message_time': '2025-03-06T11:09:40.325000+08:00',
            'path': 'main',
            'branch_root': None,
        }],
    }


def counts(repo):
    with repo.connect() as db:
        return (
            db.execute('SELECT COUNT(*) FROM memory_episodes').fetchone()[0],
            db.execute('SELECT COUNT(*) FROM memory_provenance').fetchone()[0],
        )


def test_dry_run_writes_nothing(tmp_path):
    repo = CognitiveMemoryRepository(tmp_path)
    stats = DeepSeekV21Importer(repo).import_rows([sample_row()], dry_run=True)
    assert stats.created == 1
    assert counts(repo) == (0, 0)


def test_commit_creates_external_episode_and_provenance(tmp_path):
    repo = CognitiveMemoryRepository(tmp_path)
    stats = DeepSeekV21Importer(repo).import_rows([sample_row()], dry_run=False)
    assert stats.created == 1
    assert stats.provenance_created == 1
    assert counts(repo) == (1, 1)
    with repo.connect() as db:
        e = db.execute('SELECT * FROM memory_episodes').fetchone()
        p = db.execute('SELECT * FROM memory_provenance').fetchone()
    assert e['memory_origin'] == 'external'
    assert e['source_system'] == 'deepseek'
    assert e['source_scope'] == 'historical_import'
    assert e['source_key'] == 'dss_test_001'
    assert p['source_id'] == 'conversation-1'
    assert p['message_id'] == '7/4/0'
    assert p['evidence_quote'] == '我之前明确说过这件事情'


def test_import_is_idempotent(tmp_path):
    repo = CognitiveMemoryRepository(tmp_path)
    imp = DeepSeekV21Importer(repo)
    imp.import_rows([sample_row()], dry_run=False)
    second = imp.import_rows([sample_row()], dry_run=False)
    assert second.already_complete == 1
    assert second.provenance_created == 0
    assert counts(repo) == (1, 1)


def test_missing_provenance_is_repaired(tmp_path):
    repo = CognitiveMemoryRepository(tmp_path)
    imp = DeepSeekV21Importer(repo)
    imp.import_rows([sample_row()], dry_run=False)
    with repo.connect() as db:
        db.execute('DELETE FROM memory_provenance')
    second = imp.import_rows([sample_row()], dry_run=False)
    assert second.repaired_existing == 1
    assert second.provenance_created == 1
    assert counts(repo) == (1, 1)


def test_conversation_tombstone_blocks_summary(tmp_path):
    repo = CognitiveMemoryRepository(tmp_path)
    repo.suppress_source('deepseek', 'conversation-1')
    stats = DeepSeekV21Importer(repo).import_rows([sample_row()], dry_run=False)
    assert stats.suppressed == 1
    assert counts(repo) == (0, 0)


def test_summary_tombstone_blocks_summary(tmp_path):
    repo = CognitiveMemoryRepository(tmp_path)
    repo.suppress_source('deepseek', 'dss_test_001')
    stats = DeepSeekV21Importer(repo).import_rows([sample_row()], dry_run=False)
    assert stats.suppressed == 1
    assert counts(repo) == (0, 0)


def test_multiple_evidence_preserved(tmp_path):
    repo = CognitiveMemoryRepository(tmp_path)
    row = sample_row()
    row['evidence'].append({
        'key': '7/5/0',
        'quote': '这是第二条证据',
        'conversation_id': 'conversation-1',
        'conversation_index': 7,
        'message_time': '2025-03-06T11:10:00.000000+08:00',
        'path': 'main',
        'branch_root': None,
    })
    stats = DeepSeekV21Importer(repo).import_rows([row], dry_run=False)
    assert stats.provenance_created == 2
    assert counts(repo) == (1, 2)


def test_unexpected_stage_rejected(tmp_path):
    repo = CognitiveMemoryRepository(tmp_path)
    row = sample_row()
    row['stage'] = 'memory_card'
    with pytest.raises(DeepSeekV21ImportError):
        DeepSeekV21Importer(repo).import_rows([row], dry_run=True)


def test_changed_summary_same_id_rejected(tmp_path):
    repo = CognitiveMemoryRepository(tmp_path)
    imp = DeepSeekV21Importer(repo)
    imp.import_rows([sample_row()], dry_run=False)
    changed = sample_row()
    changed['summary'] = '同一个 summary_id 却出现不同内容。'
    with pytest.raises(DeepSeekV21ImportError):
        imp.import_rows([changed], dry_run=False)

def test_import_uses_end_of_evidence_span_and_preserves_span(tmp_path):
    import json

    repo = CognitiveMemoryRepository(tmp_path)
    row = sample_row()
    row['time'] = '2025年3月6日（综合多条消息）'
    row['evidence'] = [
        {
            'key': '7/4/0',
            'quote': '开始',
            'conversation_id': 'conversation-1',
            'conversation_index': 7,
            'message_time': '2025-03-06T11:09:40.325000+08:00',
            'path': 'main',
            'branch_root': None,
        },
        {
            'key': '7/5/0',
            'quote': '结束',
            'conversation_id': 'conversation-1',
            'conversation_index': 7,
            'message_time': '2025-03-08T18:22:11.000000+08:00',
            'path': 'main',
            'branch_root': None,
        },
    ]

    DeepSeekV21Importer(repo).import_rows([row], dry_run=False)
    with repo.connect() as db:
        episode = db.execute('SELECT occurred_at, metadata_json FROM memory_episodes').fetchone()
    metadata = json.loads(episode['metadata_json'])
    assert episode['occurred_at'] == '2025-03-08T18:22:11.000000+08:00'
    assert metadata['raw_time'] == '2025年3月6日（综合多条消息）'
    assert metadata['evidence_time_start'] == '2025-03-06T11:09:40.325000+08:00'
    assert metadata['evidence_time_end'] == '2025-03-08T18:22:11.000000+08:00'
    assert metadata['time_mapping_policy'] == 'evidence_span_end'


def test_import_prefers_evidence_end_even_when_summary_time_is_parseable(tmp_path):
    repo = CognitiveMemoryRepository(tmp_path)
    row = sample_row()
    row['time'] = '2025-03-01T00:00:00+08:00'
    row['evidence'].append({
        'key': '7/9/0',
        'quote': '后来的消息',
        'conversation_id': 'conversation-1',
        'conversation_index': 7,
        'message_time': '2025-03-10T23:59:59+08:00',
        'path': 'main',
        'branch_root': None,
    })
    DeepSeekV21Importer(repo).import_rows([row], dry_run=False)
    with repo.connect() as db:
        occurred_at = db.execute('SELECT occurred_at FROM memory_episodes').fetchone()[0]
    assert occurred_at == '2025-03-10T23:59:59+08:00'
