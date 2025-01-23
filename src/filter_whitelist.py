#!/usr/bin/env python3

import logging
from pathlib import Path
from typing import List, Set, TextIO
import sys

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def load_whitelist(filepath: Path) -> Set[str]:
    """Load whitelist from file into a set"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return {line.strip() for line in f if line.strip()}
    except FileNotFoundError:
        logger.error(f"Whitelist file {filepath} not found")
        return set()
    except Exception as e:
        logger.error(f"Error loading whitelist {filepath}: {e}")
        return set()

def parse_analysis_line(analysis_line: str) -> tuple[str, str, Set[str]]:
    """Parse a single analysis line into lemma, category, and properties"""
    parts = analysis_line.split()
    if len(parts) < 2:
        return None, None, set()
        
    lemma, attributes = parts[0], parts[1]
    attr_parts = attributes.split(',')
    category = attr_parts[0]
    properties = set(attr_parts[1:])
    
    return lemma, category, properties

def meets_noun_criteria(properties: Set[str]) -> bool:
    """Check if properties meet noun criteria"""
    has_gender = any(gender in properties for gender in {'masc', 'neut', 'fem'})
    has_sing = 'sing' in properties
    has_nom = 'nom' in properties
    return has_gender and has_sing and has_nom

def meets_adj_criteria(properties: Set[str]) -> bool:
    """Check if properties meet adjective criteria"""
    return (
        ('nom' in properties) and
        ('sing' in properties) and
        ('strong' in properties) and
        any(gender in properties for gender in {'masc', 'neut', 'fem'})
    )

def meets_length_criteria(lemma: str, category: str) -> bool:
    """Check if lemma meets length criteria based on category"""
    length = len(lemma)
    return (4 <= length <= 6) if category == 'NN' else (5 <= length <= 9)

def process_entry(word: str, 
                 analysis_lines: List[str], 
                 outfile: TextIO, 
                 adj_whitelist: Set[str], 
                 nn_whitelist: Set[str]) -> None:
    """Process a word entry and its analysis lines"""
    valid_analyses = []
    
    for line in analysis_lines:
        lemma, category, properties = parse_analysis_line(line)
        if not lemma:
            continue
            
        if category not in {'NN', 'ADJ'}:
            continue

        # Check if lemma is in corresponding whitelist
        if category == 'NN' and lemma not in nn_whitelist:
            continue
        if category == 'ADJ' and lemma not in adj_whitelist:
            continue

        meets_criteria = (
            (category == 'NN' and meets_noun_criteria(properties)) or
            (category == 'ADJ' and meets_adj_criteria(properties))
        )

        if meets_criteria and meets_length_criteria(lemma, category):
            valid_analyses.append(line)

    if valid_analyses:
        outfile.write(f"{word}\n")
        for analysis in valid_analyses:
            outfile.write(f"{analysis}\n")
        outfile.write("\n")

def filter_dictionary(input_path: Path, 
                     output_path: Path, 
                     adj_whitelist_path: Path, 
                     nn_whitelist_path: Path) -> None:
    """Filter the dictionary file according to specified criteria and whitelists"""
    logger.info("Loading whitelists...")
    adj_whitelist = load_whitelist(adj_whitelist_path)
    nn_whitelist = load_whitelist(nn_whitelist_path)
    
    logger.info(f"Loaded {len(adj_whitelist)} adjectives and {len(nn_whitelist)} nouns from whitelists")
    logger.info(f"Starting to process {input_path}")
    
    try:
        with input_path.open('r', encoding='utf-8') as infile, \
             output_path.open('w', encoding='utf-8') as outfile:
            
            current_word = None
            current_analyses = []
            
            for line in infile:
                line = line.strip()
                
                if not line:
                    if current_word and current_analyses:
                        process_entry(current_word, current_analyses, outfile, 
                                   adj_whitelist, nn_whitelist)
                    current_word = None
                    current_analyses = []
                    continue
                
                if ' ' not in line:
                    if current_word and current_analyses:
                        process_entry(current_word, current_analyses, outfile,
                                   adj_whitelist, nn_whitelist)
                    current_word = line
                    current_analyses = []
                else:
                    current_analyses.append(line)
            
            # Process the last entry if exists
            if current_word and current_analyses:
                process_entry(current_word, current_analyses, outfile,
                           adj_whitelist, nn_whitelist)
    
    except Exception as e:
        logger.error(f"Error processing files: {e}")
        raise

    logger.info(f"Filtering completed. Output written to {output_path}")

def main():
    if len(sys.argv) != 5:
        print("Usage: python filter_sensible.py input_file output_file adj_whitelist nn_whitelist")
        sys.exit(1)

    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])
    adj_whitelist_path = Path(sys.argv[3])
    nn_whitelist_path = Path(sys.argv[4])

    if not input_path.exists():
        logger.error(f"Input file {input_path} does not exist")
        sys.exit(1)

    try:
        filter_dictionary(input_path, output_path, adj_whitelist_path, nn_whitelist_path)
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
