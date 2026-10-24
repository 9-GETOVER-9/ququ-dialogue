"""Offline checks for the published documents and course manifest."""
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit


def main():
    root = Path(__file__).resolve().parent.parent
    if os.name == 'nt' and not str(root).startswith('\\\\?\\'):
        root = Path('\\\\?\\' + str(root))
    problems = []
    manifest = json.loads((root / 'courses/manifest.json').read_text(encoding='utf-8'))
    listed = set()
    for item in manifest['files']:
        rel = item['path']
        path = root / rel
        if rel in listed or '..' in Path(rel).parts or not rel.startswith('courses/'):
            problems.append(('invalid_manifest_path', rel))
            continue
        listed.add(rel)
        if not path.is_file():
            problems.append(('missing_course', rel))
            continue
        raw = path.read_bytes()
        if len(raw) != item['bytes'] or hashlib.sha256(raw).hexdigest() != item['sha256']:
            problems.append(('course_hash_mismatch', rel))
    actual = {p.relative_to(root).as_posix() for p in (root / 'courses').rglob('*')
              if p.is_file() and p.name not in ('README.md', 'manifest.json')}
    if listed != actual:
        problems.append(('course_inventory_mismatch', str(len(actual ^ listed))))

    patterns = {
        'private_key': r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
        'github_credential': r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{50,})\b',
        'api_credential': r'\bsk-[A-Za-z0-9_-]{24,}\b',
        'machine_path': r'(?i)(?:[A-Z]:[\\/](?:Users|codex|桌面|文档)[\\/]|' + '/' + r'Users/[^/]+/)',
    }
    allowed = {'.md', '.txt', '.json', '.srt', '.py'}
    files = 0
    for path in root.rglob('*'):
        rel = path.relative_to(root)
        if '.git' in rel.parts or '__pycache__' in rel.parts:
            continue
        if path.is_symlink():
            problems.append(('unexpected_symlink', rel.as_posix()))
            continue
        if not path.is_file():
            continue
        files += 1
        if path.suffix not in allowed and path.name not in ('.gitignore', '.gitattributes'):
            problems.append(('unexpected_file_type', rel.as_posix()))
        if path.stat().st_size >= 100 * 1024 * 1024:
            problems.append(('oversized_file', rel.as_posix()))
        content = path.read_text(encoding='utf-8')
        for name, pattern in patterns.items():
            if re.search(pattern, content):
                problems.append((name, rel.as_posix()))
        if path.suffix == '.md' and (rel.parts[0] != 'courses' or path.name == 'README.md'):
            for link in re.findall(r'\]\(([^)]+)\)', content):
                parsed = urlsplit(link)
                if parsed.scheme in ('https', 'http', 'mailto') or link.startswith('#'):
                    continue
                target = (path.parent / unquote(parsed.path)).resolve()
                if parsed.scheme or not target.is_relative_to(root) or not target.exists():
                    problems.append(('broken_document_link', rel.as_posix()))
    print(json.dumps({'status': 'failed' if problems else 'passed',
                      'course_files': len(listed), 'publication_files': files,
                      'problems': problems}, ensure_ascii=True, indent=2))
    return bool(problems)


if __name__ == '__main__':
    sys.exit(main())
