#!/usr/bin/env python3

import logging
from pathlib import Path
from typing import List, Set, TextIO
import sys

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def parse_analysis_line(analysis_line: str) -> tuple[str, str, Set[str]]:
    """Parse a single analysis line into lemma, category, and properties"""
    parts = analysis_line.split()
    if len(parts) < 2:  # This is a word line, not an analysis line
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
    has_case = any(case in properties for case in {'nom', 'dat', 'acc'})
    return has_gender and has_sing and has_case

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
    return (5 <= length <= 7) if category == 'NN' else (5 <= length <= 9)

def process_entry(word: str, analysis_lines: List[str], outfile: TextIO) -> None:
    """Process a word entry and its analysis lines"""
    valid_analyses = []
    
    for line in analysis_lines:
        lemma, category, properties = parse_analysis_line(line)
        if not lemma:  # Skip invalid lines
            continue
            
        if category not in {'NN', 'ADJ'}:
            continue

        meets_criteria = (
            (category == 'NN' and meets_noun_criteria(properties)) or
            (category == 'ADJ' and meets_adj_criteria(properties))
        )

        if meets_criteria and meets_length_criteria(lemma, category):
            valid_analyses.append(line)

    # If we found valid analyses, write the word and its analyses
    if valid_analyses:
        outfile.write(f"{word}\n")
        for analysis in valid_analyses:
            outfile.write(f"{analysis}\n")
        outfile.write("\n")

def filter_dictionary(input_path: Path, output_path: Path) -> None:
    """Filter the dictionary file according to specified criteria"""
    logger.info(f"Starting to process {input_path}")
    
    try:
        with input_path.open('r', encoding='utf-8') as infile, \
             output_path.open('w', encoding='utf-8') as outfile:
            
            current_word = None
            current_analyses = []
            
            for line in infile:
                line = line.strip()
                
                if not line:  # Empty line
                    if current_word and current_analyses:
                        process_entry(current_word, current_analyses, outfile)
                    current_word = None
                    current_analyses = []
                    continue
                
                if ' ' not in line:  # This is a word line
                    if current_word and current_analyses:
                        process_entry(current_word, current_analyses, outfile)
                    current_word = line
                    current_analyses = []
                else:  # This is an analysis line
                    current_analyses.append(line)
            
            # Process the last entry if exists
            if current_word and current_analyses:
                process_entry(current_word, current_analyses, outfile)
    
    except Exception as e:
        logger.error(f"Error processing files: {e}")
        raise

    logger.info(f"Filtering completed. Output written to {output_path}")

def main():
    if len(sys.argv) != 3:
        print("Usage: python filter_sensible.py input_file output_file")
        sys.exit(1)

    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])

    if not input_path.exists():
        logger.error(f"Input file {input_path} does not exist")
        sys.exit(1)

    try:
        filter_dictionary(input_path, output_path)
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
