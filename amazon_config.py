from dataclasses import dataclass

# Country and category configurations with postcodes
COUNTRY_CONFIGS = {
    "germany": {
        "domain": "amazon.de",
        "country_code": "DE",
        "locale": "de-DE",
        "use_postcode": True,
        "postcode": "10115",
    },
    "sweden": {
        "domain": "amazon.se",
        "country_code": "SE",
        "locale": "sv-SE",
        "use_postcode": True,
        "postcode": "112 19",
    },
    "france": {
        "domain": "amazon.fr",
        "country_code": "FR",
        "locale": "fr-FR",
        "use_postcode": True,
        "postcode": "75017",
        "note": "May show intermediate page with 'Continuer les achats' button",
    },
    "italy": {
        "domain": "amazon.it",
        "country_code": "IT",
        "locale": "it-IT",
        "use_postcode": True,
        "postcode": "00195",
        "note": "May show intermediate page with 'Clicca qui per tornare alla home page' link",
    },
    "spain": {
        "domain": "amazon.es",
        "country_code": "ES",
        "locale": "es-ES",
        "use_postcode": True,
        "postcode": "28055",
        "note": "May show intermediate page with 'Seguir comprando' button",
    },
    "netherlands": {
        "domain": "amazon.nl",
        "country_code": "NL",
        "locale": "nl-NL",
        "use_postcode": False,
    },
}

# Categories with energy labels
ENERGY_CATEGORIES = {
    "light_sources": "Light Sources",
    "domestic_ovens": "Domestic Ovens",
    "range_hoods": "Range Hoods",
    "dishwashers": "Household Dishwashers",
    "washing_machines": "Household Washing Machines",
    "washing_dryers": "Household Washing Dryers",
    "tumble_dryers": "Tumble Dryers",
    "fridges_freezers": "Fridges and Freezers",
    "commercial_refrigerators": "Commercial Refrigerators",
    "professional_refrigerated_cabinets": "Professional Refrigerated Storage Cabinets",
    "air_conditioners": "Air Conditioners and Comfort Fans",
    "space_heaters": "Local Space Heaters",
    "ventilation_units": "Ventilation Units",
    "solid_fuel_boilers": "Solid Fuel Boilers",
    "water_heaters": "Water Heaters",
    "electronic_displays": "Electronic Displays",
    "smartphones_tablets": "Smartphones and Tablets",
    "tires": "Tires",
}

# Category search queries for each marketplace
CATEGORY_QUERIES = {
    "light_sources": {
        "amazon.se": "ljuskällor",
        "amazon.fr": "sources lumineuses",
        "amazon.it": "sorgenti luminose",
        "amazon.es": "fuentes de luz",
        "amazon.nl": "lichtbronnen",
    },
    "domestic_ovens": {
        "amazon.se": "ugnar",
        "amazon.fr": "fours domestiques",
        "amazon.it": "forni domestici",
        "amazon.es": "hornos domésticos",
        "amazon.nl": "ovens",
    },
    "range_hoods": {
        "amazon.se": "köksfläktar",
        "amazon.fr": "hottes de cuisine",
        "amazon.it": "cappe da cucina",
        "amazon.es": "campanas extractoras",
        "amazon.nl": "afzuigkappen",
    },
    "dishwashers": {
        "amazon.se": "diskmaskiner",
        "amazon.fr": "lave-vaisselle",
        "amazon.it": "lavastoviglie",
        "amazon.es": "lavavajillas",
        "amazon.nl": "vaatwassers",
    },
    "washing_machines": {
        "amazon.se": "tvättmaskiner",
        "amazon.fr": "machines à laver",
        "amazon.it": "lavatrici",
        "amazon.es": "lavadoras",
        "amazon.nl": "wasmachines",
    },
    "washing_dryers": {
        "amazon.se": "torktumlare",
        "amazon.fr": "sèche-linge",
        "amazon.it": "asciugatrici",
        "amazon.es": "secadoras",
        "amazon.nl": "wasdrogers",
    },
    "tumble_dryers": {
        "amazon.se": "torktumlare",
        "amazon.fr": "sèche-linge tambour",
        "amazon.it": "asciugatrici a tamburo",
        "amazon.es": "secadoras de tambor",
        "amazon.nl": "trommel drogers",
    },
    "fridges_freezers": {
        "amazon.se": "kylskåp frysar",
        "amazon.fr": "réfrigérateurs congélateurs",
        "amazon.it": "frigoriferi congelatori",
        "amazon.es": "frigoríficos congeladores",
        "amazon.nl": "koelkasten vriezers",
    },
    "air_conditioners": {
        "amazon.se": "luftkonditionering",
        "amazon.fr": "climatiseurs",
        "amazon.it": "condizionatori",
        "amazon.es": "aires acondicionados",
        "amazon.nl": "airconditioners",
    },
    "water_heaters": {
        "amazon.se": "varmvattenberedare",
        "amazon.fr": "chauffe-eau",
        "amazon.it": "scaldacqua",
        "amazon.es": "calentadores de agua",
        "amazon.nl": "boilers",
    },
    "electronic_displays": {
        "amazon.se": "bildskärmar",
        "amazon.fr": "écrans électroniques",
        "amazon.it": "display elettronici",
        "amazon.es": "pantallas electrónicas",
        "amazon.nl": "elektronische displays",
    },
    "smartphones_tablets": {
        "amazon.se": "smartphones surfplattor",
        "amazon.fr": "smartphones tablettes",
        "amazon.it": "smartphone tablet",
        "amazon.es": "smartphones tablets",
        "amazon.nl": "smartphones tablets",
    },
    "tires": {
        "amazon.se": "däck",
        "amazon.fr": "pneus",
        "amazon.it": "pneumatici",
        "amazon.es": "neumáticos",
        "amazon.nl": "banden",
    },
}


# Optional: direct seed category URLs per country (will be used if present)
CATEGORY_SEED_URLS = {
    "germany": [
        "https://www.amazon.de/s?i=electronics&rh=n%3A3468301&s=popularity-rank&fs=true&language=en&ref=lp_3468301_sar",
    ],
    "italy": [
        "https://www.amazon.it/s?i=electronics&srs=203868731031&rh=n%3A203868731031&s=popularity-rank&fs=true&language=en&ref=lp_203868731031_sar",
    ],
    "sweden": [
        "https://www.amazon.se/s?i=electronics&rh=n%3A20637719031&s=popularity-rank&fs=true&language=en&ref=lp_20637719031_sar",
    ],
}


