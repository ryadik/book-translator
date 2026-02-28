"""
Glossary Manager — TSV export/import utilities.

Provides functions to export glossary terms to TSV format,
import terms from TSV files, and generate approval TSV buffers
for LLM-discovered terms.
"""
import sys
from pathlib import Path
from typing import List, Dict, TextIO

from db import add_term, get_terms, init_glossary_db

TSV_HEADER = '# source_term\ttarget_term\tcomment'


def export_tsv(db_path: Path, output: TextIO = None,
               source_lang: str = 'ja', target_lang: str = 'ru') -> int:
    """Export glossary to TSV format. Returns number of terms exported."""
    out = output or sys.stdout
    terms = get_terms(db_path, source_lang, target_lang)
    out.write(TSV_HEADER + '\n')
    for term in terms:
        line = f"{term['term_source']}\t{term['term_target']}\t{term.get('comment', '')}"
        out.write(line + '\n')
    return len(terms)


def import_tsv(db_path: Path, tsv_path: Path,
               source_lang: str = 'ja', target_lang: str = 'ru') -> int:
    """Import terms from TSV file into glossary database.
    Lines starting with # are ignored.
    Format: source_term<TAB>target_term[<TAB>comment]
    Returns: number of terms imported
    """
    count = 0
    with open(tsv_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split('\t')
            if len(parts) < 2:
                continue  # skip malformed lines
            term_source = parts[0].strip()
            term_target = parts[1].strip()
            comment = parts[2].strip() if len(parts) > 2 else ''
            if term_source and term_target:
                add_term(db_path, term_source, term_target,
                         source_lang, target_lang, comment)
                count += 1
    return count


def generate_approval_tsv(terms: List[Dict], output_path: Path):
    """Generate a TSV file with LLM-discovered terms for user approval.
    This is the TSV 'approval buffer' — user edits this, then
    the approved version is imported into the DB.
    """
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('# Проверьте и отредактируйте термины ниже\n')
        f.write('# Удалите строки, которые не нужны\n')
        f.write('# Формат: исходный_термин<TAB>перевод<TAB>комментарий\n')
        f.write(TSV_HEADER + '\n')
        for term in terms:
            source = term.get('term_jp', term.get('term_source', ''))
            target = term.get('term_ru', term.get('term_target', ''))
            comment = term.get('comment', '')
            f.write(f"{source}\t{target}\t{comment}\n")
