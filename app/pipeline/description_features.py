import re
import unicodedata


def normalize_text(text: str | None) -> str:
    if not text:
        return ""

    text = text.lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def has_any(text: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def extract_upfront_terms(
    title: str | None,
    description: str | None,
    seller_name: str | None = None,
) -> dict:
    text = normalize_text(" ".join([title or "", description or "", seller_name or ""]))

    no_pets = has_any(
        text,
        [
            r"nu\s+accepta\s+animale",
            r"fara\s+animale",
            r"nu\s+se\s+accepta\s+animale",
        ],
    )

    is_pet_friendly = has_any(
        text,
        [
            r"pet\s*friendly",
            r"accepta\s+animale",
            r"animale\s+acceptate",
            r"acceptam\s+animale",
            r"se\s+accepta\s+animale",
            r"cu\s+animale?",
        ],
    )

    if no_pets:
        is_pet_friendly = False

    has_no_commission = has_any(
        text,
        [
            r"fara\s+comision",
            r"0%\s*comision",
            r"zero\s+comision",
            r"comision\s*0",
        ],
    )

    is_private_owner = has_any(
        text,
        [
            r"\bproprietar\b",
            r"direct\s+proprietar",
            r"fara\s+agentie",
            r"fara\s+comision",
            r"0%\s*comision",
            r"zero\s+comision",
        ],
    )

    is_agency = has_any(
        text,
        [
            r"\bagentie\b",
            r"\bagentia\b",
            r"\bcomision\b",
            r"comision\s+agentie",
            r"consultant\s+imobiliar",
            r"reprezentant",
        ],
    ) and not has_no_commission

    has_parking = has_any(
        text,
        [
            r"loc\s+de\s+parcare",
            r"parcare\s+inclusa",
            r"parcare\s+privata",
            r"parcare\s+subterana",
        ],
    )

    deposit_months = None
    upfront_rent_months = None
    agency_commission_percent = None
    agency_commission_months = None

    deposit_patterns = [
        r"garantie\s+(?:de\s+)?(\d+(?:[.,]\d+)?)\s+lun",
        r"deposit\s+(?:de\s+)?(\d+(?:[.,]\d+)?)\s+lun",
        r"cautiune\s+(?:de\s+)?(\d+(?:[.,]\d+)?)\s+lun",
        r"o\s+garantie",
        r"1\s+garantie",
    ]

    for pattern in deposit_patterns:
        match = re.search(pattern, text)
        if match:
            if match.groups():
                deposit_months = float(match.group(1).replace(",", "."))
            else:
                deposit_months = 1.0
            break

    upfront_patterns = [
        r"(\d+(?:[.,]\d+)?)\s+lun[ia]\s+avans",
        r"avans\s+(\d+(?:[.,]\d+)?)\s+lun",
        r"o\s+luna\s+avans",
        r"1\s+luna\s+avans",
        r"chirie\s+in\s+avans",
    ]

    for pattern in upfront_patterns:
        match = re.search(pattern, text)
        if match:
            if match.groups():
                upfront_rent_months = float(match.group(1).replace(",", "."))
            else:
                upfront_rent_months = 1.0
            break

    commission_percent_match = re.search(
        r"comision(?:ul)?(?:\s+agentiei)?\s*(?:este\s*)?(\d{1,3})\s*%",
        text,
    )
    if commission_percent_match:
        agency_commission_percent = float(commission_percent_match.group(1))

    commission_month_match = re.search(
        r"comision(?:ul)?(?:\s+agentiei)?\s*(?:este\s*)?(\d+(?:[.,]\d+)?)\s+lun",
        text,
    )
    if commission_month_match:
        agency_commission_months = float(commission_month_match.group(1).replace(",", "."))

    if has_no_commission:
        agency_commission_percent = 0.0
        agency_commission_months = 0.0

    has_upfront_cost_info = any(
        value is not None
        for value in [
            deposit_months,
            upfront_rent_months,
            agency_commission_percent,
            agency_commission_months,
        ]
    )

    return {
        "is_pet_friendly": is_pet_friendly,
        "is_private_owner": is_private_owner,
        "is_agency": is_agency,
        "has_no_commission": has_no_commission,
        "has_parking": has_parking,
        "deposit_months": deposit_months,
        "upfront_rent_months": upfront_rent_months,
        "agency_commission_percent": agency_commission_percent,
        "agency_commission_months": agency_commission_months,
        "has_upfront_cost_info": has_upfront_cost_info,
    }


def description_score(features: dict) -> float:
    score = 0.0

    if features.get("is_pet_friendly"):
        score += 0.8

    if features.get("is_private_owner"):
        score += 0.7

    if features.get("has_no_commission"):
        score += 0.8

    if features.get("has_parking"):
        score += 0.4

    deposit = features.get("deposit_months")
    upfront = features.get("upfront_rent_months")
    commission_percent = features.get("agency_commission_percent")
    commission_months = features.get("agency_commission_months")

    if deposit is not None:
        if deposit <= 1:
            score += 0.2
        elif deposit >= 2:
            score -= 0.5

    if upfront is not None:
        if upfront <= 1:
            score += 0.1
        elif upfront >= 2:
            score -= 0.5

    if commission_percent is not None:
        if commission_percent == 0:
            score += 0.5
        elif commission_percent >= 50:
            score -= 0.7

    if commission_months is not None:
        if commission_months == 0:
            score += 0.5
        elif commission_months >= 0.5:
            score -= 0.6

    if features.get("is_agency") and not features.get("has_no_commission"):
        score -= 0.3

    return round(score, 2)