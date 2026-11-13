#!/usr/bin/env python3
"""Build the passphrase wordlists (main + kids) from the curated TSV files.

The curated files in data/wordlists/curated/ are the source of truth: one row per
candidate lemma with its forms and the review decisions (keep, kid, ...).
This script applies those decisions plus hard safety checks and writes the JSON
wordlists consumed by ger-morph-pw-gen's SentenceGenerator.
"""

import csv
import json
import logging
import math
import re
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Set

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
CURATED_DIR = ROOT / 'data' / 'wordlists' / 'curated'
BLOCKLIST_PATH = ROOT / 'data' / 'wordlists' / 'blocklist.txt'
OUTPUT_DIR = ROOT / 'data' / 'output'

# Every character must type identically on German QWERTZ and US QWERTY:
# no y/z (swapped), no umlauts/ß (missing on QWERTY).
LOWER_WORD = re.compile(r'^[a-x]+$')
NOUN_WORD = re.compile(r'^[A-X][a-x]+$')

# Wiktionary usage tags covering every sense of a word, e.g. "vulgar:1/1".
# "derogatory" alone is not excluded: Wiktionary uses it for merely pejorative words (Kitsch, Ramsch).
FULLY_OFFENSIVE = re.compile(r'(vulgar|offensive|slur):(\d+)/\2\b')

LICENSE = 'CC BY-SA 4.0'
ATTRIBUTION = (
    'Word forms and usage tags: Wiktionary contributors (via kaikki.org), CC BY-SA 4.0. '
    'Frequencies: wordfreq (Robyn Speer), CC BY-SA 4.0. '
    'Kids-list hints: LaRS-Wortliste / Grundwortschatz Berlin (LISUM), CC BY-SA 4.0.'
)


def read_tsv(path: Path) -> List[Dict[str, str]]:
    """Read a TSV file with a header row into a list of dicts"""
    with path.open('r', encoding='utf-8', newline='') as f:
        return list(csv.DictReader(f, delimiter='\t'))


def load_blocklist(path: Path) -> Set[str]:
    """Load lowercase blocked words, ignoring comments and blank lines"""
    if not path.exists():
        return set()
    with path.open('r', encoding='utf-8') as f:
        return {
            line.strip().lower()
            for line in f
            if line.strip() and not line.startswith('#')
        }


def is_flagged(row: Dict[str, str], col: str) -> bool:
    return row.get(col, '0').strip() == '1'


def is_blocked(row: Dict[str, str], forms: Iterable[str], blocklist: Set[str]) -> bool:
    """True if any form is blocklisted or every sense is tagged offensive"""
    if any(form.lower() in blocklist for form in forms):
        return True
    return bool(FULLY_OFFENSIVE.search(row.get('flags', '')))


def build_nouns(rows: List[Dict[str, str]], blocklist: Set[str], kids: bool) -> List[dict]:
    """Select nouns: kept, gender confirmed, picturable, layout-safe, unique nom and acc forms"""
    result: List[dict] = []
    seen: Dict[str, Set[str]] = {'nom': set(), 'acc': set()}
    for row in rows:
        if not (is_flagged(row, 'keep') and is_flagged(row, 'gender_ok')):
            continue
        # Concrete things and living beings are far easier to picture, and so to remember,
        # than abstract nouns; costs under 1 bit per noun slot.
        if not (is_flagged(row, 'concrete') or is_flagged(row, 'animate')):
            continue
        if kids and not is_flagged(row, 'kid'):
            continue
        nom, acc, gender = row['nom_sg'], row['acc_sg'], row['gender']
        if not (NOUN_WORD.match(nom) and NOUN_WORD.match(acc)) or gender not in {'m', 'f', 'n'}:
            logger.warning(f"Skipping noun with unsafe form: {nom}/{acc}")
            continue
        if is_blocked(row, [row['lemma'], nom, acc], blocklist):
            continue
        # Drache and Drachen (kite) share the accusative "Drachen"; keep the more frequent one
        if nom in seen['nom'] or acc in seen['acc']:
            continue
        seen['nom'].add(nom)
        seen['acc'].add(acc)
        result.append({'g': gender, 'nom': nom, 'acc': acc})
    return sorted(result, key=lambda n: n['nom'])


def build_adjectives(rows: List[Dict[str, str]], blocklist: Set[str], kids: bool) -> List[dict]:
    """Select adjectives: kept, forms confirmed, layout-safe, no form shared with another lemma"""
    result: List[dict] = []
    seen: Dict[str, Set[str]] = {key: set() for key in ('base', 'm', 'f', 'n', 'accM')}
    for row in rows:
        if not (is_flagged(row, 'keep') and is_flagged(row, 'forms_ok')):
            continue
        if kids and not is_flagged(row, 'kid'):
            continue
        entry = {
            'base': row['lemma'],
            'm': row['nom_m'],
            'f': row['nom_f'],
            'n': row['nom_n'],
            'accM': row['acc_m'],
        }
        if not all(LOWER_WORD.match(form) for form in entry.values()):
            logger.warning(f"Skipping adjective with unsafe form: {entry}")
            continue
        if is_blocked(row, entry.values(), blocklist):
            continue
        # A shared surface form would make some outputs more likely than others
        if any(entry[key] in seen[key] for key in seen):
            continue
        for key in seen:
            seen[key].add(entry[key])
        result.append(entry)
    return sorted(result, key=lambda a: a['base'])


def build_verbs(rows: List[Dict[str, str]], blocklist: Set[str], kids: bool) -> List[dict]:
    """Select verbs that take an accusative object"""
    result, seen = [], set()
    for row in rows:
        if not (is_flagged(row, 'keep') and is_flagged(row, 'takes_acc_obj')):
            continue
        if kids and not is_flagged(row, 'kid'):
            continue
        base, s3 = row['lemma'], row['pres_3sg']
        if not (LOWER_WORD.match(base) and LOWER_WORD.match(s3)):
            logger.warning(f"Skipping verb with unsafe form: {base}/{s3}")
            continue
        if is_blocked(row, [base, s3], blocklist) or s3 in seen:
            continue
        seen.add(s3)
        result.append({'base': base, 's3': s3})
    return sorted(result, key=lambda v: v['base'])


def build_adverbs(rows: List[Dict[str, str]], adjectives: List[dict]) -> List[str]:
    """Adverbs are base forms of selected adjectives that read naturally after a verb"""
    selected = {adj['base'] for adj in adjectives}
    adverbs = {
        row['lemma'] for row in rows
        if row['lemma'] in selected and is_flagged(row, 'adverb_ok')
    }
    return sorted(adverbs)


def build_wordlist(name: str, kids: bool, blocklist: Set[str]) -> dict:
    """Build one wordlist from the curated TSV files"""
    noun_rows = read_tsv(CURATED_DIR / 'nouns.tsv')
    adj_rows = read_tsv(CURATED_DIR / 'adjectives.tsv')
    verb_rows = read_tsv(CURATED_DIR / 'verbs.tsv')

    adjectives = build_adjectives(adj_rows, blocklist, kids)
    return {
        'version': 1,
        'name': name,
        'license': LICENSE,
        'attribution': ATTRIBUTION,
        'nouns': build_nouns(noun_rows, blocklist, kids),
        'adjectives': adjectives,
        'verbs': build_verbs(verb_rows, blocklist, kids),
        'adverbs': build_adverbs(adj_rows, adjectives),
    }


def log_strength(wordlist: dict) -> None:
    """Log list sizes and the resulting entropy of the default sentence format"""
    sizes = {key: len(wordlist[key]) for key in ('nouns', 'adjectives', 'verbs', 'adverbs')}
    bits = {key: math.log2(size) if size else 0.0 for key, size in sizes.items()}
    short = 2 * bits['adjectives'] + 2 * bits['nouns'] + bits['verbs'] + math.log2(100)
    logger.info(
        f"{wordlist['name']}: {sizes} -> "
        f"{short + bits['adverbs']:.1f} bits (default), {short:.1f} bits (without adverb)"
    )


def main():
    if len(sys.argv) != 1:
        print("Usage: python build_wordlists.py")
        sys.exit(1)

    blocklist = load_blocklist(BLOCKLIST_PATH)
    logger.info(f"Loaded {len(blocklist)} blocklisted words")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, kids in (('main', False), ('kids', True)):
        wordlist = build_wordlist(name, kids, blocklist)
        log_strength(wordlist)
        output_path = OUTPUT_DIR / f'wordlist_{name}.json'
        with output_path.open('w', encoding='utf-8') as f:
            json.dump(wordlist, f, ensure_ascii=False, separators=(',', ':'))
            f.write('\n')
        logger.info(f"Written {output_path}")


if __name__ == "__main__":
    main()
