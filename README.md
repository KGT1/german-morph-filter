# German Morphological Dictionary Filter

A tool for filtering and processing German morphological dictionaries.

## Requirements
- Python 3.x
- German morphological dictionary from [german-morph-dictionaries](https://github.com/DuyguA/german-morph-dictionaries)

## Usage
# Example usage commands
cd src
python filter_whitelist.py ../data/input/DE_morph_dict.txt ../data/output/whitelist_dict.txt ../data/whitelists/ADJ_whitelist.txt ../data/whitelists/NN_whitelist.txt
python filter_sensible.py ../data/input/DE_morph_dict.txt ../data/output/DE_morph_dict_filtered.txt
