"""Validate publication completeness, input immutability and every reader target."""
from collections import Counter
import gzip
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs'
AUDIT = json.loads((DOCS / 'data/publication_audit.json').read_text())


class ReaderParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'source-block' in attrs.get('class', '').split():
            self.ids.append(attrs['id'])


targets = {}
for p in (DOCS / 'readers').glob('*/*.html'):
    parser = ReaderParser(); parser.feed(p.read_text())
    assert len(set(parser.ids)) == len(parser.ids), p
    targets[str(p.relative_to(DOCS))] = set(parser.ids)

link_count = 0
def refs(value):
    global link_count
    if isinstance(value, dict):
        if {'url','ids','quotes','role'} <= value.keys():
            target = value['url'].removeprefix('../../')
            assert target in targets, target
            assert set(value['ids']) <= targets[target], (target, value['ids'])
            link_count += 1
        else:
            for v in value.values(): refs(v)
    elif isinstance(value, list):
        for v in value: refs(v)

for name, digest in AUDIT['source_sha256'].items():
    assert hashlib.sha256((ROOT.parent / name).read_bytes()).hexdigest() == digest, name

for plan, expected in [('env6th',2298),('ene7th',5094)]:
    data = DOCS / 'data' / plan
    rows = json.loads(gzip.decompress((data / 'judgments_full.json.gz').read_bytes()))
    metadata = [json.loads(l) for l in gzip.decompress((data / 'metadata.jsonl.gz').read_bytes()).decode().splitlines()]
    assert len(rows) == len({r['request_id'] for r in rows}) == expected
    assert {r['request_id'] for r in rows} == {r['request_id'] for r in metadata}
    assert sum(r['judgment'] == 'not_evaluated' for r in rows) == (87 if plan == 'env6th' else 0)
    labels = Counter(r['final_judgment_label_ja'] for r in rows)
    expected_labels = ({'対応あり':295,'一部対応':822,'対応なし':1089,'判定不可':5,'未判定':87}
        if plan == 'env6th' else {'対応あり':590,'一部対応':1799,'対応なし':2702,'判定不可':3})
    assert labels == expected_labels, labels
    if plan == 'env6th':
        reviews = [r for r in rows if r.get('human_review')]
        assert len(reviews) == 44
        assert all(r['human_review']['review_status'] == 'confirmed' for r in reviews)
        assert all('human_review_provisional' not in r for r in rows)
        overlay = ROOT.parent / 'env6th/追加実験_最終7版Batch判定_20261028/uncertain_review_20261028/review_overlay'
        original_review = {r['request_id']:r for p in overlay.glob('*/judgments_with_provisional_review.jsonl')
            for line in p.open() if (r := json.loads(line)).get('human_review_provisional')}
        for r in reviews:
            original = original_review[r['request_id']]
            assert r['final_judgment'] == original['final_judgment']
            assert r['final_judgment_label_ja'] == original['final_judgment_label_ja']
            assert r['human_review']['rationale'] == original['human_review_provisional']['rationale']
        for p in (ROOT.parent / 'env6th/追加実験_最終7版Batch判定_20261028/quote_corrected').glob('*/judgments_quote_corrected.jsonl'):
            by_id = {r['request_id']:r for r in rows}
            for line in p.open():
                original = json.loads(line)
                assert by_id[original['request_id']]['judgment'] == original['judgment']
                assert by_id[original['request_id']]['reason'] == original['reason']
    refs(rows)
    viewer = (DOCS / 'viewers' / plan / 'judgments.html').read_text()
    display = json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>', viewer, re.S)[1])
    assert len(display) == expected
    assert (DOCS / 'viewers' / plan / 'judgments.html').stat().st_size < 100 * 1024**2

with zipfile.ZipFile(ROOT / 'backups/site_before_20261030.zip') as z:
    assert z.testzip() is None
    assert 'docs/viewers/env6th/judgments.html' in z.namelist()
    assert 'docs/viewers/ene7th/judgments.html' in z.namelist()

for line in (DOCS / 'SHA256SUMS.txt').read_text().splitlines():
    digest,name=line.split('  ',1)
    assert hashlib.sha256((DOCS / name).read_bytes()).hexdigest() == digest, name
result = {'source_files_unchanged':len(AUDIT['source_sha256']), 'reader_documents':len(targets),
    'reader_links_verified':link_count, 'environment_requests':2298, 'environment_not_evaluated':87,
    'energy_requests':5094, 'backup_archive_verified':True, 'checksums_verified':True}
(ROOT / 'verification-data.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(result,ensure_ascii=False,indent=2))
