"""Offline, version-pinned publication. Never modifies research inputs.

Reader links are resolved by document and element ID, checked against the text,
and exported with the publication audit. Missing judgments are never inferred.
"""
from __future__ import annotations

from collections import Counter
import csv
import gzip
import hashlib
import html
import json
from pathlib import Path
import re
import shutil
import tomllib
import unicodedata
import xml.etree.ElementTree as ET

XID = '{http://www.w3.org/XML/1998/namespace}id'
NS = {'t': 'http://www.tei-c.org/ns/1.0'}
ASSET_VERSIONS = {}
DISPLAY_JUDGMENTS = {
    'corresponding': '対応あり', 'present_correspondence': '対応あり',
    'partially_corresponding': '一部対応', 'partial_present_correspondence': '一部対応',
    'not_corresponding': '対応なし', 'no_present_correspondence': '対応なし',
    'uncertain': '判定不可', 'unjudgeable': '判定不可', 'not_evaluated': '未判定',
}
LABELS = {'env6th': {'ver1': '中間取りまとめ案 初版', 'ver2': '中間取りまとめ案 修正版',
    'chukan': '中間取りまとめ', 'soan': '素案', 'an': '案', 'toshin': '答申案', 'kakugi': '閣議決定'},
    'ene7th': {'kokkaku': '骨格案', 'genan': '原案', 'an': '案', 'saisyu': '最終案'}}


def read_jsonl(path):
    with Path(path).open(encoding='utf-8') as f:
        return [json.loads(s) for s in f if s.strip()]


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def payload(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c')


def norm(value):
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', value or ''))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def text_of(node, plan=False):
    # Match extraction semantics while keeping original visible characters.
    parts = []
    def visit(n):
        if n.text:
            parts.append(n.text)
        for c in n:
            tag = c.tag.split('}')[-1]
            if not (plan and (tag in {'seg', 'ab'} or (tag == 'ref' and c.get('type') == 'noteAnchor'))):
                visit(c)
            if c.tail:
                parts.append(c.tail)
    visit(node)
    return re.sub(r'[ \t]+', ' ', ''.join(parts)).strip()


def version_assets(document):
    """Change resource URLs with their contents, avoiding stale browser/CDN caches."""
    return re.sub(r'((?:src|href)="[^"]*/assets/([^"?]+))(?:\?v=[^"]*)?(\")',
        lambda m: m[1] + '?v=' + ASSET_VERSIONS[m[2]] + m[3]
        if m[2] in ASSET_VERSIONS else m[0], document)


def page(title, body, script='', stylesheet='../../assets/reader.css'):
    return version_assets(f'''<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title><link rel="stylesheet" href="{stylesheet}"></head><body>{body}{script}</body></html>''')


class Readers:
    def __init__(self, docs, plan):
        self.docs, self.plan = docs, plan
        self.documents, self.speeches = {}, {}
        self.stats = Counter()
        self.issues = []

    def add(self, key, title, root, source, is_plan=False):
        blocks = []
        container = root.find('t:text', NS)
        if container is None:
            raise ValueError(f'Missing TEI text: {source}')
        def visit(node, depth=0):
            tag = node.tag.split('}')[-1]
            eid = node.get(XID)
            if tag in {'u', 'p', 'head', 'note', 'ab'} and (eid or tag in {'u','head','ab'}):
                # A speech is rendered as one unit; its seg children stay within it.
                eid = eid or f'block-{len(blocks)}'
                blocks.append({'id': eid, 'kind': tag, 'text': text_of(node, is_plan and tag != 'ab'),
                               'speaker': node.get('n', '') if tag == 'u' else '', 'depth': depth})
                return
            for child in node:
                visit(child, depth + (tag == 'div'))
        visit(container)
        lookup = {b['id']: b for b in blocks}
        if len(lookup) != len(blocks):
            raise ValueError(f'Duplicate reader IDs in {key}')
        target = self.docs / 'readers' / self.plan / f'{key}.html'
        target.parent.mkdir(parents=True, exist_ok=True)
        contents = []
        for b in blocks:
            heading = f'<h2>{html.escape(b["text"])}</h2>' if b['kind'] == 'head' else f'<div class="source-text">{html.escape(b["text"])}</div>'
            speaker = f'<div class="block-meta"><b>{html.escape(b["speaker"])}</b></div>' if b['speaker'] else ''
            contents.append(f'<section id="{html.escape(b["id"])}" class="source-block {b["kind"]}">{speaker}{heading}</section>')
        raw_url = '../../' + str(source.relative_to(self.docs))
        body = f'<header class="reader-header"><a href="../../">サイトトップ</a><h1>{html.escape(title)}</h1><p><a href="{html.escape(raw_url)}" download>元のTEI XML</a> <button id="copy-link">この箇所のリンクをコピー</button></p><p id="reader-status" role="status"></p><nav id="target-nav"></nav></header><main class="reading">{"".join(contents)}</main>'
        target.write_text(page(title, body, '<script src="../../assets/reader.js"></script>'), encoding='utf-8')
        self.documents[key] = {'title': title, 'blocks': lookup,
            'url': f'../../readers/{self.plan}/{key}.html?v={sha(target)[:12]}'}
        if not is_plan:
            for b in blocks:
                if b['kind'] == 'u':
                    if b['id'] in self.speeches:
                        raise ValueError(f'Ambiguous speech: {b["id"]}')
                    self.speeches[b['id']] = key

    def ref(self, doc, ids, quotes=None, expected='', role='plan'):
        ids = list(dict.fromkeys(ids))
        if not ids:
            return None
        entry = self.documents.get(doc)
        if entry is None or any(i not in entry['blocks'] for i in ids):
            self.issues.append({'kind': 'unresolved_id', 'document': doc, 'ids': ids})
            return None
        texts = [entry['blocks'][i]['text'] for i in ids]
        # Exclude member separators used by the alignment export from the comparison.
        if expected and norm(re.sub(r'\s+---\s+', '', expected)) != norm(''.join(texts)):
            self.issues.append({'kind': 'text_mismatch', 'document': doc, 'ids': ids,
                                'expected': expected, 'actual': '\n'.join(texts)})
        valid_quotes = []
        for q in dict.fromkeys(quotes or []):
            if q and any(norm(q) in norm(t) for t in texts):
                valid_quotes.append(q)
                self.stats['verified_quotes'] += 1
            elif q:
                self.stats['paragraph_only_quotes'] += 1
        self.stats['resolved_links'] += 1
        return {'url': entry['url'], 'title': entry['title'], 'ids': ids, 'quotes': valid_quotes, 'role': role}

    def source_ref(self, metadata):
        location = metadata.get('source_location', '')
        match = re.search(r'xml:id=([^\s/]+)', location)
        if not match:
            return None
        eid = match[1]
        key = self.speeches.get(eid)
        if not key:
            self.issues.append({'kind': 'unresolved_speech', 'request_id': metadata['request_id'], 'id': eid})
            return None
        quote = metadata.get('request_quote', '')
        # Compound quotations retain individual quoted passages, never approximate matches.
        quotes = [quote] + re.findall('「([^「」]+)」', quote)
        return self.ref(key, [eid], quotes, role='source')


def build_readers(analysis, docs, plan, manifest):
    readers = Readers(docs, plan)
    target = docs / 'data' / plan
    if plan == 'env6th':
        cfg = tomllib.loads((analysis / plan / '改訂特定/計画7版間段落対応付け_再実行_20261028/config.toml').read_text())
        plans = {key: Path(cfg['paths']['tei_dir']) / name for key, name in cfg['documents'].items()}
        sources = ['sogo_seisaku_107-116.xml', 'sokai_031.xml', 'dantai_1-4.xml', 'env6th-chukan_pc.csv', 'env6th-an_pc.csv']
    else:
        plans = {key: analysis / plan / '計画案' / f'7th_energy_plan_{key}.xml' for key in LABELS[plan]}
        sources = ['kihon_seisaku_055-068.xml', 'ene7th_opinions_box.csv', 'ene7th-an_pc.csv']
    def copy(src, kind, name=None):
        dest = target / kind / (name or src.name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        manifest[str(src.relative_to(analysis))] = sha(src)
        return dest
    for key, src in plans.items():
        alias = {'ver1': 'chukan-an_ver1', 'ver2': 'chukan-an_ver2'}.get(key, key)
        name = f'6th_env_plan_{alias}.xml' if plan == 'env6th' else src.name
        dest = copy(src, 'plan_documents', name)
        readers.add(key, LABELS[plan][key], ET.parse(src).getroot(), dest, True)
    for name in sources:
        src = analysis / plan / '意見発言データ' / name
        dest = copy(src, 'source_materials')
        if src.suffix != '.xml':
            continue
        root = ET.parse(src).getroot()
        for tei in root.iter():
            if tei.tag.split('}')[-1] != 'TEI':
                continue
            key = 'source-' + tei.get(XID)
            title_node = tei.find('.//t:titleStmt/t:title', NS)
            title = ''.join(title_node.itertext()) if title_node is not None else key
            readers.add(key, title, tei, dest)
    return readers


def prepare_rows(analysis, plan, manifest):
    cluster = analysis / plan / '要求クラスタリング/runs/final'
    metadata = read_jsonl(cluster / 'metadata.jsonl')
    by_id = {r['request_id']: r for r in metadata}
    if plan == 'env6th':
        base = analysis / plan / '追加実験_最終7版Batch判定_20261028/uncertain_review_20261028/review_overlay'
        files = sorted(base.glob('*/judgments_with_provisional_review.jsonl'))
        rows = []
        for p in files:
            for row in read_jsonl(p):
                row['_publication_source'] = str(p.relative_to(analysis))
                rows.append(row)
        evaluated = {r['request_id'] for r in rows}
        missing = [r for r in metadata if r['request_id'] not in evaluated]
        assert len(missing) == 87
        assert all('meeting-116-' in r['record_id'] and r['consideration_target'] == '第六次環境基本計画答申案' for r in missing)
        for m in missing:
            rows.append({**m, 'judgment': 'not_evaluated', 'judgment_label_ja': '未判定',
                'final_judgment': 'not_evaluated', 'final_judgment_label_ja': '未判定',
                'stage': 'toshin_to_kakugi', 'old_document': 'toshin', 'new_document': 'kakugi',
                'judgment_mode': 'not_evaluated', 'matched_revisions': [],
                'reason': '第116回部会・答申案の最終検討段階の要求。最新の保存済み改訂判定に結果がないため未判定。対応なしを意味しません。',
                '_publication_source': str((cluster / 'metadata.jsonl').relative_to(analysis))})
    else:
        p = analysis / plan / '統合最新結果_全5094要求_20261017/data/energy_latest_integrated.json'
        files = [p]
        # Use display data as an additive layer, preserving all integrated research fields.
        display = json.loads((p.parents[1] / 'viewer_data/all.json').read_text())
        files.append(p.parents[1] / 'viewer_data/all.json')
        by_display = {r['request_id']: r for r in display}
        rows = json.loads(p.read_text())
        rows = [{**r, **by_display[r['request_id']], '_publication_source': str(p.relative_to(analysis))} for r in rows]
        missing = []
    assert len(rows) == len({r['request_id'] for r in rows}) == len(metadata)
    assert set(by_id) == {r['request_id'] for r in rows}
    for p in [*files, cluster / 'metadata.jsonl']:
        manifest[str(p.relative_to(analysis))] = sha(p)
    for r in rows:
        if plan == 'env6th' and r.get('human_review_provisional'):
            previous = r.pop('human_review_provisional')
            r['review_history'] = [{'human_review_provisional': previous,
                'final_judgment_basis': r.get('final_judgment_basis'),
                'effective_judgment_provisional': r.pop('effective_judgment_provisional', None)}]
            # The researcher explicitly confirmed all 44 reviews on 2026-10-30.
            # This promotes their status; no substantive judgment or evidence changes.
            r['human_review'] = {**previous, 'review_status': 'confirmed',
                'confirmed_by': 'researcher', 'confirmed_on': '2026-10-30'}
            r['final_judgment_basis'] = '人手確認済み。元のLLM判定はjudgmentに保持'
            r['effective_judgment'] = r['final_judgment']
        m = by_id[r['request_id']]
        r['source_group'] = r.get('source_group') or m['source_label']
        r['speaker_display'] = r.get('speaker_display') or r.get('speaker_name') or m.get('speaker_or_heading', '')
        r['original_text_display'] = r.get('original_text_display') or r.get('original_text') or r.get('comment') or m.get('original_text', '')
        r['old_document_label'] = r.get('old_document_label') or LABELS[plan].get(r.get('old_document'), '')
        r['new_document_label'] = r.get('new_document_label') or LABELS[plan].get(r.get('new_document'), '')
        r['final_judgment'] = r.get('final_judgment') or r['judgment']
        original_label = r.get('final_judgment_label_ja') or r.get('judgment_label_ja') or r['judgment']
        r['final_judgment_label_ja'] = DISPLAY_JUDGMENTS[r['final_judgment']]
        if original_label != r['final_judgment_label_ja']:
            r['original_final_judgment_label_ja'] = original_label
    return rows, metadata, missing


def attach_navigation(rows, metadata, readers):
    source_map = {m['request_id']: readers.source_ref(m) for m in metadata}
    for r in rows:
        r['source_ref'] = source_map[r['request_id']]
        for revision in r.get('matched_revisions', []):
            attach_revision(r, revision, readers)
        listed = {v.get('alignment_id') for v in r.get('matched_revisions', [])}
        r['additional_evidence'] = []
        for evidence in r.get('document_evidence_quotes', []):
            aid = evidence.get('alignment_id', '')
            if aid not in listed and re.fullmatch(r'[^:]+:(?:p|head|note)\d+', aid):
                doc, eid = aid.split(':')
                r['additional_evidence'].append({**evidence, 'ref': readers.ref(doc, [eid], [evidence.get('quote', '')])})
        manual = r.get('manual_search') or {}
        for rev in manual.get('revisions', []) or []:
            attach_revision(r, rev, readers)
        # Energy manual confirmations use related_revisions / revision too.
        for field in ['related_revisions', 'matched_revisions']:
            for rev in manual.get(field, []) or []:
                attach_revision(r, rev, readers)
        if isinstance(manual.get('revision'), dict):
            attach_revision(r, manual['revision'], readers)
        review = r.get('human_review') or {}
        refs = []
        grouped = {}
        for qualified in review.get('evidence_element_ids', []):
            doc, eid = qualified.split(':', 1)
            grouped.setdefault(doc, []).append(eid)
        for doc, ids in grouped.items():
            refs.append(readers.ref(doc, ids))
        r['review_refs'] = [ref for ref in refs if ref]
    return source_map


def attach_revision(row, rev, readers):
    aid = rev.get('alignment_id', '')
    quotes = [q for q in row.get('document_evidence_quotes', []) if q.get('alignment_id') == aid]
    evidence = [e for e in row.get('evidence', []) if e.get('alignment_id') == aid]
    for side in ['old', 'new']:
        doc = rev.get(side + '_document') or (rev.get('document') if side == 'new' else None) or row.get(side + '_document')
        ids = rev.get(side, [])
        if not ids and side == 'new':
            if rev.get('element_id'):
                ids = [rev['element_id']]
            elif re.match(r'^[^:]+:(?:p|head|note)\d+$', aid):
                doc, eid = aid.split(':')
                ids = [eid]
            elif rev.get('chroma_id'):
                doc, _, eid, *_ = rev['chroma_id'].split(':')
                ids = [eid]
        if not ids:
            rev[side + '_ref'] = None
            continue
        qs = [e.get(side + '_evidence_quote', '') for e in evidence]
        if side == 'new':
            qs += [q.get('quote', '') for q in quotes]
        if row.get('judgment_mode') != 'single_document_presence':
            qs += [rev.get('added_text' if side == 'new' else 'removed_text', '')]
        rev[side + '_ref'] = readers.ref(doc, ids, qs, rev.get(side + '_text', ''))


def build_site(analysis, repo):
    docs = repo / 'docs'
    manifest = {}
    audits = {}
    assets = docs / 'assets'
    assets.mkdir(exist_ok=True)
    for src in (repo / 'scripts/web').iterdir():
        shutil.copy2(src, assets / src.name)
    ASSET_VERSIONS.update({src.name: sha(src)[:12] for src in assets.iterdir() if src.is_file()})
    for plan, title in [('env6th', '第六次環境基本計画'), ('ene7th', '第7次エネルギー基本計画')]:
        readers = build_readers(analysis, docs, plan, manifest)
        rows, metadata, missing = prepare_rows(analysis, plan, manifest)
        source_map = attach_navigation(rows, metadata, readers)
        if readers.issues:
            write_json(repo / 'build_link_issues.json', readers.issues)
            raise ValueError(f'{plan}: {len(readers.issues)} source/ID/text discrepancies; see build_link_issues.json')
        data = docs / 'data' / plan
        full = json.dumps(rows, ensure_ascii=False).encode()
        (data / 'judgments_full.json.gz').write_bytes(gzip.compress(full, mtime=0))
        write_json(data / 'judgments_sample.json', rows[:30])
        with (data / 'judgments_sample.csv').open('w', encoding='utf-8-sig', newline='') as f:
            fields = ['request_id', 'stage', 'source_group', 'judgment', 'final_judgment', 'request_summary', 'reason']
            w = csv.DictWriter(f, fields, extrasaction='ignore', lineterminator='\n'); w.writeheader(); w.writerows(rows[:30])
        # Retain full source records in gzip; omit API diagnostics only from browser payload.
        fields = {'request_id','request_summary','request_quote','original_text_display',
            'source_group','speaker_display','old_document_label','new_document_label','stage',
            'judgment_mode','judgment','judgment_label_ja','final_judgment','final_judgment_label_ja',
            'final_judgment_basis','reason','confidence_components','evidence','document_evidence_quotes',
            'human_review','manual_search','review_refs','source_ref','matched_revisions','additional_evidence',
            'opinion_heading_reference','label','reply','administrative_reply_reference','_publication_source'}
        display = [{k:v for k,v in r.items() if k in fields} for r in rows]
        viewer_dir = docs / 'viewers' / plan
        body = f'<div class="viewer-toolbar"><header><a href="../../">← トップ</a><h1>{title}：改訂対応判定</h1></header><div class="controls viewer-controls"><label>検索<input id="search" placeholder="要求ID・要約・原文・本文ID"></label><label>判定方法<select id="mode"></select></label><label>版間<select id="stage"></select></label><label>資料<select id="source"></select></label><label>表示判定<select id="judgment"></select></label><label>LLM判定<select id="llm"></select></label><label>人手探索<select id="manual"></select></label></div></div><main id="viewer-main"><p id="summary" role="status"></p><p class="legend">黄色枠：本文の対象箇所 ／ 黄色：根拠引用 ／ <ins>緑：追加</ins> ／ <del>赤：削除</del></p><div class="pager"><button id="prev">前へ</button><span id="page"></span><button id="next">次へ</button></div><div id="cards"></div></main>'
        scripts = f'<script id="data" type="application/json">{payload(display)}</script><script src="../../assets/navigation.js"></script><script src="../../assets/judgments.js"></script>'
        (viewer_dir / 'judgments.html').write_text(page(title + ' 改訂対応判定', body, scripts), encoding='utf-8')
        cluster = analysis / plan / '要求クラスタリング/runs/final'
        for name in ['metadata.jsonl', 'assignments.jsonl']:
            src = cluster / name
            manifest[str(src.relative_to(analysis))] = sha(src)
            (data / (name + '.gz')).write_bytes(gzip.compress(src.read_bytes(), mtime=0))
        for name in ['lower_clusters.json', 'upper_clusters.json', 'completion_summary.json']:
            src = cluster / name
            manifest[str(src.relative_to(analysis))] = sha(src)
            shutil.copy2(src, data / name)
        write_json(data / 'cluster_assignments_sample.json', read_jsonl(cluster / 'assignments.jsonl')[:30])
        s = (cluster / 'cluster_explorer.html').read_text()
        manifest[str((cluster / 'cluster_explorer.html').relative_to(analysis))] = sha(cluster / 'cluster_explorer.html')
        injection = f'<link rel="stylesheet" href="../../assets/reader.css"><script id="source-navigation" type="application/json">{payload(source_map)}</script><script src="../../assets/navigation.js"></script><script src="../../assets/clustering-navigation.js"></script>'
        (viewer_dir / 'clustering.html').write_text(version_assets(s.replace('</body>', injection + '</body>')), encoding='utf-8')
        audits[plan] = {'requests': len(rows), 'evaluated': len(rows)-len(missing), 'not_evaluated': len(missing),
            'not_evaluated_requests': [{k:r[k] for k in ['request_id','source_location','policy_stage','consideration_target']} for r in missing],
            'confirmed_human_reviews': sum(bool(r.get('human_review')) for r in rows),
            'source_links': sum(bool(ref) for ref in source_map.values()),
            'reader_documents': len(readers.documents), 'link_verification': dict(readers.stats), 'issues': readers.issues}
        for sub in ['source_materials', 'plan_documents']:
            d = data / sub
            links = ''.join(f'<li><a href="{html.escape(p.name)}">{html.escape(p.name)}</a></li>' for p in sorted(d.glob('*')) if p.name != 'index.html')
            (d / 'index.html').write_text(page(title, f'<main><a href="../../../">← トップ</a><h1>{title}：元データ</h1><ul>{links}</ul></main>', stylesheet='../../../assets/reader.css'))
    write_json(docs / 'data/publication_audit.json', {'build_date': '2026-10-30', 'plans': audits, 'source_sha256': manifest,
        'previous_site_archive': 'backups/site_before_20261030.zip',
        'environment_gap_explanation': '87要求はすべて第116回部会・答申案の最終検討段階。最新版に保存済み判定がなく未判定として保持。',
        'human_review_policy': '環境の人手確認44件は2026-10-30の研究者による全件確認済みとの明示に基づき確認済みとして扱う。判定内容・根拠・元のLLM判定は変更しない。'})
    # Homepage links also bypass cached copies of older viewer HTML.
    index = docs / 'index.html'
    index.write_text(re.sub(r'(href=")(viewers/[^"?]+\.html)(?:\?v=[^"]*)?(\")',
        lambda m: m[1] + m[2] + '?v=' + sha(docs / m[2])[:12] + m[3], index.read_text()), encoding='utf-8')
    # Include every deployed asset (including index and scripts), not only data copies.
    files = sorted(p for p in docs.rglob('*') if p.is_file() and p.name != 'SHA256SUMS.txt')
    (docs / 'SHA256SUMS.txt').write_text(''.join(f'{sha(p)}  {p.relative_to(docs)}\n' for p in files))
    print(json.dumps({'plans': {p:{k:v for k,v in a.items() if k != 'not_evaluated_requests'} for p,a in audits.items()}, 'files': len(files)}, ensure_ascii=False, indent=2))
