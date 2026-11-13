# German passphrase CANDIDATE word lists (mechanical stage)

Pattern: `flinkerFuchs.malt.leise.roteTomate.42!`
= subjAdj (strong nom) + SubjNoun (nom) . verb (3sg pres) . adverb (adj base) . objAdj (strong acc) + ObjNoun (acc) . digits `!`

These are **candidates**. Only hard filters were applied; subjective curation happens later.
Rebuild: `venv/bin/python build.py` (about 1 min; defaults `--floor-noun 2.5 --floor-adj 1.8 --floor-verb 2.0`). Console output is in `build.log`, all stage counts are in `stats.json`.

## Outputs
| file | rows | columns |
|---|---|---|
| candidates_nouns.tsv | 8000 | rank, lemma, gender(m/f/n), nom_sg, acc_sg, zipf, flags, kid_basic, source |
| candidates_adjs.tsv | 1611 | rank, lemma, nom_m, nom_f, nom_n, acc_m, zipf, flags, kid_basic, source |
| candidates_verbs.tsv | 1520 | rank, lemma, pres_3sg, zipf, flags, kid_basic, source |
| chunks/ | | nouns_01..20, adjs_01..05, verbs_01..04 (400 rows each, last one shorter; same header) |
| rejected_multigender_nouns.tsv | 164 | layout-safe nouns that were dropped only because they have more than one gender (Monat, Liter, Ketchup, Teller …), for the curators |
| stats.json | | stage counts, layout-loss lists, chunk list |

## Sources (versions, licenses)
| source | version / date | license | use |
|---|---|---|---|
| kaikki.org German dictionary (`kaikki.org-dictionary-German.jsonl.gz`, wiktextract over **English** Wiktionary) | extracted 2026-10-30 from the enwiktionary dump of 2026-10-01 (wiktextract 19f9a30). sha256 e16ea346…b520 | CC BY-SA 4.0 (and GFDL), inherited from Wiktionary | lemmas, gender, declension/conjugation forms, sense usage tags |
| wordfreq (PyPI) | 3.1.1 (data snapshot frozen around 2021) | code Apache-2.0, **data CC BY-SA 4.0** | Zipf frequency for `de` (blend of subtitles/OpenSubtitles, Wikipedia, news, web and social media) |
| DuyguA/german-morph-dictionaries `morf_dict.zip` → DE_morph_dict.txt | commit 8b0a182 (2018-02-26). sha256 842e0b2f…af52 | LICENSE file says **CC BY-SA 4.0**, but the README says MIT. Treat it as CC BY-SA | fallback only: 27 adjective rows (`source=kaikki+olddict`) |
| KSKHugo/lars-wortliste `wortliste.csv` (LaRS word list for school years 2–4, 919 words) | commit 204be92 (2026-10-25). sha256 72b2e121…3d44 | CC BY-SA 4.0. Based on the "Aktualisierter Berliner Grundwortschatz" (LISUM 2024, CC BY-SA 4.0). Required attribution: "LaRS-Wortliste Klasse 2–4, Pascal Hugo, auf Grundlage u. a. des Aktualisierten Berliner Grundwortschatzes (LISUM 2024), CC BY-SA 4.0" | `kid_basic` = exact lemma match |

**Shipping a derived whitelist.** The repos are MIT. A plain list of common German words with their regular inflections is mostly factual. But this list is a *selection* computed from CC BY-SA databases (Wiktionary, wordfreq data, LaRS), so it may count as an adapted database. The safe option is to ship the final whitelist as a separate data file under CC BY-SA 4.0, with attribution to Wiktionary contributors (via kaikki.org/wiktextract), wordfreq (Robyn Speer), and LaRS/LISUM if `kid_basic` influenced the selection. The MIT code can stay MIT. Do not ship the zipf column unless you want wordfreq attribution in the product. Not legal advice.

## Pipeline and counts (defaults)
Lemma entries are kaikki entries that have a lemma head template (`de-noun`/`de-adj`/`de-verb`) and at least one non-inflectional sense. Derivational `form-of` senses are kept (wiktextract tags "agent noun of lehren" → *Lehrer* and "female equivalent of" as form-of). Alternative spellings are kept too (modern *Delfin* is "alt of Delphin"), except initialisms, misspellings, nonstandard forms and non-clipping abbreviations.

**Usage drop.** A lemma is dropped when **all** its senses carry one of archaic, obsolete, dated, rare, uncommon, dialectal or regional, or a regional label (Austria, Switzerland, Bavaria, Southern-Germany …). Tags that also appear in the head line are ignored, because wiktextract copies head qualifiers onto every sense (for example *Herz* "(very rare) Herzes" would otherwise make every sense "rare").

| stage | nouns | adjs | verbs |
|---|---|---|---|
| kaikki lemma entries (unique words) | 65180 | 16419 | 10524 |
| − usage restricted (all senses archaic/obsolete/dated/rare/dialectal/regional) | 4511 | 806 | 937 |
| − pure nominalised infinitive (*das Zeigen*; its frequency is just the verb's) | 3450 | – | – |
| − no gender / multi-gender / plural-only | 1205 / 474 / 204 | – | – |
| − indeclinable (indecl/predonly in Wiktionary, denylist, final single a/i/o/u) / predicative-only | – | 984 / 19 | – |
| − no lemma head template | – | 71 | 58 |
| − separable verb (3sg is split: *sieht aus*) | – | – | 4351 |
| − forms still missing after old-dict fallback | 0 | 575 | 0 |
| **− LAYOUT SAFETY** (y z ä ö ü ß or non-letter in ANY stored form, lemma included) | **18754** | **4966** | **1544** |
| − case shape (nouns `^[A-Z][a-z]+$`, adjs/verbs `^[a-z]+$`) | 111 | 20 | 0 |
| − length (noun nom_sg 3–10, adj lemma 3–9, verb 3sg 3–9) | 17076 | 5304 | 1057 |
| − duplicate lemma / surface form | 0 | 12 | 4 |
| = pool before frequency floor | 19395 | 3662 | 2573 |
| survivors at Zipf ≥ 1.5 / 1.8 / 2.0 / 2.5 / 2.8 / 3.0 / 3.5 / 4.0 | 14885 / 13627 / 12601 / 9545 / 7602 / 6391 / 3665 / 1752 | 1933 / 1611 / 1379 / 880 / 635 / 487 / 234 / 90 | 1856 / 1668 / 1520 / 1098 / 865 / 711 / 401 / 197 |
| floor used | 2.5 | 1.8 | 2.0 |
| **FINAL** (cap 8000 / 4000 / 3000) | **8000** (cap reached, lowest kept Zipf 2.74) | **1611** | **1520** |
| words lost ONLY to layout safety (would pass shape, length and floor) | 2859 (Zeit, Platz, Straße, Glück, Mädchen …) | 601 (groß, schön, kurz, schwarz …) | 652 (können, wissen, laufen, hören …) |

### Frequency (`zipf`)
wordfreq is case-insensitive, so one form can be inflated by a homograph. The Zipf value is therefore a min over forms:
- nouns: `min(Z(nom_sg), Z(acc_sg))`
- verbs: `min(Z(lemma), Z(pres_3sg))`. This kills *fasen*/fast and *einen*/article.
- adjectives: `min(Z(lemma), Z(nom_m + nom_n))`. The -e/-en forms collide with verb forms (*lasse/lassen*). This also demotes participles that Wiktionary lists as adjectives but that are rarely attributive.

The adjective and verb floors are lower because the min() metric is stricter than lemma Zipf. *flink* scores 2.43.

## Flags column (`;`-separated)
- **Sensitive:** `vulgar|derogatory|offensive|slur|pejorative|ethnic|Nazism:k/N` (k of N senses).
- **Usage:** `partly_restricted:k/N` (some senses archaic/regional/…), `colloquial` (all senses colloquial/informal/slang).
- **Frequency:**
  - `freq_shared:<pos>`: the surface form is also another POS or a name in Wiktionary, so the frequency is mixed. Examples: *Ich, Aber, Wenn, Macht* (verb), *Bernd* (name).
- **Noun morphology:**
  - `homograph_gender:m/f…`: separate Wiktionary entries with different genders. The first entry's gender is used (*See*, *Leiter*, *Band*, *Elf* = f "eleven" vs m "elf").
  - `alt_gender_ignored:…`: a qualified variant gender was ignored (*Meter* n[dated], *Joghurt* n[Austria]).
  - `homograph_multigender_dropped`: another entry of the same word was multi-gender and was skipped.
  - `adjectival_noun`: nom/acc are the strong forms (*Deutscher/Deutschen*). Its frequency is the adjective's.
  - `acc_variants:…`: the first variant was taken.
  - `acc_rule`: no declension table in kaikki, so acc = nom, or the genitive minus -s for weak masculines (`source=kaikki+rule`).
- **Adjective morphology:** `<form>_variants:…`, `relational`, `no_predicative_form`.
- **Verbs:** `3sg_variants:…`, `reflexive_only`, `impersonal`, `separable_homograph_skipped`.
- **Any POS:** `<x>_safe_variant_chosen`, `alt_of:<lemma>`, `homographs:n`.

## Known issues (for curators)
- **Nominalised function words** sit at the top of the noun list because of the case-insensitive frequency: *Ich, Des, Als, Aber, Wenn, Mehr, Hier, Bis, Unter, Etwas, Nichts* … They are flagged `freq_shared`.
- **Adjectival nouns:** 116 nouns (*Gute, Andere, Kleiner*). Their frequency is the adjective's.
- **Brand, place and person names** that Wiktionary lists as common nouns: *Siemens, Bernd, Hugo, Lidl, Nike, Peugeot, Taliban*. They often carry `acc_rule` (no declension table) and/or `freq_shared:name`.
- **Common nouns dropped as multi-gender:** *Monat, Liter, Ketchup, Gummi, Teller, Blog, Virus* (see rejected_multigender_nouns.tsv).
- **Unattested genders:** genders come from Wiktionary head templates and are not validated against a second source.
- **Adjective lemmas in -e** (*besondere, erste, dritte*) are poor adverbs. Only some carry `no_predicative_form`.
- **575 adjectives** (mostly participles) have no declension table in kaikki and are not in the old dict, so they were dropped.
