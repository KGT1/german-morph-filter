#!/usr/bin/env python3
"""Build ranked CANDIDATE word lists (nouns, adjectives, verbs) for a German
mini-sentence passphrase generator.

    subjAdj(strong nom) + SubjNoun(nom) . verb(3sg pres) . adverb(adj base)
    . objAdj(strong acc) + ObjNoun(acc) . digits !

Mechanical stage only: morphology (kaikki.org / English Wiktionary), modern
frequency (wordfreq), usage tags, hard filters, ~400-row review chunks.

Reproduce (work directory defaults to tmp/candidates/, which is git-ignored):
    python3 -m venv venv && venv/bin/pip install wordfreq==3.1.1
    # put the inputs in tmp/candidates/src/ (see data/wordlists/CANDIDATES.md for URLs + pinned versions)
    venv/bin/python src/build_candidates.py [--floor-noun 2.5 --floor-adj 1.8 --floor-verb 2.0]

The review decisions were then added by hand/LLM review following
data/wordlists/REVIEW_GUIDE.md and merged into data/wordlists/curated/*.tsv,
which are the source of truth for src/build_wordlists.py.
"""
import argparse
import collections
import csv
import gzip
import json
import math
import os
import random
import re
import sys

from wordfreq import word_frequency

HERE = os.environ.get(
    "CANDIDATES_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tmp", "candidates"),
)
SRC = os.path.join(HERE, "src")
KAIKKI = os.path.join(SRC, "kaikki-German.jsonl.gz")
OLDDICT = os.path.join(SRC, "DE_morph_dict.txt")
LARS = os.path.join(SRC, "lars-wortliste.csv")
CHUNKS = os.path.join(HERE, "chunks")

CAPS = {"noun": 8000, "adj": 4000, "verb": 3000}
CHUNK_ROWS = 400

# ---------------------------------------------------------------- tag sets
RESTRICT_CORE = {"archaic", "obsolete", "dated", "rare", "uncommon",
                 "dialectal", "regional"}
RESTRICT_REGION = {
    "Austria", "Austrian", "Switzerland", "Swiss", "Liechtenstein", "Bavaria",
    "Southern-Germany", "southern-Germany", "Northern-Germany", "Rhineland",
    "Westphalia", "Berlin", "Namibia", "Upper-German", "Luxembourg",
    "Ruhrgebiet", "Münsterland", "Palatine", "Bohemia", "Basel", "Belgium",
    "South-Africa", "Texas", "US", "Australia", "UK", "South-Tyrol",
    "Northern", "Southern", "Eastern", "Western", "East", "West", "Central",
    "Northeastern", "Northwestern", "Southwestern", "South", "North",
}
RESTRICT = RESTRICT_CORE | RESTRICT_REGION
SENSITIVE = ["vulgar", "derogatory", "offensive", "slur", "pejorative",
             "ethnic", "Nazism"]
COLLOQ = {"colloquial", "informal", "slang"}
# form-level tags that make an inflected form non-preferred
FORM_BAD = RESTRICT | {"colloquial", "informal", "nonstandard", "proscribed",
                       "poetic", "literary", "obsolete", "error-unknown-tag"}

# explicitly indeclinable adjectives (Wiktionary sometimes generates bogus
# declension tables for these, e.g. "superer"); also caught by heuristics.
INDECL_ADJ = {"super", "prima", "klasse", "spitze", "lila", "rosa", "orange",
              "beige", "extra", "okay", "egal", "schuld", "pleite", "quitt",
              "top", "gratis", "live", "online", "offline", "sexy", "mega",
              "ultra", "bio", "retro", "mini", "maxi", "creme", "oliv", "cyan",
              "khaki", "magenta", "bordeaux", "uni", "allright", "tabu"}
# NB: fesch/vegan/pink/fit/fair decline regularly in modern usage -> kept.

SAFE_RE = re.compile(r"^[A-Za-z]+$")
UNSAFE_CHARS = set("yzYZäöüÄÖÜß")


def layout_safe(form):
    """True if form types identically on German QWERTZ and US QWERTY."""
    return bool(form) and SAFE_RE.match(form) is not None and not (set(form) & UNSAFE_CHARS)


def _z(forms):
    f = sum(word_frequency(w, "de") for w in set(x.lower() for x in forms if x))
    return round(math.log10(f * 1e9), 2) if f > 0 else 0.0


def prefer_safe(lst, flags, label):
    """If the preferred variant is not layout-safe but another unmarked
    variant is (e.g. backen: bäckt|backt), put the safe one first + flag."""
    if lst and not layout_safe(lst[0]):
        safe = [w for w in lst if layout_safe(w)]
        if safe:
            flags.append(f"{label}_safe_variant_chosen")
            return safe + [w for w in lst if w not in safe]
    return lst


def zipf_for(cat, r):
    """Homograph-robust frequency (wordfreq is case-insensitive):
    noun: min(Zipf(nom_sg), Zipf(acc_sg))
    adj : min(Zipf(lemma), Zipf(nom_m + nom_n summed)) -- the -e/-en forms
          are skipped because they collide with verb forms (lasse/lassen,
          garen); this also demotes participles that Wiktionary lists as
          adjectives but that are hardly used attributively (passiert).
    verb: min(Zipf(lemma), Zipf(pres_3sg))
    Using min() suppresses inflation by an unrelated homograph of ONE form
    (e.g. verb 'fasen' via adverb 'fast', 'einen' via the article)."""
    if cat == "noun":
        return min(_z([r.get("nom_sg")]), _z([r.get("acc_sg")]))
    if cat == "adj":
        return min(_z([r.get("lemma")]), _z([r.get("nom_m"), r.get("nom_n")]))
    return min(_z([r.get("lemma")]), _z([r.get("pres_3sg")]))


# ------------------------------------------------------------ head parsing
def split_top(s, seps):
    """Split on any char in seps at bracket depth 0 ([] and <>)."""
    out, cur, depth = [], [], 0
    for ch in s:
        if ch in "[<(":
            depth += 1
        elif ch in "]>)":
            depth -= 1
        if depth == 0 and ch in seps:
            out.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    out.append("".join(cur))
    return out


GENDER_RESTRICT_RE = re.compile(
    r"rare|archaic|dated|obsolete|dialect|regional|austria|switzerland|swiss|"
    r"southern|northern|eastern|western|bavaria|uncommon|originally|until|"
    r"formerly|technical|alternativ|nonstandard|proscribed|colloquial|informal|"
    r"some|occasional|less common|also|old|liechtenstein|south tyrol", re.I)


def noun_genders(entry):
    """Return (list of (gender, qualifier)), flags:set ; gender in m/f/n/p."""
    out, flags = [], set()
    for h in entry.get("head_templates", []):
        if h["name"] != "de-noun":
            continue
        spec = h["args"].get("1", "")
        if spec.startswith("(("):
            groups = re.findall(r"<([^<>]*)>", spec)
            specs = groups or [spec.strip("()")]
        else:
            specs = [spec]
        for sp in specs:
            if "<" in sp:              # multi-word head like "Herz<m,..> aus Stein"
                flags.add("multiword")
                continue
            first = split_top(split_top(sp, ",")[0], ".")[0]
            if first.startswith("+") or sp == "+" or first == "":
                flags.add("adjectival" if "+" in first else "nogender")
                continue
            for tok in split_top(first, ":"):
                m = re.match(r"^([a-z]+)(?:\[(.*)\])?$", tok)
                if not m:
                    flags.add("unparsed_gender")
                    continue
                g, q = m.group(1), m.group(2) or ""
                if g in ("m", "f", "n"):
                    out.append((g, q))
                elif "p" in g:
                    out.append(("p", q))
                else:
                    flags.add("unparsed_gender")
    # adjectival nouns: gender from expansion "Angestellter m (adjectival ..."
    if "adjectival" in flags:
        for h in entry.get("head_templates", []):
            m = re.match(r"^\S+ ([mfn])\b", h.get("expansion", ""))
            if m:
                out.append((m.group(1), ""))
    return out, flags


def head_text(entry):
    """Head-line text (expansions + template args) used to detect qualifiers
    that wiktextract propagates from the head line onto every sense."""
    parts = []
    for h in entry.get("head_templates", []):
        if h["name"] in ("tlb", "term-label"):
            continue
        parts.append(h.get("expansion", ""))
        parts.extend(str(v) for v in h.get("args", {}).values())
    for t in entry.get("inflection_templates", []):
        parts.extend(str(v) for v in t.get("args", {}).values())
    return " ".join(parts).lower()


INFL_TAGS = {"nominative", "accusative", "dative", "genitive", "plural",
             "comparative", "superlative", "first-person", "second-person",
             "third-person", "participle", "imperative", "subjunctive",
             "subjunctive-i", "subjunctive-ii", "preterite", "past", "present",
             "infinitive", "zu-infinitive", "inflection-of"}
ALT_BAD = {"initialism", "acronym", "misspelling", "nonstandard", "indeclinable",
           "numeral", "proscribed"}


def lemma_senses(entry):
    """Senses that make this entry a usable lemma: no inflected-form senses;
    alternative-form senses are kept (modern spellings such as Delfin are
    often listed as 'alternative spelling of Delphin'), except abbreviations
    (clippings like Abo/Deo are kept), misspellings and nonstandard forms.
    Restricted alternatives (obsolete, archaic, Swiss ss-spelling, ...) are
    removed later by usage_info()."""
    if any(h["name"] == "head" and " form" in str(h["args"].get("2", ""))
           for h in entry.get("head_templates", [])):
        return []   # "noun form" / "adjective form" / "verb form" entries
    out = []
    for s in entry.get("senses", []):
        tags = set(s.get("tags", []))
        if "form-of" in tags or s.get("form_of"):
            # wiktextract also uses form-of for derivations ("agent noun of
            # lehren" -> Lehrer, "female equivalent of", "verbal noun of");
            # only inflectional form-of senses are skipped.
            if tags & INFL_TAGS:
                continue
        if "alt-of" in tags or s.get("alt_of"):
            if tags & ALT_BAD:
                continue
            if "abbreviation" in tags and "clipping" not in tags:
                continue
        out.append(s)
    return out


def alt_flag(entries):
    """'alt_of:X' if every lemma sense of the first entry is an alternative form."""
    for e in entries[:1]:
        ss = lemma_senses(e)
        if ss and all("alt-of" in s.get("tags", []) or s.get("alt_of") for s in ss):
            tgt = {a.get("word") for s in ss for a in s.get("alt_of", []) if a.get("word")}
            return ["alt_of:" + "|".join(sorted(tgt))] if tgt else ["alt_of"]
    return []


def usage_info(entry, senses):
    """-> (all_restricted:bool, flags:list)"""
    ht = head_text(entry)
    n = len(senses)
    restricted = 0
    sens_count = collections.Counter()
    colloq = 0
    for s in senses:
        tags = set(s.get("tags", []))
        eff = {t for t in tags & RESTRICT
               if t.lower().replace("-", " ") not in ht}
        if eff:
            restricted += 1
        if tags & COLLOQ:
            colloq += 1
        for t in SENSITIVE:
            if t in tags:
                sens_count[t] += 1
    flags = [f"{t}:{c}/{n}" for t, c in sens_count.items()]
    if restricted and restricted < n:
        flags.append(f"partly_restricted:{restricted}/{n}")
    if n and colloq == n:
        flags.append("colloquial")
    return (n > 0 and restricted == n), flags


def pick_form(forms, need, forbid=(), source=None):
    """Return ordered distinct candidate forms with tags ⊇ need, no forbid tags.
    Preferred (no FORM_BAD tag) first."""
    good, bad = [], []
    for f in forms:
        tags = set(f.get("tags", []))
        if not need <= tags or tags & set(forbid):
            continue
        if source is not None and f.get("source") != source:
            continue
        w = f["form"]
        (bad if tags & FORM_BAD else good).append(w)
    seen, res = set(), []
    for w in good:
        if w not in seen:
            seen.add(w)
            res.append(w)
    return res, [w for w in dict.fromkeys(bad) if w not in seen]


# --------------------------------------------------------------- kaikki
def load_kaikki():
    ents = {"noun": collections.defaultdict(list),
            "adj": collections.defaultdict(list),
            "verb": collections.defaultdict(list)}
    lc_pos = collections.defaultdict(set)   # lowercase surface -> POS set (all entries)
    with gzip.open(KAIKKI, "rt", encoding="utf-8") as fh:
        for line in fh:
            d = json.loads(line)
            pos = d.get("pos")
            lc_pos[d["word"].lower()].add(pos)
            if pos not in ents:
                continue
            senses = lemma_senses(d)
            if not senses:
                continue  # inflected-form / alternative-spelling entries
            ents[pos][d["word"]].append(d)
    return ents, lc_pos


def noun_record(word, entries, st):
    """Merge homograph entries of the same lemma. Returns dict or (None, reason)."""
    usable = []
    nominf = 0
    for e in entries:
        senses = lemma_senses(e)
        if all("proper-noun" in s.get("tags", []) for s in senses):
            continue
        # pure nominalised infinitive ("das Zeigen" = verbal noun of zeigen):
        # every sense is a derivational form-of pointing at the same verb.
        # Its wordfreq Zipf is just the verb's (case-insensitive) -> drop.
        if senses and all((s.get("form_of") or []) and
                          all(f.get("word", "").lower() == word.lower() for f in s["form_of"])
                          for s in senses):
            nominf += 1
            continue
        allres, uflags = usage_info(e, senses)
        if allres:
            continue
        usable.append((e, uflags))
    if not usable:
        return None, ("nominalised_infinitive" if nominf else "usage_restricted")
    flags = []
    genders = []
    for e, uflags in usable:
        gs, gflags = noun_genders(e)
        if "multiword" in gflags and not gs:
            continue
        genders.append((e, uflags, gs, gflags))
    if not genders:
        return None, "no_gender"
    per_entry = []
    for e, uflags, gs, gflags in genders:
        if any(g == "p" and not q for g, q in gs) or (gs and all(g == "p" for g, q in gs)):
            per_entry.append((e, uflags, "p", gflags, []))
            continue
        unq = sorted({g for g, q in gs if g != "p" and not (q and GENDER_RESTRICT_RE.search(q))})
        allg = sorted({g for g, q in gs if g != "p"})
        if len(unq) == 1:
            g = unq[0]
        elif len(unq) == 0 and len(allg) == 1:
            g = allg[0]
        elif not allg:
            g = None
        else:
            g = "multi"
        dropped = [f"{g2}[{q}]" if q else g2 for g2, q in gs if g2 != g and g2 != "p"]
        per_entry.append((e, uflags, g, gflags, dropped))
    valid = [p for p in per_entry if p[2] in ("m", "f", "n")]
    if not valid:
        kinds = {p[2] for p in per_entry}
        if "p" in kinds:
            return None, "plural_only"
        if "multi" in kinds:
            return None, "multi_gender"
        return None, "no_gender"
    if any(p[2] == "multi" for p in per_entry):
        # one homograph entry is multi-gender, the other is fine -> keep fine one
        flags.append("homograph_multigender_dropped")
    gset = sorted({p[2] for p in valid})
    e, uflags, g, gflags, dropped = valid[0]
    if len(gset) > 1:
        flags.append("homograph_gender:" + "/".join(p[2] for p in valid))
    if dropped:
        flags.append("alt_gender_ignored:" + ",".join(dropped))
    flags.extend(uflags)
    adjectival = "adjectival" in gflags
    forms = e.get("forms", [])
    src = "kaikki"
    if adjectival:
        flags.append("adjectival_noun")
        nom, _ = pick_form(forms, {"nominative", "singular", "strong"})
        acc, _ = pick_form(forms, {"accusative", "singular", "strong"})
    else:
        nom, _ = pick_form(forms, {"nominative", "singular"},
                           forbid=("definite", "indefinite", "plural"), source="declension")
        acc, accbad = pick_form(forms, {"accusative", "singular"},
                                forbid=("definite", "indefinite", "plural"), source="declension")
        if not acc and accbad:
            acc = accbad[:1]
            flags.append("acc_only_marked_form")
    nom_sg = nom[0] if nom else word
    if nom and nom[0] != word and not adjectival:
        flags.append(f"nom_differs:{nom[0]}")
    acc = prefer_safe(acc, flags, "acc")
    if len(acc) > 1:
        flags.append("acc_variants:" + "|".join(acc))
    acc_sg = acc[0] if acc else None
    if acc_sg is None:
        # rule-based fallback from head template
        weak = any(".weak" in h["args"].get("1", "") or "(weak" in h.get("expansion", "")
                   for h in e.get("head_templates", []) if h["name"] == "de-noun")
        if g != "m" or not weak:
            acc_sg = nom_sg
            src = "kaikki+rule"
        else:
            gen, _ = pick_form(forms, {"genitive"}, forbid=("plural",))
            if gen:
                gn = gen[0]
                acc_sg = gn[:-1] if gn.endswith("ns") else gn
                src = "kaikki+rule"
            else:
                src = "needs_olddict"
        flags.append("acc_rule")
    flags.extend(alt_flag([e]))
    rec = dict(lemma=word, gender=g, nom_sg=nom_sg, acc_sg=acc_sg, flags=flags,
               source=src)
    if len(usable) > 1 and len(gset) == 1:
        rec["flags"].append(f"homographs:{len(usable)}")
    return rec, None


def adj_record(word, entries):
    usable = []
    for e in entries:
        senses = lemma_senses(e)
        allres, uflags = usage_info(e, senses)
        if allres:
            continue
        usable.append((e, uflags, senses))
    if not usable:
        return None, "usage_restricted"
    e, uflags, senses = usable[0]
    flags = list(uflags)
    heads = [h for h in e.get("head_templates", []) if h["name"] in ("de-adj", "de-adjective")]
    if not heads:
        return None, "no_adj_head"
    args = " ".join(str(h["args"].get("1", "")) for h in heads)
    if (word in INDECL_ADJ or "indecl" in args or "predonly" in args
            or any("indeclinable" in s.get("tags", []) for s in senses)):
        return None, "indeclinable"
    if re.search(r"[^aeiouäöü][aiou]$", word):
        # final single a/i/o/u (lila, rosa, prima, extra, mini, tabu) ->
        # indeclinable in standard German; diphthongs (blau, neu, frei) are fine
        return None, "indeclinable"
    if any("predicative" in s.get("tags", []) and "attributive" not in s.get("tags", [])
           for s in senses) and all("predicative" in s.get("tags", []) for s in senses):
        return None, "predicative_only"
    forms = e.get("forms", [])
    no_cmp = ("comparative", "superlative")
    req = {
        "nom_m": {"masculine", "nominative", "singular", "strong", "without-article"},
        "nom_f": {"feminine", "nominative", "singular", "strong", "without-article"},
        "nom_n": {"neuter", "nominative", "singular", "strong", "without-article"},
        "acc_m": {"masculine", "accusative", "singular", "strong", "without-article"},
    }
    flags.extend(alt_flag([e]))
    rec = dict(lemma=word, flags=flags, source="kaikki")
    for k, need in req.items():
        good, bad = pick_form(forms, need, forbid=no_cmp)
        if not good and bad:
            good = bad[:1]
            flags.append(f"{k}_marked_form")
        good = prefer_safe(good, flags, k)
        if len(good) > 1:
            flags.append(f"{k}_variants:" + "|".join(good))
        rec[k] = good[0] if good else None
    if not all(rec[k] for k in req):
        rec["source"] = "needs_olddict"
    tags_all = collections.Counter(t for s in senses for t in s.get("tags", []))
    if tags_all.get("no-predicative-form"):
        flags.append("no_predicative_form")
    if tags_all.get("relational") and tags_all["relational"] == len(senses):
        flags.append("relational")
    if len(usable) > 1:
        flags.append(f"homographs:{len(usable)}")
    return rec, None


def is_separable(e):
    """Main-clause 3sg is split ("sieht aus"); the joined form ("aussieht")
    is subordinate-clause only -> unusable in the 'Noun.verb.' slot."""
    allf = [f["form"] for f in e.get("forms", [])
            if {"present", "singular", "third-person"} <= set(f.get("tags", []))]
    heads = " ".join(str(h["args"].get("1", "")) for h in e.get("head_templates", [])
                     if h["name"] == "de-verb")
    return any(" " in w for w in allf) or re.match(r"^[a-zäöü]+\.", heads) is not None


def verb_record(word, entries):
    usable = []
    for e in entries:
        senses = lemma_senses(e)
        allres, uflags = usage_info(e, senses)
        if allres:
            continue
        usable.append((e, uflags, senses))
    if not usable:
        return None, "usage_restricted"
    usable = [u for u in usable
              if any(h["name"] == "de-verb" for h in u[0].get("head_templates", []))]
    if not usable:
        return None, "no_verb_head"
    insep = [u for u in usable if not is_separable(u[0])]
    if not insep:
        return None, "separable"
    flags = []
    if len(insep) < len(usable):
        flags.append("separable_homograph_skipped")
    e, uflags, senses = insep[0]
    flags.extend(uflags)
    forms = e.get("forms", [])
    good, bad = pick_form(forms, {"present", "singular", "third-person"},
                          forbid=("subjunctive", "subjunctive-i", "subjunctive-ii",
                                  "multiword-construction", "preterite", "past"))
    if not good and bad:
        good = bad[:1]
        flags.append("3sg_marked_form")
    good = prefer_safe(good, flags, "3sg")
    if len(good) > 1:
        flags.append("3sg_variants:" + "|".join(good))
    tags_all = collections.Counter(t for s in senses for t in s.get("tags", []))
    if tags_all.get("impersonal") == len(senses):
        flags.append("impersonal")
    if tags_all.get("reflexive") == len(senses):
        flags.append("reflexive_only")
    if len(insep) > 1:
        flags.append(f"homographs:{len(insep)}")
    flags.extend(alt_flag([e]))
    rec = dict(lemma=word, pres_3sg=good[0] if good else None, flags=flags,
               source="kaikki" if good else "needs_olddict")
    return rec, None


# ------------------------------------------------------------ old dict
ANAL_RE = re.compile(r"^(\S+) (NN|ADJ|V),(.*)$")


def olddict_lookup(need):
    """need: dict cat -> set(lemma). Returns dict (cat, lemma) -> list[(form, attrs)]"""
    res = collections.defaultdict(list)
    if not any(need.values()) or not os.path.exists(OLDDICT):
        return res
    cur = None
    with open(OLDDICT, encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            m = ANAL_RE.match(line)
            if not m:
                cur = line
                continue
            lem, cat, attrs = m.groups()
            if lem in need.get(cat, ()):
                res[(cat, lem)].append((cur, set(attrs.split(","))))
    return res


def olddict_fill(recs_by_cat):
    need = {"NN": set(), "ADJ": set(), "V": set()}
    for cat, recs in recs_by_cat.items():
        for r in recs:
            if r["source"] == "needs_olddict":
                need[{"noun": "NN", "adj": "ADJ", "verb": "V"}[cat]].add(r["lemma"])
    print("old-dict lookups:", {k: len(v) for k, v in need.items()}, file=sys.stderr)
    found = olddict_lookup(need)
    for cat, recs in recs_by_cat.items():
        for r in recs:
            if r["source"] != "needs_olddict":
                continue
            if cat == "noun":
                gtag = {"m": "masc", "f": "fem", "n": "neut"}[r["gender"]]
                cand = [f for f, a in found.get(("NN", r["lemma"]), [])
                        if {"acc", "sing", gtag} <= a]
                if cand:
                    r["acc_sg"] = cand[0]
                    r["source"] = "kaikki+olddict"
            elif cat == "adj":
                # old dict omits "strong" where strong == mixed (e.g. fem nom sg)
                keys = {"nom_m": {"masc", "nom", "sing", "pos"},
                        "nom_f": {"fem", "nom", "sing", "pos"},
                        "nom_n": {"neut", "nom", "sing", "pos"},
                        "acc_m": {"masc", "acc", "sing", "pos"}}
                ok = True
                for k, need_t in keys.items():
                    if r.get(k):
                        continue
                    cand = [f for f, a in found.get(("ADJ", r["lemma"]), [])
                            if need_t <= a and "weak" not in a and "mixed" not in a]
                    strong = [f for f, a in found.get(("ADJ", r["lemma"]), [])
                              if need_t <= a and "strong" in a]
                    cand = strong or cand
                    if cand:
                        r[k] = cand[0]
                    else:
                        ok = False
                if ok:
                    r["source"] = "kaikki+olddict"
            elif cat == "verb":
                cand = [f for f, a in found.get(("V", r["lemma"]), [])
                        if {"3per", "sing", "pres", "ind"} <= a]
                if cand:
                    r["pres_3sg"] = cand[0]
                    r["source"] = "kaikki+olddict"


# ------------------------------------------------------------ kid list
def load_kid():
    s = set()
    if os.path.exists(LARS):
        with open(LARS, encoding="utf-8") as fh:
            for row in csv.DictReader(fh, delimiter=";"):
                s.add(row["Wort"].strip())
    return s


# ------------------------------------------------------------ main
COLS = {
    "noun": ["rank", "lemma", "gender", "nom_sg", "acc_sg", "zipf", "flags", "kid_basic", "source"],
    "adj": ["rank", "lemma", "nom_m", "nom_f", "nom_n", "acc_m", "zipf", "flags", "kid_basic", "source"],
    "verb": ["rank", "lemma", "pres_3sg", "zipf", "flags", "kid_basic", "source"],
}
FORMS = {"noun": ["nom_sg", "acc_sg"], "adj": ["lemma", "nom_m", "nom_f", "nom_n", "acc_m"],
         "verb": ["lemma", "pres_3sg"]}
FILES = {"noun": ("candidates_nouns.tsv", "nouns"), "adj": ("candidates_adjs.tsv", "adjs"),
         "verb": ("candidates_verbs.tsv", "verbs")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--floor-noun", type=float, default=2.5, help="min Zipf for nouns")
    ap.add_argument("--floor-adj", type=float, default=1.8, help="min Zipf for adjectives")
    ap.add_argument("--floor-verb", type=float, default=2.0, help="min Zipf for verbs")
    a = ap.parse_args()

    kid = load_kid()
    ents, lc_pos = load_kaikki()
    stats = collections.OrderedDict()
    recs_by_cat = {}
    multig = []
    for cat in ("noun", "adj", "verb"):
        st = collections.OrderedDict()
        st["kaikki lemma entries (unique words with >=1 non-inflectional sense)"] = len(ents[cat])
        reasons = collections.Counter()
        recs = []
        for word, es in ents[cat].items():
            if cat == "noun":
                r, why = noun_record(word, es, st)
            elif cat == "adj":
                r, why = adj_record(word, es)
            else:
                r, why = verb_record(word, es)
            if r is None:
                reasons[why] += 1
                if cat == "noun" and why == "multi_gender" and layout_safe(word) \
                        and re.match(r"^[A-Z][a-z]{2,9}$", word):
                    multig.append(word)
            else:
                recs.append(r)
        for k, v in sorted(reasons.items(), key=lambda x: -x[1]):
            st[f"  dropped: {k}"] = v
        st["after usage/morphology parse"] = len(recs)
        recs_by_cat[cat] = recs
        stats[cat] = st

    olddict_fill(recs_by_cat)

    final = {}
    layout_lost_freq = {}
    for cat in ("noun", "adj", "verb"):
        a.floor = {"noun": a.floor_noun, "adj": a.floor_adj, "verb": a.floor_verb}[cat]
        st = stats[cat]
        recs = recs_by_cat[cat]
        # missing forms
        fkeys = FORMS[cat]
        miss = [r for r in recs if not all(r.get(k) for k in fkeys)]
        recs = [r for r in recs if all(r.get(k) for k in fkeys)]
        st["  dropped: missing forms (after old-dict fallback)"] = len(miss)
        st["with complete forms"] = len(recs)
        # layout safety (every stored form incl. lemma)
        bad = [r for r in recs if not all(layout_safe(r[k]) for k in fkeys + ["lemma"])]
        recs = [r for r in recs if all(layout_safe(r[k]) for k in fkeys + ["lemma"])]
        st["  dropped: LAYOUT SAFETY (y/z/umlaut/ß/non-letter in any form)"] = len(bad)
        st["after layout safety"] = len(recs)
        # case shape
        if cat == "noun":
            shape = re.compile(r"^[A-Z][a-z]+$")
            ok = lambda r: shape.match(r["nom_sg"]) and shape.match(r["acc_sg"]) and shape.match(r["lemma"])
        else:
            shape = re.compile(r"^[a-z]+$")
            ok = lambda r: all(shape.match(r[k]) for k in fkeys)
        n0 = len(recs)
        recs = [r for r in recs if ok(r)]
        st["  dropped: case shape (nouns ^[A-Z][a-z]+$, others ^[a-z]+$)"] = n0 - len(recs)
        # length
        if cat == "noun":
            lk, lo, hi = "nom_sg", 3, 10
        elif cat == "adj":
            lk, lo, hi = "lemma", 3, 9
        else:
            lk, lo, hi = "pres_3sg", 3, 9
        n0 = len(recs)
        recs = [r for r in recs if lo <= len(r[lk]) <= hi]
        st[f"  dropped: length ({lk} {lo}-{hi})"] = n0 - len(recs)
        st["after shape+length"] = len(recs)
        # frequency
        shared_key = {"noun": "nom_sg", "adj": "lemma", "verb": "pres_3sg"}[cat]
        # POS that legitimately share the surface (participles, adverbial use)
        own = {"noun": {"noun"}, "adj": {"adj", "verb", "adv"}, "verb": {"verb"}}[cat]
        for r in recs:
            r["zipf"] = zipf_for(cat, r)
            other = sorted(lc_pos.get(r[shared_key].lower(), set()) - own)
            if other:
                r["flags"].append("freq_shared:" + ",".join(other))
            r["kid_basic"] = "1" if r["lemma"] in kid else "0"
        for r in bad:
            r["zipf"] = zipf_for(cat, r)
        # report: words lost ONLY to layout safety, i.e. single tokens that
        # would pass case shape, length and the frequency floor if y/z/ä/ö/ü/ß
        # were allowed.
        if cat == "noun":
            shp = re.compile(r"^[A-ZÄÖÜ][a-zäöüß]+$")
        else:
            shp = re.compile(r"^[a-zäöüß]+$")
        layout_lost_freq[cat] = sorted(
            [r for r in bad if r["zipf"] >= a.floor
             and all(shp.match(r[k] or "") for k in fkeys + ["lemma"])
             and lo <= len(r[lk]) <= hi],
            key=lambda r: -r["zipf"])
        st["  (info) lost ONLY to layout safety (would pass shape/length/floor)"] = len(layout_lost_freq[cat])
        recs.sort(key=lambda r: (-r["zipf"], r["lemma"]))
        # dedupe by lemma and by surface form (keep most frequent)
        seen_l, seen_s, out = set(), set(), []
        dup = 0
        for r in recs:
            surf = tuple(r[k] for k in fkeys if k != "lemma")
            key_l = r["lemma"].lower() if cat != "noun" else r["lemma"]
            if key_l in seen_l or any(s in seen_s for s in surf[:1]):
                dup += 1
                continue
            seen_l.add(key_l)
            seen_s.add(surf[0])
            out.append(r)
        recs = out
        st["  dropped: duplicate lemma/surface"] = dup
        st["after dedupe"] = len(recs)
        for thr in (1.5, 1.8, 2.0, 2.5, 2.8, 3.0, 3.5, 4.0):
            st[f"    survivors at zipf>={thr}"] = sum(1 for r in recs if r["zipf"] >= thr)
        recs = [r for r in recs if r["zipf"] >= a.floor]
        st[f"after frequency floor (zipf>={a.floor})"] = len(recs)
        recs = recs[:CAPS[cat]]
        st[f"FINAL (cap {CAPS[cat]})"] = len(recs)
        st["  of which kid_basic"] = sum(r["kid_basic"] == "1" for r in recs)
        st["  of which source!=kaikki"] = sum(r["source"] != "kaikki" for r in recs)
        st["  of which flagged sensitive"] = sum(
            any(f.split(":")[0] in SENSITIVE for f in r["flags"]) for r in recs)
        final[cat] = recs

    # write
    os.makedirs(CHUNKS, exist_ok=True)
    for fn in os.listdir(CHUNKS):
        if fn.endswith(".tsv"):
            os.remove(os.path.join(CHUNKS, fn))
    chunk_files = []
    for cat, recs in final.items():
        fname, prefix = FILES[cat]
        cols = COLS[cat]
        rows = []
        for i, r in enumerate(recs, 1):
            r = dict(r, rank=i, flags=";".join(r["flags"]))
            rows.append([str(r[c]) for c in cols])
        with open(os.path.join(HERE, fname), "w", encoding="utf-8") as fh:
            fh.write("\t".join(cols) + "\n")
            for row in rows:
                fh.write("\t".join(row) + "\n")
        n_chunks = max(1, math.ceil(len(rows) / CHUNK_ROWS))
        for c in range(n_chunks):
            cf = f"{prefix}_{c + 1:02d}.tsv"
            chunk_files.append(cf)
            with open(os.path.join(CHUNKS, cf), "w", encoding="utf-8") as fh:
                fh.write("\t".join(cols) + "\n")
                for row in rows[c * CHUNK_ROWS:(c + 1) * CHUNK_ROWS]:
                    fh.write("\t".join(row) + "\n")

    # side list for curators: layout-safe nouns rejected only as multi-gender
    with open(os.path.join(HERE, "rejected_multigender_nouns.tsv"), "w", encoding="utf-8") as fh:
        fh.write("lemma\tgenders\tzipf\n")
        rows = []
        for w in multig:
            gs = sorted({f"{g}[{q}]" if q else g for e in ents["noun"][w]
                         for g, q in noun_genders(e)[0]})
            rows.append((w, ",".join(gs), _z([w])))
        for w, gs, zz in sorted(rows, key=lambda x: -x[2]):
            if zz >= {"noun": a.floor_noun}["noun"]:
                fh.write(f"{w}\t{gs}\t{zz}\n")
    with open(os.path.join(HERE, "stats.json"), "w", encoding="utf-8") as fh:
        json.dump({"floors": {"noun": a.floor_noun, "adj": a.floor_adj, "verb": a.floor_verb}, "stats": stats,
                   "layout_lost_above_floor": {c: [(r["lemma"], r["zipf"]) for r in v]
                                               for c, v in layout_lost_freq.items()},
                   "chunks": chunk_files}, fh, ensure_ascii=False, indent=1)
    for cat, st in stats.items():
        print(f"== {cat}")
        for k, v in st.items():
            print(f"  {k}: {v}")
        print(f"  layout-lost single words above floor: {len(layout_lost_freq[cat])}; top:",
              ", ".join(f"{r['lemma']}({r['zipf']})" for r in layout_lost_freq[cat][:15]))
    print("chunks:", " ".join(chunk_files))


if __name__ == "__main__":
    main()
