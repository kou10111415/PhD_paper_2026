"""Publish the saved revision-judgment prompts as readable, linked pages."""
import hashlib
import html
import json
import re


def publish_prompts(analysis, docs, manifest):
    def read(path):
        manifest[str(path.relative_to(analysis))] = hashlib.sha256(path.read_bytes()).hexdigest()
        return path.read_text(encoding='utf-8')

    energy = analysis / 'ene7th/プロンプト全文確認_20261018/プロンプト全文一覧.txt'
    energy_text = read(energy)
    environment = analysis / 'env6th/追加実験_最終7版Batch判定_20261028'
    sections = []
    for family in ('部会', '総会', '団体意見交換会', 'パブリックコメント'):
        directory = environment / family / 'review'
        system = read(directory / 'system_prompt.txt')
        sections.append((family + '／新旧比較・システムプロンプト全文', system))
        # Match each published example against a saved API input.
        preparation = json.loads(read(environment / family / 'preparation/manifest.json'))
        sent = set()
        for job in preparation['jobs']:
            path = environment / family / 'inputs' / job['path'].rsplit('/', 1)[-1]
            text = read(path)
            assert hashlib.sha256(path.read_bytes()).hexdigest() == job['sha256']
            for line in text.splitlines():
                messages = json.loads(line)['body']['input']
                sent.add(tuple(message['content'].strip() for message in messages))
        for path in sorted(directory.glob('*_full_user_prompt.txt')):
            user = read(path)
            assert (system.strip(), user.strip()) in sent, path
            sections.append((family + '／' + path.name.removesuffix('_full_user_prompt.txt')
                             + '・ユーザープロンプト全文の入力例', user))
    presence = environment / '単一文書_ver1/inputs/pilot.jsonl'
    example = json.loads(read(presence).splitlines()[0])['body']['input']
    for message in example:
        role = 'システムプロンプト全文' if message['role'] == 'system' else 'ユーザープロンプト全文の入力例'
        sections.append(('部会／単一文書の記載有無判定・' + role, message['content']))
    env_text = '\n\n'.join(title + '\n\n' + text for title, text in sections)
    # The existing energy export contains complete systems and symbolic user templates.
    blocks = re.split(r'={70}\s*\n', energy_text)
    energy_sections = [
        (blocks[i].strip(), blocks[i + 1].strip())
        for i in range(1, len(blocks) - 1, 2)
    ]
    if not energy_sections:
        raise ValueError('No sections in the energy prompt export')
    for plan, label, text, entries, description in (
        ('env6th', '第六次環境基本計画', env_text, sections,
         '新旧比較と単一文書の記載有無判定に用いたシステムプロンプト全文と、要求・本文候補を含むユーザープロンプト全文の入力例です。入力例の要求と本文候補は判定ごとに変わります。'),
        ('ene7th', '第7次エネルギー基本計画', energy_text, energy_sections,
         '分科会・委員追加意見、意見箱、パブリックコメントの判定に用いたシステムプロンプト全文と、ユーザープロンプトのテンプレートです。波括弧の部分には要求や本文候補が入ります。'),
    ):
        directory = docs / 'prompts' / plan
        directory.mkdir(parents=True, exist_ok=True)
        (directory / 'prompts.txt').write_text(text, encoding='utf-8')
        navigation = ''.join(f'<li><a href="#prompt-{i}">{html.escape(title)}</a></li>'
                             for i, (title, _) in enumerate(entries))
        body = ''.join(f'<section id="prompt-{i}"><h2>{html.escape(title)}</h2>'
                       f'<pre>{html.escape(content)}</pre></section>'
                       for i, (title, content) in enumerate(entries))
        (directory / 'index.html').write_text(
            '<!doctype html><html lang="ja"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{label}の改訂判定プロンプト全文</title>'
            '<link rel="stylesheet" href="../../assets/site.css">'
            '<style>pre{white-space:pre-wrap;overflow-wrap:anywhere;background:white;padding:20px;'
            'border:1px solid #d9e2ec;line-height:1.8}section{scroll-margin-top:20px}'
            'h2{overflow-wrap:anywhere}nav a{color:#155d8a}</style></head><body>'
            f'<main><a href="../../">← トップ</a><h1>{label}の改訂判定プロンプト全文</h1>'
            f'<p>{description}</p><p><a href="prompts.txt">全文をテキストで開く</a></p>'
            f'<nav aria-label="プロンプトの目次"><ul>{navigation}</ul></nav>{body}'
            '</main></body></html>', encoding='utf-8')
