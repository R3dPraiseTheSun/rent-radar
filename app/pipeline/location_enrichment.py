import re
import unicodedata


ZONE_ALIASES = {
    "Copou": [
        "copou",
        "royal town",
        "sadoveanu",
        "negruzzi",
        "titu maiorescu",
        "universitatea de stiinte agricole",
    ],
    "Tatarasi": [
        "tatarasi",
        "tătărași",
        "flora",
        "metalurgiei",
        "tudor center",
    ],
    "Podu Ros": [
        "podu ros",
        "podu roș",
        "podu-ros",
        "socola",
        "liceul racovita",
        "racoviță",
    ],
    "Nicolina": [
        "nicolina",
        "lacului",
        "salciilor",
    ],
    "Pacurari": [
        "pacurari",
        "păcurari",
        "petru poni",
        "kaufland pacurari",
        "comat towers",
    ],
    "Alexandru cel Bun": [
        "alexandru cel bun",
        "alexandru-cel-bun",
        "zimbru",
    ],
    "Centru": [
        "centru",
        "central",
        "ultracentral",
        "palas",
        "piata unirii",
        "piața unirii",
        "stefan cel mare",
        "mitropolie",
        "gara",
        "arcu",
        "independentei",
        "umf",
        "uaic",
    ],
    "CUG": [
        "cug",
        "rond cug",
        "capat cug",
        "capăt cug",
        "alee tudor neculai",
    ],
    "Moara de Vant": [
        "moara de vant",
        "moara de vânt",
        "moara-de-vant",
        "7moon",
        "roua",
    ],
    "Dacia": [
        "dacia",
    ],
    "Bucium": [
        "bucium",
        "poitiers",
        "poitiers towers",
    ],
    "Galata": [
        "galata",
    ],
    "Frumoasa": [
        "frumoasa",
    ],
    "Mircea cel Batran": [
        "mircea cel batran",
        "mircea cel bătrân",
        "mircea-cel-batran",
    ],
    "Tudor Vladimirescu": [
        "tudor vladimirescu",
        "tudor-vladimirescu",
    ],
}


def normalize_text(text: str | None) -> str:
    if not text:
        return ""

    text = text.lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def infer_zone_from_text(
    title: str | None,
    description: str | None,
    url: str | None,
    current_zone: str | None = None,
) -> tuple[str | None, str | None]:
    text = normalize_text(" ".join([title or "", description or "", url or ""]))

    matches = []

    for zone, aliases in ZONE_ALIASES.items():
        for alias in aliases:
            alias_norm = normalize_text(alias)

            if alias_norm and alias_norm in text:
                matches.append((zone, alias))
                break

    if not matches:
        return current_zone, None

    inferred_zone, matched_alias = matches[0]

    return inferred_zone, matched_alias