"""Region names as they appear in government files, mapped to the codes PolicyEngine uses."""

STATE_CODES = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR", "California": "CA",
    "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE", "District of Columbia": "DC",
    "Florida": "FL", "Georgia": "GA", "Hawaii": "HI", "Idaho": "ID", "Illinois": "IL",
    "Indiana": "IN", "Iowa": "IA", "Kansas": "KS", "Kentucky": "KY", "Louisiana": "LA",
    "Maine": "ME", "Maryland": "MD", "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN",
    "Mississippi": "MS", "Missouri": "MO", "Montana": "MT", "Nebraska": "NE", "Nevada": "NV",
    "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY",
    "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK", "Oregon": "OR",
    "Pennsylvania": "PA", "Rhode Island": "RI", "South Carolina": "SC", "South Dakota": "SD",
    "Tennessee": "TN", "Texas": "TX", "Utah": "UT", "Vermont": "VT", "Virginia": "VA",
    "Washington": "WA", "West Virginia": "WV", "Wisconsin": "WI", "Wyoming": "WY",
    "Guam": "GU", "Virgin Islands": "VI",
}

# Sub-state SNAP areas, keyed by (state, area name as FNS writes it).
SNAP_AREAS = {
    ("Alaska", "Central"): "AK_C",
    ("Alaska", "Northern"): "AK_N",
    ("Alaska", "Northwest"): "AK_NW",
    ("Alaska", "Southcentral"): "AK_SC",
    ("Alaska", "Southeast"): "AK_SE",
    ("Alaska", "Southwest"): "AK_SW",
    ("New York", "Nassau and Suffolk Counties"): "NY_NAS",
    ("New York", "New York City"): "NY_NYC",
    ("New York", "Rest of New York State"): "NY_ONY",
}
