"""Add project licensing to public TEI copies without reserializing the text."""

import re
import xml.etree.ElementTree as ET

TEI = '{http://www.tei-c.org/ns/1.0}'
CC_BY = 'https://creativecommons.org/licenses/by/4.0/'
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
