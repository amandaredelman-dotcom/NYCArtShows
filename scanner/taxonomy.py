"""Genre labels used across the scanner and the website.

Each show gets:
  - genres: its own period/movement, plus culture/region where it matters
  - media: what kinds of objects are on view
  - related: traditions a show is "in dialogue with" (edge cases), each with a short note
"""

FAMILIES = {
    "Old Masters": ["Medieval", "Renaissance", "Baroque", "Dutch Golden Age", "Rococo"],
    "18th–19th century": [
        "Neoclassicism", "Romanticism", "Academic & Salon", "Hudson River School",
        "Realism (19th c.)", "Impressionism", "Post-Impressionism", "Symbolism",
    ],
    "Modern": [
        "Modernism", "Expressionism", "Cubism", "Surrealism", "Modern sculpture",
        "Abstract Expressionism", "Pop Art", "Minimalism",
    ],
    "Contemporary": [
        "Contemporary painting", "Contemporary realism", "Photorealism & hyperrealism",
        "Abstraction", "Conceptual & installation", "Video & new media", "Street art & graffiti",
    ],
    "Photography": ["Photography"],
    "Design & fashion": ["Decorative arts", "Design & architecture", "Fashion"],
    "Ancient & world": [
        "Ancient", "Islamic world", "East Asian", "Japanese", "South Asian", "African",
        "Indigenous", "Latin American", "Spanish", "Oceanic",
    ],
}

GENRES = [g for gs in FAMILIES.values() for g in gs]

MEDIA = [
    "Painting", "Sculpture", "Works on paper", "Photography", "Installation",
    "Video", "Fashion & textiles", "Decorative arts", "Books & manuscripts", "Performance",
]

GENRE_GUIDE = """
Use ONLY these genre labels (copy them exactly):
{genres}

Rules:
- "genres" = what the work on view actually IS: its period or movement, plus a culture/region label when it matters.
- Living artists get contemporary labels, even if their style looks old. A living painter in a realist
  style is "Contemporary realism"; near-photographic precision is "Photorealism & hyperrealism".
- "related" = an earlier tradition the show deliberately responds to or quotes (an edge case), e.g. a
  contemporary artist reworking a Vermeer -> related genre "Dutch Golden Age" with a note naming the link.
  Leave "related" empty when there is no clear, stated connection.
- Use at most 4 genres and 2 related entries.
- Set "confident" to false if the page gives too little information to be sure.
""".strip()


def guide_text() -> str:
    return GENRE_GUIDE.format(genres="\n".join(f"- {g}" for g in GENRES))
