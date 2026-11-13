# Review guide — German passphrase wordlists

You are curating words for a memorable German passphrase generator. Passwords are mini sentences:

    flinkerFuchs.malt.leise.roteTomate.42!
    = adjective+Noun (subject, nominative) . verb (3sg present) . adverb (adjective base form) . adjective+Noun (object, accusative) . digits !

Users must be able to **remember** the sentence, **picture** it, and **type** it. Every word you keep must be one an ordinary adult German speaker uses or instantly understands today. Keyboard-layout filtering (no y/z/umlauts/ß) is already done. Don't re-check it.

Judge each row on its own, using your own knowledge of German. The frequency (`zipf`) and `flags` columns are hints only. Most rows are fine; be decisive, not precious. Expect to keep roughly 50–80% of rows in high-frequency chunks and fewer in the long tail.

## Output

For every input chunk `chunks/<name>.tsv`, write `reviewed/<name>.tsv`:
- It has **all original columns unchanged, in order**, plus these extra columns at the end.
- It has exactly one output row per input row, in the same order.
- It has a header row.

Extra columns per category:

| category | extra columns |
|---|---|
| nouns | `keep` (1/0), `kid` (1/0), `animate` (1/0), `concrete` (1/0), `gender_ok` (1/0), `note` |
| adjs  | `keep` (1/0), `kid` (1/0), `adverb_ok` (1/0), `forms_ok` (1/0), `note` |
| verbs | `keep` (1/0), `kid` (1/0), `takes_acc_obj` (1/0), `note` |

`note`: empty when keep=1 and nothing is wrong. Otherwise use a short reason code: `function_word`, `name_or_brand`, `adjectival_noun`, `obscure`, `jargon`, `archaic`, `offensive`, `sensitive`, `negative`, `wrong_gender`, `wrong_form`, `ambiguous`, `bad_adverb`, `needs_dative`, `reflexive_only`, `auxiliary`, `ugly_in_sentence`, or a few words of free text.

## keep = 1 (main list) when ALL hold
- It is a real, current, standard-German common word that a typical adult knows. Moderately abstract words are OK (Idee, Plan).
- **It is not one of the following:**
  - a function word or pronoun misparsed as a noun (Ich, Als, Etwas)
  - a person's name, a brand, a company or a place
  - an adjective used as a noun (Gute, Kleiner)
  - an obscure word, technical jargon, a heavy loanword, or an abbreviation
  - an archaic or regional word
- **Not offensive or upsetting:**
  - no slurs, insults, sexual words, drugs, violence, weapons, death, disease or crime
  - no politics, religion, ethnicity or nationality words (belgischer, Taliban, Liturgie)
  - no words likely to make a password embarrassing to read aloud
  - Mildly negative everyday words are OK in the main list (müde, kalt, Regen).
- The data is right:
  - **Nouns:** the gender is correct for the main modern meaning (`gender_ok`). If wrong, set gender_ok=0 and keep=0, and note the right gender. Also check that `acc_sg` is the correct accusative singular (weak masculines: Hase→Hasen, Postbote→Postboten; most others are identical to nom).
  - **Adjectives:** nom_m/nom_f/nom_n/acc_m are the correct strong forms (-er/-e/-es/-en, with e.g. dunkel→dunkler, teuer→teurer) (`forms_ok`). The word must make sense *before a noun* ("roter Ball").
  - **Verbs:** pres_3sg is correct ("er malt", "sie liest").

## kid = 1 (kids list, ages ~7–10) when keep=1 AND
The word is concrete or very familiar to a primary-school child, and it is positive or neutral. Examples:
- Nouns: animals, food, toys, everyday objects, nature, family, school.
- Adjectives: colours, sizes, textures, simple feelings.
- Verbs: simple actions like malt, baut, sucht.

Set kid=0 for anything scary, sad, grown-up or abstract. `kid_basic=1` in the input (from a school vocabulary list) is a strong hint, but still apply the rules.

## Category-specific
- **nouns:**
  - `animate`=1 for people, animals and creatures (Fuchs, Lehrerin, Drache). They make good sentence subjects.
  - `concrete`=1 for things you can see or touch.
  - Both are informational; abstract nouns can still be kept.
- **adjs:** `adverb_ok`=1 if the base form works naturally as a manner adverb after a verb ("malt leise", "baut schnell", "liest gern" is fine; "malt hölzern", "baut dritte", "malt belgisch" are not).
- **verbs:**
  - `takes_acc_obj`=1 if "Der Fuchs <verb> den Ball / eine Tomate" (an accusative object) is natural for typical objects ("malt", "sucht", "baut", "isst").
  - Verbs that need a dative (hilft, folgt), are reflexive-only (sich freuen), are auxiliaries or modals (wird, hat, ist, kann), or take no object (schläft) get takes_acc_obj=0.
  - keep can still be 1 for an intransitive verb if it's a good word. Downstream only uses keep=1 AND takes_acc_obj=1.

## Process
- Read the whole chunk.
- Decide every row. Writing a small Python script that holds your decisions as a dict, then merges them with the input TSV, is a fine way to produce the output.
- Validate before finishing:
  - the row count matches the input
  - every original column is unchanged
  - all extra columns are filled with 0/1 where required
- Never modify files outside `reviewed/`.
