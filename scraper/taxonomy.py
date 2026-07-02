"""The fixed topic/subtopic taxonomy used by the classifier and the dashboard."""

TAXONOMY = {
    "strikes_on_ukraine": {
        "label": "Strikes on Ukraine",
        "color": "#00205B",
        "subtopics": {
            "deep_strikes": "Deep strikes on cities & industry",
            "fuel_infrastructure": "Fuel-infrastructure campaign",
            "other": "Other strikes on Ukraine",
        },
    },
    "frontline": {
        "label": "Frontline",
        "color": "#00A3E0",
        "subtopics": {
            "pokrovsk": "Pokrovsk direction",
            "hulyaipole": "Hulyaipole / Zaporizhzhia direction",
            "kupyansk": "Kupyansk / Kharkiv direction",
            "other": "Other directions",
        },
    },
    "ukraine_strikes_on_russia": {
        "label": "Ukraine strikes on Russia",
        "color": "#D19000",
        "subtopics": {
            "crimea_energy": "Crimea fuel & energy crisis",
            "drones_on_regions": "Drones on Russian regions",
            "other": "Other Ukrainian strikes",
        },
    },
    "west_nato": {
        "label": "West & NATO",
        "color": "#005A70",
        "subtopics": {
            "military_aid": "Military aid to Ukraine",
            "rearmament": "European rearmament",
            "negotiations": "Negotiations & diplomacy",
            "alliance_politics": "Alliance politics",
            "other": "Other West & NATO",
        },
    },
    "russia_internal": {
        "label": "Russia internal",
        "color": "#7D55C7",
        "subtopics": {
            "ideology_society": "Ideology & society essays",
            "security_cases": "Security & treason cases",
            "elite_politics": "Elite politics",
            "economy": "Economy & sanctions",
            "mobilisation": "Mobilisation & recruitment",
            "other": "Other Russia internal",
        },
    },
    "criticism": {
        "label": "Criticism",
        "color": "#FF6900",
        "subtopics": {
            "army_command": "Army command & logistics",
            "government": "Government & ministries",
            "putin": "Putin personally",
            "regional": "Regional authorities",
            "other": "Other criticism",
        },
    },
}

# Standing watchlist: (topic, subtopic) pairs that get flagged the moment they appear
WATCHLIST = [
    ("russia_internal", "mobilisation", "Mobilisation rumours"),
    ("criticism", "putin", "Criticism of Putin"),
]

CHANNEL_LABELS = {
    "rybar": "Rybar",
    "dva_majors": "Two Majors",
    "wargonzo": "WarGonzo",
    "Sladkov_plus": "Sladkov+",
    "epoddubny": "Poddubny",
    "sashakots": "Kotsnews",
    "grey_zone": "Grey Zone",
    "rusich_army": "Arkhangel Spetsnaza",
    "vysokygovorit": "Starshe Eddy",
    "ngp_razvedka": "NgP raZVedka",
}
