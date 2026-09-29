from __future__ import annotations

import csv
import gzip
import hashlib
import html
import json
from pathlib import Path
import re
import shutil


REPO = Path(__file__).resolve().parents[1]
ANALYSIS = REPO.parent
DOCS = REPO / "docs"

VIEWER_FIELDS = (
    "request_id", "request_summary", "original_text_display", "request_quote",
    "opinion_heading_reference", "stage", "old_document_label", "new_document_label",
    "source_group", "warning_status", "judgment", "judgment_label_ja",
    "confidence_components", "matched_revisions", "judgment_mode", "source_stage",
    "speaker_display", "validation_warnings", "reason", "reply",
    "administrative_reply_reference",
)

PLANS = {
    "env6th": {
        "title": "第六次環境基本計画",
        "cluster": ANALYSIS / "env6th/要求クラスタリング/runs/final",
        "judgment": ANALYSIS / "env6th/改訂判定/outputs/latest_20260921/environment_latest_integrated.json",
        "judgment_viewer": ANALYSIS / "env6th/改訂判定/outputs/latest_20260921/environment_latest_integrated_viewer.html",
        "sources": [
            ANALYSIS / "env6th/意見発言データ/sogo_seisaku_107-116.xml",
            ANALYSIS / "env6th/意見発言データ/sokai_031.xml",
            ANALYSIS / "env6th/意見発言データ/dantai_1-4.xml",
            ANALYSIS / "env6th/意見発言データ/env6th-chukan_pc.csv",
            ANALYSIS / "env6th/意見発言データ/env6th-an_pc.csv",
        ],
        "documents": list((ANALYSIS / "env6th/計画案").glob("*.xml")),
    },
    "ene7th": {
        "title": "第7次エネルギー基本計画",
        "cluster": ANALYSIS / "ene7th/要求クラスタリング/runs/final",
        "judgment": ANALYSIS / "ene7th/改訂判定/outputs/latest_20260921/energy_latest_integrated.json",
        "judgment_viewer": ANALYSIS / "ene7th/改訂判定/outputs/latest_20260921/energy_latest_integrated_viewer.html",
        "sources": [
            ANALYSIS / "ene7th/意見発言データ/kihon_seisaku_055-068.xml",
            ANALYSIS / "ene7th/意見発言データ/ene7th_opinions_box.csv",
            ANALYSIS / "ene7th/意見発言データ/ene7th-an_pc.csv",
        ],
        "documents": [
            ANALYSIS / "ene7th/計画案/7th_energy_plan_kokkaku.xml",
            ANALYSIS / "ene7th/計画案/7th_energy_plan_genan.xml",
            ANALYSIS / "ene7th/計画案/7th_energy_plan_an.xml",
            ANALYSIS / "ene7th/計画案/7th_energy_plan_saisyu.xml",
        ],
    },
}


def compact(item: dict) -> dict:
    return {key: item[key] for key in VIEWER_FIELDS if key in item and item[key] not in (None, "", [], {})}


def write_gzip(source: Path, target: Path) -> None:
    target.write_bytes(gzip.compress(source.read_bytes(), compresslevel=9, mtime=0))


def sample_rows(rows: list[dict], limit: int = 36) -> list[dict]:
    chosen, seen = [], set()
    for row in rows:
        key = (row.get("stage"), row.get("judgment"), row.get("source_group"))
        if key not in seen:
            chosen.append(compact(row))
            seen.add(key)
        if len(chosen) >= limit:
            break
    return chosen


def write_sample_csv(rows: list[dict], target: Path) -> None:
    fields = ["request_id", "stage", "source_group", "judgment", "warning_status", "request_summary", "reason"]
    with target.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_directory_index(directory: Path, title: str) -> Path:
    links = "".join(
        f'<li><a href="{html.escape(path.name)}">{html.escape(path.name)}</a> '
        f'<small>({path.stat().st_size:,} bytes)</small></li>'
        for path in sorted(directory.iterdir()) if path.is_file() and path.name != "index.html"
    )
    page = f'''<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title><link rel="stylesheet" href="../../../assets/site.css"></head><body><main><p><a href="../../../">← トップへ</a></p><h1>{html.escape(title)}</h1><ul>{links}</ul></main></body></html>'''
    target = directory / "index.html"
    target.write_text(page, encoding="utf-8")
    return target


def build_plan(plan_id: str, cfg: dict) -> list[Path]:
    built: list[Path] = []
    cluster_dir = DOCS / "viewers" / plan_id
    data_dir = DOCS / "data" / plan_id
    source_dir = data_dir / "source_materials"
    document_dir = data_dir / "plan_documents"
    for directory in (cluster_dir, data_dir, source_dir, document_dir):
        directory.mkdir(parents=True, exist_ok=True)

    cluster_viewer = cluster_dir / "clustering.html"
    shutil.copy2(cfg["cluster"] / "cluster_explorer.html", cluster_viewer)
    built.append(cluster_viewer)

    rows = json.loads(cfg["judgment"].read_text(encoding="utf-8"))
    slim = [compact(row) for row in rows]
    payload = json.dumps(slim, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    template = cfg["judgment_viewer"].read_text(encoding="utf-8")
    viewer = re.sub(
        r'(<script id="data" type="application/json">).*?(</script>)',
        lambda match: match.group(1) + payload + match.group(2),
        template,
        count=1,
        flags=re.S,
    )
    judgment_viewer = cluster_dir / "judgments.html"
    judgment_viewer.write_text(viewer, encoding="utf-8")
    built.append(judgment_viewer)

    for name in ("metadata.jsonl", "assignments.jsonl"):
        target = data_dir / f"{name}.gz"
        write_gzip(cfg["cluster"] / name, target)
        built.append(target)
    for name in ("lower_clusters.json", "upper_clusters.json", "completion_summary.json"):
        target = data_dir / name
        shutil.copy2(cfg["cluster"] / name, target)
        built.append(target)

    judgments_gz = data_dir / "judgments_full.json.gz"
    write_gzip(cfg["judgment"], judgments_gz)
    built.append(judgments_gz)

    sample = sample_rows(rows)
    sample_json = data_dir / "judgments_sample.json"
    sample_json.write_text(json.dumps(sample, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    sample_csv = data_dir / "judgments_sample.csv"
    write_sample_csv(sample, sample_csv)
    built.extend((sample_json, sample_csv))

    assignment_sample = []
    with (cfg["cluster"] / "assignments.jsonl").open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                assignment_sample.append(json.loads(line))
            if len(assignment_sample) == 30:
                break
    cluster_sample = data_dir / "cluster_assignments_sample.json"
    cluster_sample.write_text(json.dumps(assignment_sample, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    built.append(cluster_sample)

    for source in cfg["sources"]:
        target = source_dir / source.name
        shutil.copy2(source, target)
        built.append(target)
    for source in cfg["documents"]:
        target = document_dir / source.name
        shutil.copy2(source, target)
        built.append(target)
    built.append(write_directory_index(source_dir, f"{cfg['title']}：意見・議事録の元データ"))
    built.append(write_directory_index(document_dir, f"{cfg['title']}：計画文書の版別データ"))
    return built


def main() -> None:
    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / ".nojekyll").touch()
    built = [DOCS / ".nojekyll"]
    for plan_id, cfg in PLANS.items():
        built.extend(build_plan(plan_id, cfg))

    checksums = []
    for path in sorted(set(built)):
        checksums.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(DOCS)}")
    (DOCS / "SHA256SUMS.txt").write_text("\n".join(checksums) + "\n", encoding="utf-8")
    print(json.dumps({"files": len(built), "docs": str(DOCS)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
