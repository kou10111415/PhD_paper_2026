"""Prepare metadata for public TEI copies while preserving the text bytes."""

import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

TEI = '{http://www.tei-c.org/ns/1.0}'
XML_ID = '{http://www.w3.org/XML/1998/namespace}id'
CC_BY = 'https://creativecommons.org/licenses/by/4.0/'
ENCODER = '石井康平'
SOURCE_REFERENCES = json.loads(Path(__file__).with_name('public_tei_sources.json').read_text(encoding='utf-8'))
ENV_COMMITTEE = '中央環境審議会総合政策部会'
ENERGY_COMMITTEE = '総合資源エネルギー調査会基本政策分科会'
MINUTES_AUTHORS = {
    'dantai_1-4.xml': ENV_COMMITTEE,
    'sogo_seisaku_107-116.xml': ENV_COMMITTEE,
    'sokai_031.xml': '中央環境審議会',
    'kihon_seisaku_055-068.xml': ENERGY_COMMITTEE,
}
OPINION_TITLE = re.compile(r'第\d+回基本政策分科会 (.+?)委員 追加意見')
DATE_RANGE = re.compile(r'(\d{4}-\d{2}-\d{2})/(\d{4}-\d{2}-\d{2})')
WORKING_TITLE_SUFFIX = re.compile(r'\s*［(?:統合試作版|TEI統合版)］\s*$')
HEADER = re.compile(rb'<teiHeader(?:\s[^>]*)?>.*?</teiHeader>', re.S)
PUBLICATION = re.compile(rb'(<publicationStmt(?:\s[^>]*)?>)(.*?)(\n([ \t]*)</publicationStmt>)', re.S)
LICENCE = (
    f'<licence target="{CC_BY}">本プロジェクトによるTEI符号化およびメタデータのうち、'
    '本プロジェクトが許諾できる部分は、Creative Commons 表示 4.0 国際（CC BY 4.0）で提供します。'
    '原資料および第三者が権利を持つ内容には、それぞれの利用条件が適用されます。</licence>'
).encode()


def licensed_public_copy(data):
    root = ET.fromstring(data)
    publications = []
    for header in root.iter(TEI + 'teiHeader'):
        statement = header.find(f'{TEI}fileDesc/{TEI}publicationStmt')
        if statement is None:
            raise ValueError('TEI header has no publicationStmt')
        publications.append(statement)

    def update(match):
        statement = next(pending)
        # Preserve any existing licensing or access terms.
        if statement.find(f'.//{TEI}availability') is not None or statement.find(f'.//{TEI}licence') is not None:
            return match[0]
        start, body, end, indent = match.groups()
        child_indent = indent + b'  '
        detail_indent = child_indent + b'  '
        extra = b''
        if all(c.tag == TEI + 'p' for c in statement):
            # The prose-only and structured forms of publicationStmt cannot mix.
            paragraphs = re.findall(rb'<p(?:\s[^>]*)?>.*?</p>|<p\s*/>', body, re.S)
            if len(paragraphs) != len(statement):
                raise ValueError('Unsupported prose publicationStmt')
            extra = b''.join(b'\n' + detail_indent + raw
                             for raw, p in zip(paragraphs, statement)
                             if ''.join(p.itertext()).strip() or p.attrib)
            body = b'\n' + child_indent + b'<authority>PhD_paper_2026</authority>'
        return (start + body + b'\n' + child_indent + b'<availability>' + extra
                + b'\n' + detail_indent + LICENCE + b'\n' + child_indent + b'</availability>' + end)

    pending = iter(publications)

    def update_header(match):
        header, count = PUBLICATION.subn(update, match[0])
        if count != 1:
            raise ValueError('Expected one editable publicationStmt per teiHeader')
        return header

    result, count = HEADER.subn(update_header, data)
    if not publications or count != len(publications):
        raise ValueError('Could not account for all TEI headers')
    ET.fromstring(result)
    return result


def record_source_metadata(source, citation, reference, filename, owner, key, people):
    bibliographies = [bibl for bibl in source.iter(TEI + 'bibl') if bibl is not citation]
    for bibl in bibliographies or [citation]:
        if key.startswith('additional-meeting-'):
            title = bibl.findtext(TEI + 'title', '')
            match = OPINION_TITLE.fullmatch(title)
            if match is None:
                raise ValueError(f'No contributor in additional opinion title: {title}')
            authors = [match[1]]
        elif key.startswith('pre-meeting-'):
            # These TEI documents transcribe the committee members' written submissions.
            contributors = dict.fromkeys(u.get('who', '').removeprefix('#') for u in owner.iter(TEI + 'u'))
            authors = [people[contributor] for contributor in contributors]
        else:
            authors = [reference.get('author') or MINUTES_AUTHORS[filename]]
        if bibl.find(TEI + 'author') is None:
            for position, name in enumerate(authors):
                author = ET.Element(TEI + 'author')
                author.text = name
                bibl.insert(position, author)

        date = bibl.find(TEI + 'date')
        if date is None and 'date' in reference:
            date = ET.SubElement(bibl, TEI + 'date', {'when': reference['date']})
            date.text = reference['date']
            if 'dateType' in reference:
                date.set('type', reference['dateType'])
        elif date is not None and filename in MINUTES_AUTHORS:
            period = DATE_RANGE.fullmatch(date.text or '')
            if period:
                date.attrib.pop('when', None)
                date.attrib.update({'from': period[1], 'to': period[2], 'type': 'coverage'})
            elif key.startswith('meeting'):
                date.attrib.setdefault('type', 'meeting')


def prepare_public_tei(data, filename):
    """Normalize publication metadata and link the official source for each header."""
    data = licensed_public_copy(data)
    root = ET.fromstring(data)
    references = SOURCE_REFERENCES[filename]
    people = {
        person.get(XML_ID): ''.join(part.strip() for part in name.itertext())
        for person in root.iter(TEI + 'person')
        if (name := person.find(TEI + 'persName')) is not None
    }
    headers = []
    used_keys = set()
    for owner in root.iter():
        header = owner.find(TEI + 'teiHeader')
        if header is None:
            continue
        key = owner.get(XML_ID, 'root')
        used_keys.add(key)
        reference = references[key]
        file_desc = header.find(TEI + 'fileDesc')
        title_stmt = file_desc.find(TEI + 'titleStmt')
        for title in title_stmt.findall(TEI + 'title'):
            if title.text:
                title.text = WORKING_TITLE_SUFFIX.sub('', title.text)
        if not any(
            responsibility.findtext(TEI + 'resp') == 'TEI符号化'
            and ENCODER in [name.text for name in responsibility.findall(TEI + 'name')]
            for responsibility in title_stmt.findall(TEI + 'respStmt')
        ):
            responsibility = ET.SubElement(title_stmt, TEI + 'respStmt')
            ET.SubElement(responsibility, TEI + 'resp').text = 'TEI符号化'
            ET.SubElement(responsibility, TEI + 'name').text = ENCODER

        publication = file_desc.find(TEI + 'publicationStmt')
        original_publishers = publication.findall(TEI + 'publisher')
        for child in list(publication):
            if child.tag in {TEI + tag for tag in ('authority', 'publisher', 'distributor', 'date')}:
                publication.remove(child)
        distributor = ET.Element(TEI + 'distributor')
        distributor.text = ENCODER
        publication.insert(0, distributor)
        date = ET.Element(TEI + 'date', {'when': '2026-09-30'})
        date.text = '2026年9月30日'
        publication.insert(1, date)

        source = file_desc.find(TEI + 'sourceDesc')
        citation = source.find(f'{TEI}bibl[@type="sourceReference"]')
        if citation is None:
            citation = ET.SubElement(source, TEI + 'bibl', {'type': 'sourceReference'})
        if 'title' in reference and citation.find(TEI + 'title') is None:
            ET.SubElement(citation, TEI + 'title').text = reference['title']
        citation.extend(original_publishers)
        # Keep the input filename or conversion note in the source citation.
        for paragraph in source.findall(TEI + 'p'):
            source.remove(paragraph)
            paragraph.tag = TEI + 'note'
            citation.append(paragraph)
        record_source_metadata(source, citation, reference, filename, owner, key, people)
        for field, label in (
            ('document', '原資料'),
            ('page', '公開・配付資料ページ'),
            ('related', '関連資料'),
        ):
            for old_link in citation.findall(f'{TEI}ref[@type="{field}"]'):
                citation.remove(old_link)
            if field in reference:
                link = ET.SubElement(citation, TEI + 'ref', {'type': field, 'target': reference[field]})
                link.text = label
        headers.append(header)

    if used_keys != references.keys():
        raise ValueError(f'Unused source references for {filename}: {references.keys() - used_keys}')
    pending = iter(headers)
    ET.register_namespace('', TEI[1:-1])

    def serialize_header(match):
        header = next(pending)
        indent = len(data[data.rfind(b'\n', 0, match.start()) + 1:match.start()])
        ET.indent(header, space='  ')
        # The surrounding TEI or teiCorpus already declares the default namespace.
        rendered = ET.tostring(header, encoding='utf-8').replace(
            b' xmlns="http://www.tei-c.org/ns/1.0"', b'', 1
        ).rstrip()
        return rendered.replace(b'\n', b'\n' + b' ' * indent)

    result, count = HEADER.subn(serialize_header, data)
    if count != len(headers):
        raise ValueError(f'Could not account for all TEI headers in {filename}')
    ET.fromstring(result)
    return result
