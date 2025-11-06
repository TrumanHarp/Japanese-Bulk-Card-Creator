# kana_romaji.py

# This file is an approximation of the Hepburn romanization system for Japanese kana.
# Most of the dictionaries were created with AI.

from __future__ import annotations

from typing import List


def _kata_to_hira(ch: str) -> str:
    """Convert a single katakana char to hiragana; leave others as-is."""
    code = ord(ch)
    if 0x30A1 <= code <= 0x30F6:
        return chr(code - 0x60)
    return ch


# Digraphs (きゃ, しゃ, etc.), Hepburn-style
_HIRA_DIGRAPHS = {
    # k
    "きゃ": "kya", "きゅ": "kyu", "きょ": "kyo",
    # g
    "ぎゃ": "gya", "ぎゅ": "gyu", "ぎょ": "gyo",
    # s / sh
    "しゃ": "sha", "しゅ": "shu", "しょ": "sho",
    "じゃ": "ja",  "じゅ": "ju",  "じょ": "jo",
    # ch / j
    "ちゃ": "cha", "ちゅ": "chu", "ちょ": "cho",
    # n
    "にゃ": "nya", "にゅ": "nyu", "にょ": "nyo",
    # h
    "ひゃ": "hya", "ひゅ": "hyu", "ひょ": "hyo",
    # b
    "びゃ": "bya", "びゅ": "byu", "びょ": "byo",
    # p
    "ぴゃ": "pya", "ぴゅ": "pyu", "ぴょ": "pyo",
    # m
    "みゃ": "mya", "みゅ": "myu", "みょ": "myo",
    # r
    "りゃ": "rya", "りゅ": "ryu", "りょ": "ryo",
}

# Single kana → romaji
_HIRA_MONO = {
    "あ": "a",   "い": "i",   "う": "u",   "え": "e",   "お": "o",
    "か": "ka",  "き": "ki",  "く": "ku",  "け": "ke",  "こ": "ko",
    "さ": "sa",  "し": "shi", "す": "su",  "せ": "se",  "そ": "so",
    "た": "ta",  "ち": "chi", "つ": "tsu", "て": "te",  "と": "to",
    "な": "na",  "に": "ni",  "ぬ": "nu",  "ね": "ne",  "の": "no",
    "は": "ha",  "ひ": "hi",  "ふ": "fu",  "へ": "he",  "ほ": "ho",
    "ま": "ma",  "み": "mi",  "む": "mu",  "め": "me",  "も": "mo",
    "や": "ya",              "ゆ": "yu",              "よ": "yo",
    "ら": "ra",  "り": "ri",  "る": "ru",  "れ": "re",  "ろ": "ro",
    "わ": "wa",                          "を": "o",
    "ん": "n",
    # dakuten
    "が": "ga",  "ぎ": "gi",  "ぐ": "gu",  "げ": "ge",  "ご": "go",
    "ざ": "za",  "じ": "ji",  "ず": "zu",  "ぜ": "ze",  "ぞ": "zo",
    "だ": "da",  "ぢ": "ji",  "づ": "zu",  "で": "de",  "ど": "do",
    "ば": "ba",  "び": "bi",  "ぶ": "bu",  "べ": "be",  "ぼ": "bo",
    "ぱ": "pa",  "ぴ": "pi",  "ぷ": "pu",  "ぺ": "pe",  "ぽ": "po",
    # small vowels
    "ぁ": "a", "ぃ": "i", "ぅ": "u", "ぇ": "e", "ぉ": "o",
    # small ya/yu/yo
    "ゃ": "ya", "ゅ": "yu", "ょ": "yo",
    # small tsu handled specially (sokuon)
    "っ": "",
    # chōon (ー) handled separately
    "ー": "",
}


def _next_romaji_chunk(hira: str, pos: int) -> str:
    """Peek romaji for the kana at `pos` (considering digraphs)."""
    if pos >= len(hira):
        return ""
    ch = hira[pos]
    if pos + 1 < len(hira):
        pair = ch + hira[pos + 1]
        if pair in _HIRA_DIGRAPHS:
            return _HIRA_DIGRAPHS[pair]
    return _HIRA_MONO.get(ch, "")


def _apply_macrons(basic: str) -> str:
    """
    Very rough long-vowel handling for Hepburn with macrons.

    True 'perfect' behavior needs lexical knowledge, but
    this covers the big patterns.
    """
    repl = (
        ("aa", "ā"),
        ("ii", "ī"),
        ("uu", "ū"),
        ("ee", "ē"),
        ("oo", "ō"),
        ("ou", "ō"),
    )
    s = basic
    for src, dst in repl:
        s = s.replace(src, dst)
    return s


def kana_to_romaji(
    text: str,
    *,
    use_macrons: bool = False,
    use_m_before_bmp: bool = True,
) -> str:
    """
    Convert kana (hiragana/katakana) to modified Hepburn romaji.

    - Digraphs (しゃ → sha, きょ → kyo, etc.)
    - Sokuon っ as consonant doubling (がっこう → gakkou)
    - 'ん':
        - n' before vowels / y (しんよう → shin'you)
        - m before b/m/p if use_m_before_bmp=True (しんぶん → shimbun)
        - n before b/m/p if use_m_before_bmp=False (しんぶん → shinbun)
        - n otherwise
    - Optional macrons (Tōkyō) if use_macrons=True.
    """
    if not text:
        return ""

    # Normalize to hiragana
    hira = "".join(_kata_to_hira(ch) for ch in text)

    result: List[str] = []
    i = 0
    length = len(hira)

    while i < length:
        ch = hira[i]

        # --- sokuon (small tsu: っ) ---
        if ch == "っ":
            if i + 1 < length:
                next_chunk = _next_romaji_chunk(hira, i + 1)
                if next_chunk:
                    c = next_chunk[0]
                    if c.isalpha():
                        result.append(c)
            i += 1
            continue

        # --- ん (moraic n) ---
        if ch == "ん":
            if i + 1 >= length:
                result.append("n")
                i += 1
                continue

            next_chunk = _next_romaji_chunk(hira, i + 1)
            if not next_chunk:
                result.append("n")
                i += 1
                continue

            first = next_chunk[0].lower()
            if first in "aeiouy":
                # before vowel or y → n'
                result.append("n'")
            elif first in "bmp":
                if use_m_before_bmp:
                    result.append("m")
                else:
                    result.append("n")
            else:
                result.append("n")

            i += 1
            continue

        # --- digraphs like きゃ, しゃ, etc. ---
        if i + 1 < length:
            pair = ch + hira[i + 1]
            if pair in _HIRA_DIGRAPHS:
                result.append(_HIRA_DIGRAPHS[pair])
                i += 2
                continue

        # --- chōon (ー): prolong last vowel ---
        if ch == "ー":
            if result:
                last = result[-1]
                for idx in range(len(last) - 1, -1, -1):
                    if last[idx] in "aeiou":
                        result.append(last[idx])
                        break
            i += 1
            continue

        # --- normal kana ---
        rom = _HIRA_MONO.get(ch)
        if rom is None:
            rom = ch  # pass through unknown
        result.append(rom)
        i += 1

    basic = "".join(result)
    if use_macrons:
        return _apply_macrons(basic)
    return basic
