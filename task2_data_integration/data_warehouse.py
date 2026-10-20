"""Task 2 - Data integration via a DATA WAREHOUSE (DBLP + ACM bibliographic sources).

Steps
  1. create_sources()  : build two SQLite source DBs (different schemas) with a few sample rows
  2. etl()             : Extract from both sources, Transform (clean / standardise / match), Load into warehouse.db
  3. demo_queries()    : query the warehouse
Run: python3 data_warehouse.py
"""
import csv, html, io, os, re, sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
ACM_DB, DBLP_DB, DW_DB = (os.path.join(HERE, n) for n in ("acm_source.db", "dblp_source.db", "warehouse.db"))
N_MATCHED, N_ONLY = 8, 3      # sample size: matched pairs, and unmatched rows per source


def read_csv(name):
    raw = open(os.path.join(DATA, name), "rb").read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:          # DBLP/ACM exports are Latin-1 (e.g. "J\xf6rg")
        text = raw.decode("cp1252", errors="replace")
    return list(csv.DictReader(io.StringIO(text, newline="")))


def fresh(path):
    if os.path.exists(path):
        os.remove(path)
    return sqlite3.connect(path)


# ----------------------------------------------------------------- 1. SOURCES
def create_sources():
    acm = {r["id"]: r for r in read_csv("ACM.csv")}
    dblp = {r["id"]: r for r in read_csv("DBLP2.csv")}
    pairs = [(m["idDBLP"], m["idACM"]) for m in read_csv("DBLP-ACM_perfectMapping.csv")
             if m["idDBLP"] in dblp and m["idACM"] in acm and acm[m["idACM"]]["authors"]]
    pairs = pairs[:N_MATCHED]
    mapped_d, mapped_a = {d for d, _ in pairs}, {a for _, a in pairs}
    all_d = {m["idDBLP"] for m in read_csv("DBLP-ACM_perfectMapping.csv")}
    all_a = {m["idACM"] for m in read_csv("DBLP-ACM_perfectMapping.csv")}
    only_a = [k for k, r in acm.items() if k not in all_a and r["authors"]][:N_ONLY]
    only_d = [k for k in dblp if k not in all_d][:N_ONLY]
    acm_ids = [a for _, a in pairs] + only_a
    dblp_ids = [d for d, _ in pairs] + only_d

    # ACM source: venue lookup + paper (authors kept as one comma-separated string)
    c = fresh(ACM_DB)
    c.executescript("""
        CREATE TABLE acm_venue (venue_id INTEGER PRIMARY KEY, venue_name TEXT);
        CREATE TABLE acm_paper (acm_id INTEGER PRIMARY KEY, title TEXT, authors TEXT,
                                venue_id INTEGER REFERENCES acm_venue, year INTEGER);""")
    vids = {}
    for k in acm_ids:
        r = acm[k]
        if r["venue"] not in vids:
            vids[r["venue"]] = len(vids) + 1
            c.execute("INSERT INTO acm_venue VALUES (?,?)", (vids[r["venue"]], r["venue"]))
        c.execute("INSERT INTO acm_paper VALUES (?,?,?,?,?)",
                  (int(k), r["title"], r["authors"], vids[r["venue"]], int(r["year"])))
    c.commit(); c.close()

    # DBLP source: normalised - paper + one row per author, venue is a short code
    c = fresh(DBLP_DB)
    c.executescript("""
        CREATE TABLE dblp_paper (dblp_key TEXT PRIMARY KEY, title TEXT, venue TEXT, year INTEGER);
        CREATE TABLE dblp_author (dblp_key TEXT REFERENCES dblp_paper, pos INTEGER, author_name TEXT,
                                  PRIMARY KEY (dblp_key, pos));""")
    for k in dblp_ids:
        r = dblp[k]
        c.execute("INSERT INTO dblp_paper VALUES (?,?,?,?)", (k, r["title"], r["venue"], int(r["year"])))
        for i, a in enumerate(r["authors"].split(","), 1):
            if a.strip():
                c.execute("INSERT INTO dblp_author VALUES (?,?,?)", (k, i, a))
    c.commit(); c.close()
    return pairs


# -------------------------------------------------------------- 2. WAREHOUSE
DW_SCHEMA = """
CREATE TABLE map_dblp_acm   (dblp_key TEXT PRIMARY KEY, acm_id INTEGER);   -- staging: entity-resolution result
CREATE TABLE dim_venue      (venue_sk INTEGER PRIMARY KEY, venue_name TEXT UNIQUE);
CREATE TABLE dim_author     (author_sk INTEGER PRIMARY KEY, author_name TEXT UNIQUE);
CREATE TABLE dim_paper      (paper_sk INTEGER PRIMARY KEY, title TEXT, year INTEGER,
                             venue_sk INTEGER REFERENCES dim_venue,
                             dblp_key TEXT, acm_id INTEGER, in_dblp INTEGER, in_acm INTEGER);
CREATE TABLE fact_authorship(paper_sk INTEGER REFERENCES dim_paper, author_sk INTEGER REFERENCES dim_author,
                             author_pos INTEGER, PRIMARY KEY (paper_sk, author_sk));
CREATE TABLE etl_log        (step TEXT, rows_in INTEGER, rows_out INTEGER, note TEXT);
"""

# Venue names differ between sources -> map every variant to one standard name
VENUE_STD = {
    "international conference on management of data": "SIGMOD Conference",
    "sigmod conference": "SIGMOD Conference",
    "very large data bases": "VLDB",
    "vldb": "VLDB",
    "acm sigmod record": "SIGMOD Record",
    "sigmod record": "SIGMOD Record",
    "the vldb journal — the international journal on very large data bases": "VLDB Journal",
    "vldb j.": "VLDB Journal",
    "acm transactions on database systems (tods)": "ACM TODS",
    "acm trans. database syst.": "ACM TODS",
}


def clean_text(s):
    s = html.unescape(s or "")                  # "&mdash;" -> "—"
    return re.sub(r"\s+", " ", s).strip()


def std_venue(v):
    v = clean_text(v)
    return VENUE_STD.get(v.lower(), v)


def clean_name(n):
    return clean_text(n)


def etl(pairs):
    dw = fresh(DW_DB)
    dw.executescript(DW_SCHEMA)
    log = lambda *a: dw.execute("INSERT INTO etl_log VALUES (?,?,?,?)", a)

    # EXTRACT (read-only attach of both sources)
    dw.execute("ATTACH ? AS acm", (ACM_DB,)); dw.execute("ATTACH ? AS dblp", (DBLP_DB,))
    acm_rows = dw.execute("""SELECT p.acm_id,p.title,p.authors,v.venue_name,p.year
                             FROM acm.acm_paper p JOIN acm.acm_venue v USING(venue_id)""").fetchall()
    dblp_rows = dw.execute("SELECT dblp_key,title,venue,year FROM dblp.dblp_paper").fetchall()
    dblp_auth = {}
    for k, pos, name in dw.execute("SELECT dblp_key,pos,author_name FROM dblp.dblp_author ORDER BY dblp_key,pos"):
        dblp_auth.setdefault(k, []).append(name)
    log("extract acm", len(acm_rows), len(acm_rows), "acm_paper JOIN acm_venue")
    log("extract dblp", len(dblp_rows), len(dblp_rows), "dblp_paper + dblp_author")

    # Entity resolution: known DBLP<->ACM links (ground-truth mapping file) restricted to loaded rows
    mapping = {m["idDBLP"]: int(m["idACM"]) for m in read_csv("DBLP-ACM_perfectMapping.csv")}
    dblp_keys = {r[0] for r in dblp_rows}; acm_keys = {r[0] for r in acm_rows}
    mapping = {d: a for d, a in mapping.items() if d in dblp_keys and a in acm_keys}
    dw.executemany("INSERT INTO map_dblp_acm VALUES (?,?)", mapping.items())
    log("entity resolution", len(dblp_rows) + len(acm_rows), len(mapping), "matched pairs")
    acm_to_dblp = {a: d for d, a in mapping.items()}

    # TRANSFORM + LOAD: one dim_paper row per real-world paper
    venues, authors = {}, {}

    def sk(table, cache, col, value):
        if value not in cache:
            cache[value] = len(cache) + 1
            dw.execute(f"INSERT INTO {table} VALUES (?,?)", (cache[value], value))
        return cache[value]

    def add_paper(title, year, venue, dblp_key, acm_id, names):
        psk = dw.execute("SELECT COUNT(*)+1 FROM dim_paper").fetchone()[0]
        dw.execute("INSERT INTO dim_paper VALUES (?,?,?,?,?,?,?,?)",
                   (psk, clean_text(title), year, sk("dim_venue", venues, "venue_name", std_venue(venue)),
                    dblp_key, acm_id, int(dblp_key is not None), int(acm_id is not None)))
        for pos, n in enumerate(names, 1):
            n = clean_name(n)
            if n:
                dw.execute("INSERT OR IGNORE INTO fact_authorship VALUES (?,?,?)",
                           (psk, sk("dim_author", authors, "author_name", n), pos))

    acm_by_id = {r[0]: r for r in acm_rows}
    for key, title, venue, year in dblp_rows:                       # DBLP is the base (clean author list)
        a = acm_by_id.get(mapping.get(key))
        add_paper(title, year, venue, key, a[0] if a else None, dblp_auth.get(key, []))
    for acm_id, title, auth, venue, year in acm_rows:               # ACM-only papers
        if acm_id not in acm_to_dblp:
            add_paper(title, year, venue, None, acm_id, auth.split(","))
    n = lambda t: dw.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    log("load dim_venue", 0, n("dim_venue"), "standardised venue names")
    log("load dim_author", 0, n("dim_author"), "distinct, trimmed author names")
    log("load dim_paper", len(dblp_rows) + len(acm_rows), n("dim_paper"), "duplicates merged")
    log("load fact_authorship", 0, n("fact_authorship"), "")
    dw.commit()
    return dw


# --------------------------------------------------------------- 3. DEMO
def show(dw, title, sql, params=()):
    cur = dw.execute(sql, params)
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    print(f"\n### {title}\n{sql.strip()}\n")
    w = [max(len(str(x)) for x in [c] + [r[i] for r in rows]) for i, c in enumerate(cols)]
    w = [min(x, 60) for x in w]
    fmt = lambda r: " | ".join(str(x)[:60].ljust(w[i]) for i, x in enumerate(r))
    print(fmt(cols)); print("-+-".join("-" * x for x in w))
    for r in rows: print(fmt(r))


def dump_sources():
    for path in (ACM_DB, DBLP_DB):
        c = sqlite3.connect(path)
        print(f"\n===== SOURCE {os.path.basename(path)} =====")
        for (t,) in c.execute("SELECT name FROM sqlite_master WHERE type='table'"):
            print(f"-- {t} ({c.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]} rows)")
            for r in c.execute(f"SELECT * FROM {t} LIMIT 4"):
                print("  ", tuple(str(x)[:45] for x in r))


def demo_queries(dw):
    print("\n===== WAREHOUSE =====")
    show(dw, "ETL log", "SELECT * FROM etl_log")
    show(dw, "Q1 Integrated papers (one row per real paper, with provenance)",
         """SELECT p.paper_sk, substr(p.title,1,45) AS title, p.year, v.venue_name, p.in_dblp, p.in_acm
            FROM dim_paper p JOIN dim_venue v USING(venue_sk) ORDER BY p.paper_sk""")
    show(dw, "Q2 Papers per standardised venue", """SELECT v.venue_name, COUNT(*) AS papers
            FROM dim_paper p JOIN dim_venue v USING(venue_sk) GROUP BY v.venue_name ORDER BY papers DESC""")
    show(dw, "Q3 Source coverage", """SELECT CASE WHEN in_dblp AND in_acm THEN 'both' WHEN in_dblp THEN 'DBLP only'
            ELSE 'ACM only' END AS coverage, COUNT(*) AS papers FROM dim_paper GROUP BY 1""")
    show(dw, "Q4 Most prolific authors", """SELECT a.author_name, COUNT(*) AS papers
            FROM fact_authorship f JOIN dim_author a USING(author_sk) GROUP BY a.author_sk
            ORDER BY papers DESC, a.author_name LIMIT 5""")
    show(dw, "Q5 Authors of papers present in BOTH sources", """SELECT substr(p.title,1,40) AS title,
            group_concat(a.author_name, '; ') AS authors FROM dim_paper p
            JOIN fact_authorship f USING(paper_sk) JOIN dim_author a USING(author_sk)
            WHERE p.in_dblp AND p.in_acm GROUP BY p.paper_sk LIMIT 4""")


if __name__ == "__main__":
    pairs = create_sources()
    dump_sources()
    dw = etl(pairs)
    demo_queries(dw)
