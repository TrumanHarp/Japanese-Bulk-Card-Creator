#!/usr/bin/env python3
"""
JMdict_e → SQLite converter (command-line version)

Usage:
    python XML2SQL.py JMdict_e.xml jmdict.db
    python XML2SQL.py JMdict_e.gz jmdict.db
    python XML2SQL.py JMdict_e jmdict.db    # works even if gzipped without extension
"""

import sqlite3
import xml.etree.ElementTree as ET
import gzip
from pathlib import Path
import argparse


def open_xml(path: Path):
    """Open JMdict file (handles plain XML or gzipped automatically)."""
    raw = open(path, "rb")
    magic = raw.read(2)
    raw.seek(0)
    if magic == b"\x1f\x8b":  # gzip magic header
        return gzip.open(raw, "rb")
    return raw


def create_db(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS entries")
    cur.execute(
        """
        CREATE TABLE entries (
            ent_seq    INTEGER PRIMARY KEY,
            expression TEXT,
            reading    TEXT,
            gloss1     TEXT,
            gloss2     TEXT,
            gloss3     TEXT,
            pos        TEXT,
            common     INTEGER
        )
        """
    )
    cur.execute("CREATE INDEX idx_expression ON entries(expression)")
    cur.execute("CREATE INDEX idx_reading    ON entries(reading)")
    conn.commit()


def extract_entry(entry: ET.Element):
    """Parse a single <entry> into a tuple matching the DB schema."""
    ent_seq_text = entry.findtext("ent_seq")
    if not ent_seq_text:
        return None
    try:
        ent_seq = int(ent_seq_text)
    except ValueError:
        return None

    kebs = [keb.text for keb in entry.findall("k_ele/keb") if keb.text]
    rebs = [reb.text for reb in entry.findall("r_ele/reb") if reb.text]
    if not rebs:
        return None

    expression = kebs[0] if kebs else rebs[0]
    reading = rebs[0]

    glosses = []
    for sense in entry.findall("sense"):
        for gloss in sense.findall("gloss"):
            lang = gloss.get("{http://www.w3.org/XML/1998/namespace}lang", "eng")
            if lang != "eng":
                continue
            if gloss.text:
                glosses.append(gloss.text)
                if len(glosses) == 3:
                    break
        if len(glosses) == 3:
            break

    if not glosses:
        return None

    gloss1, gloss2, gloss3 = (glosses + [None, None, None])[:3]

    pos_codes = []
    for sense in entry.findall("sense"):
        for pos in sense.findall("pos"):
            if pos.text and pos.text not in pos_codes:
                pos_codes.append(pos.text)
    pos_str = ";".join(pos_codes) if pos_codes else None

    is_common = 1 if (entry.findall(".//ke_pri") or entry.findall(".//re_pri")) else 0

    return (ent_seq, expression, reading, gloss1, gloss2, gloss3, pos_str, is_common)


def convert(xml_path: Path, db_path: Path):
    print(f"Reading: {xml_path}")
    print(f"Writing: {db_path}")

    conn = sqlite3.connect(db_path)
    create_db(conn)
    cur = conn.cursor()

    context = ET.iterparse(open_xml(xml_path), events=("start", "end"))
    event, root = next(context)

    batch = []
    processed = 0
    inserted = 0
    BATCH_SIZE = 1000

    for event, elem in context:
        if event == "end" and elem.tag == "entry":
            processed += 1
            row = extract_entry(elem)
            if row is not None:
                batch.append(row)
                inserted += 1

            if len(batch) >= BATCH_SIZE:
                cur.executemany(
                    """
                    INSERT INTO entries
                    (ent_seq, expression, reading, gloss1, gloss2, gloss3, pos, common)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    batch,
                )
                conn.commit()
                batch.clear()
                print(f"Processed {processed:,} entries...", end="\r")

            elem.clear()
            root.clear()

    if batch:
        cur.executemany(
            """
            INSERT INTO entries
            (ent_seq, expression, reading, gloss1, gloss2, gloss3, pos, common)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            batch,
        )
        conn.commit()

    conn.close()
    print(f"\nDone! {inserted:,} entries inserted.")


def main():
    parser = argparse.ArgumentParser(description="Convert JMdict XML to SQLite database.")
    parser.add_argument("xml_path", type=Path, help="Path to JMdict_e XML or gzipped file")
    parser.add_argument("db_path", type=Path, help="Output SQLite database file")
    args = parser.parse_args()

    convert(args.xml_path, args.db_path)


if __name__ == "__main__":
    main()
