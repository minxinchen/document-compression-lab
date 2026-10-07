"""Read-only audit of historical files; never treats logged pass as fresh validation.
Author: Nio (Master).
"""
import argparse
import hashlib
import json
import re
from pathlib import Path


def audit(root):
    rows = []
    raw_dir = root/'papers/raw'
    if not raw_dir.is_dir() or not list(raw_dir.glob('*.md')):
        raise ValueError('no historical raw files')
    for raw in sorted(raw_dir.glob('*.md')):
        compressed = root/'papers/compressed'/raw.name
        review = root/'papers/review_log'/raw.name
        row = {'file':raw.name,'warnings':[]}
        if not compressed.exists() or not review.exists():
            row['warnings'].append('missing_pair_or_review')
            rows.append(row)
            continue
        a,b = raw.read_bytes(),compressed.read_bytes()
        log = review.read_text(encoding='utf-8')
        row.update(source_chars=len(a.decode('utf-8')),draft_chars=len(b.decode('utf-8')),
                   source_sha256=hashlib.sha256(a).hexdigest(),draft_sha256=hashlib.sha256(b).hexdigest())
        row['ratio'] = row['draft_chars']/row['source_chars'] if row['source_chars'] else None
        fields = dict(re.findall(r'^- (raw_chars|final_compressed_chars|total_iterations|final_status):\s*(.+)$', log, re.M))
        row['historical_claims'] = fields
        for field,key in [('raw_chars','source_chars'),('final_compressed_chars','draft_chars')]:
            try:
                if int(fields[field]) != row[key]:
                    row['warnings'].append(field+'_mismatch')
            except (KeyError,ValueError):
                row['warnings'].append(field+'_missing_or_invalid')
        if 'carried over' in log:
            row['warnings'].append('review_carried_from_prior_iteration')
        row['issue_entries'] = len(re.findall(r'^- [HS]\d+ \([^)]+\):', log,re.M))
        # Historical logs have no immutable hash binding, even where counts agree.
        row['validation_status'] = 'historical_record_only'
        rows.append(row)
    paired = [r for r in rows if 'draft_chars' in r]
    raw_total=sum(r['source_chars'] for r in paired)
    comp_total=sum(r['draft_chars'] for r in paired)
    return dict(schema='historical-audit-v1',validation='file_counts_and_log_consistency_only',
                files=len(rows),paired_files=len(paired),source_chars=raw_total,draft_chars=comp_total,
                weighted_retention_ratio=comp_total/raw_total if raw_total else None,
                issue_entries=sum(r['issue_entries'] for r in paired),
                files_with_warnings=sum(bool(r['warnings']) for r in rows),rows=rows)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    args=p.parse_args()
    print(json.dumps(audit(args.root),ensure_ascii=False,indent=2))
