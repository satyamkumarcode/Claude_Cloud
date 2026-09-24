"""
Builds the Chen-notation ER diagram for the Tennis 2025 database
(entities = rectangles, relationships = diamonds, attributes = ellipses,
PK attributes underlined, dashed lines = partial/optional participation).
Based on data/Tennis_DB_Schema.xlsx.

Output: docs/er_diagram.svg and docs/er_diagram.png
"""
import graphviz

g = graphviz.Graph("TennisER", engine="dot")
g.attr(rankdir="TB", splines="line", ranksep="1.1", nodesep="0.35",
       pad="0.3", concentrate="false")
g.attr("node", fontname="Helvetica", fontsize="12")
g.attr("edge", fontname="Helvetica", fontsize="10", color="#666666")

ENTITY = dict(shape="box", style="filled", fillcolor="#d6e8f7",
              color="#2c5f8a", fontcolor="#1a1a1a", width="1.3", height="0.6")
REL = dict(shape="diamond", style="filled", fillcolor="#fbe3b0",
           color="#b8860b", fontcolor="#1a1a1a")
ATTR = dict(shape="ellipse", style="filled", fillcolor="#ffffff",
            color="#999999", fontcolor="#1a1a1a", width="0.1", height="0.35")


def attr_label(label, is_pk):
    return f"<<u>{label}</u>>" if is_pk else label


def entity_with_attrs(node_id, label, attrs, rank_group):
    """attrs: list of (attr_id, attr_label, is_pk, multivalued)"""
    g.node(node_id, label, **ENTITY)
    with g.subgraph(name=f"cluster_rank_{rank_group}_{node_id}") as s:
        pass
    same_rank_ids = [node_id]
    for attr_id, attr_lbl, is_pk, multi in attrs:
        style = dict(ATTR)
        if multi:
            style["peripheries"] = "2"
        g.node(attr_id, attr_label(attr_lbl, is_pk), **style)
        g.edge(node_id, attr_id, constraint="false", len="0.6")
        same_rank_ids.append(attr_id)
    with g.subgraph() as s:
        s.attr(rank="same")
        for nid in same_rank_ids:
            s.node(nid)


def relationship(node_id, label):
    g.node(node_id, label, **REL)


def link(a, b, card_a="", card_b="", style="solid"):
    g.edge(a, b, headlabel=card_b, taillabel=card_a,
           labeldistance="1.8", labelangle="20", style=style,
           fontcolor="#1a1a1a")


# ============================================================ LAYER 0
entity_with_attrs("country", "country", [
    ("country_code", "country_code", True, False),
    ("country_name", "country", False, False),
], 0)

# ============================================================ LAYER 1
entity_with_attrs("city", "city", [
    ("city_id", "city_id", True, False),
    ("city_name", "city", False, False),
], 1)

entity_with_attrs("coach", "coach", [
    ("coach_id", "coach_id", True, False),
    ("coach_full_name", "coach_full_name", False, False),
], 1)

entity_with_attrs("round", "round", [
    ("round_code", "round_code", True, False),
    ("round_name", "round_name", False, False),
    ("sequence_order", "sequence_order", False, False),
], 1)

entity_with_attrs("series", "tournament_series", [
    ("series_id", "series_id", True, False),
    ("series_name", "series_name", False, False),
    ("category", "category / level", False, False),
], 1)

with g.subgraph() as s:
    s.attr(rank="same")
    s.node("city")
    s.node("coach")
    s.node("round")
    s.node("series")

# ============================================================ LAYER 2
entity_with_attrs("player", "player", [
    ("player_id", "player_id", True, False),
    ("player_name", "player_name", False, False),
    ("atp_name", "atp_name", False, False),
    ("birthdate", "birthdate", False, False),
    ("weight_kg", "weight_kg", False, False),
    ("height_cm", "height_cm", False, False),
    ("turned_pro", "turned_pro", False, False),
    ("hand", "hand", False, False),
    ("backhand", "backhand", False, False),
], 2)

entity_with_attrs("venue", "venue", [
    ("venue_id", "venue_id", True, False),
    ("venue_name", "venue_name", False, False),
    ("surface", "surface", False, False),
], 2)

with g.subgraph() as s:
    s.attr(rank="same")
    s.node("player")
    s.node("venue")

# ============================================================ LAYER 3
entity_with_attrs("edition", "tournament_edition", [
    ("tourney_id", "tourney_id", True, False),
    ("draw_size", "draw_size", False, False),
    ("start_date", "start_date", False, False),
], 3)

# ============================================================ LAYER 4
entity_with_attrs("match", "match", [
    ("match_id", "match_id", True, False),
    ("match_date", "match_date", False, False),
    ("match_num", "match_num", False, False),
    ("indoor", "indoor (O/I)", False, False),
    ("score", "score", False, False),
    ("minutes", "minutes", False, False),
    ("best_of", "best_of", False, False),
    ("winner_seed", "winner_seed", False, False),
    ("winner_entry", "winner_entry", False, False),
    ("winner_rank", "winner_rank", False, False),
    ("winner_rank_points", "winner_rank_points", False, False),
    ("loser_seed", "loser_seed", False, False),
    ("loser_entry", "loser_entry", False, False),
    ("loser_rank", "loser_rank", False, False),
    ("loser_rank_points", "loser_rank_points", False, False),
    ("stats", "18 serve/return stats\n(w_*, l_*)", False, False),
], 4)

# ============================================================ RELATIONSHIPS

# R1: city -(N)- located_in -(1)- country
relationship("R_city_country", "located_in")
link("city", "R_city_country", card_a="N")
link("R_city_country", "country", card_b="1")

# R2: player -(N)- born_in -(1)- city   [partial: birthplace nullable]
relationship("R_born_in", "born_in")
link("player", "R_born_in", card_a="N", style="dashed")
link("R_born_in", "city", card_b="1", style="dashed")

# R3: player -(N)- coaches -(N)- coach
relationship("R_coaches", "coaches")
link("player", "R_coaches", card_a="N")
link("R_coaches", "coach", card_b="N")

# R4: player -(N)- represents -(N)- country  (has attrs start_year, end_year)
relationship("R_represents", "represents")
link("player", "R_represents", card_a="N")
link("R_represents", "country", card_b="N")
g.node("start_year", "start_year", **ATTR)
g.node("end_year", "end_year", **ATTR)
g.edge("R_represents", "start_year")
g.edge("R_represents", "end_year")
with g.subgraph() as s:
    s.attr(rank="same")
    s.node("R_represents")
    s.node("start_year")
    s.node("end_year")

# R5: venue -(N)- located_in -(1)- city
relationship("R_venue_city", "located_in")
link("venue", "R_venue_city", card_a="N")
link("R_venue_city", "city", card_b="1")

# R6: venue -(N)- located_in -(1)- country  [documented redundancy, see report]
relationship("R_venue_country", "located_in")
link("venue", "R_venue_country", card_a="N")
link("R_venue_country", "country", card_b="1", style="dashed")

# R7: series -(1)- has_edition -(N)- edition
relationship("R_has_edition", "has_edition")
link("series", "R_has_edition", card_a="1")
link("R_has_edition", "edition", card_b="N")

# R8: venue -(1)- hosts -(N)- edition
relationship("R_hosts", "hosts")
link("venue", "R_hosts", card_a="1")
link("R_hosts", "edition", card_b="N")

# R9: edition -(1)- includes -(N)- match
relationship("R_includes", "includes")
link("edition", "R_includes", card_a="1")
link("R_includes", "match", card_b="N")

# R10: round -(1)- stage_of -(N)- match
relationship("R_stage_of", "stage_of")
link("round", "R_stage_of", card_a="1")
link("R_stage_of", "match", card_b="N")

# R11: player -(1)- wins -(N)- match
relationship("R_wins", "wins")
link("player", "R_wins", card_a="1")
link("R_wins", "match", card_b="N")

# R12: player -(1)- loses -(N)- match
relationship("R_loses", "loses")
link("player", "R_loses", card_a="1")
link("R_loses", "match", card_b="N")

g.render("docs/er_diagram", format="svg", cleanup=True)
g.render("docs/er_diagram", format="png", cleanup=True)
print("done")
