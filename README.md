# German Morphological Dictionary Filter

A tool for filtering and processing German morphological dictionaries.

## Passphrase wordlists

`data/output/wordlist_main.json` and `data/output/wordlist_kids.json` are curated lists for the sentence passphrases of [ger-morph-pw-gen](https://github.com/KGT1/ger-morph-pw-gen). Every word types the same on German and US keyboards.

- Rebuild: `python src/build_wordlists.py`
- Edit decisions in `data/wordlists/curated/*.tsv`
- Details and license (data is CC BY-SA 4.0): [data/wordlists/README.md](data/wordlists/README.md)

The morphological dictionaries below are used by the legacy adjective+noun generator.

## Requirements
- Python 3.x
- German morphological dictionary from [german-morph-dictionaries](https://github.com/DuyguA/german-morph-dictionaries)

## Usage
# Example usage commands
- cd src
- python filter_whitelist.py ../data/input/DE_morph_dict.txt ../data/output/whitelist_dict.txt ../data/whitelists/ADJ_whitelist.txt ../data/whitelists/NN_whitelist.txt
- python filter_sensible.py ../data/input/DE_morph_dict.txt ../data/output/DE_morph_dict_filtered.txt

## Releases

Each release includes three dictionary files:
- DE_morph_dict.txt - Original dictionary
- whitelist_dict.txt - Dictionary filtered by whitelist
- DE_morph_dict_filtered.txt - Dictionary filtered by sensible rules

Check the [releases page](../../releases) to download the latest dictionary files.
