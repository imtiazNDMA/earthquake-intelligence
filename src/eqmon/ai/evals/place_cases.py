"""Human-labeled place-resolution cases.

Keep development examples separate from future locked release cases. These
cases exercise known spelling noise and ambiguity; they are not a substitute
for operator-derived production examples.
"""

CORPUS_VERSION = "1.0"

PLACE_CASES = (
    {"probe": "Kwetta", "level": "district", "expected": "resolved",
     "name": "Quetta", "parent": "Balochistan"},
    {"probe": "Peshwar", "level": "district", "expected": "resolved",
     "name": "Peshawar", "parent": "Khyber Pakhtunkhwa"},
    {"probe": "Muzafarabad", "level": "district", "expected": "resolved",
     "name": "Muzaffarabad", "parent": "Azad Kashmir"},
    {"probe": "Abbotabad", "level": "district", "expected": "resolved",
     "name": "Abbottabad", "parent": "Khyber Pakhtunkhwa"},
    {"probe": "Skardo", "level": "district", "expected": "resolved",
     "name": "Skardu", "parent": "Gilgit Baltistan"},
    {"probe": "Dera Ismail Khn", "level": "district", "expected": "resolved",
     "name": "Dera Ismail Khan", "parent": "Khyber Pakhtunkhwa"},
    {"probe": "Rawalpindi Dist.", "level": "district", "expected": "resolved",
     "name": "Rawalpindi", "parent": "Punjab"},
    {"probe": "Nowshehra", "level": "district", "expected": "resolved",
     "name": "Nowshera", "parent": "Khyber Pakhtunkhwa"},
    {"probe": "Khanpur", "level": "tehsil", "expected": "ambiguous"},
    {"probe": "Khanpur", "level": "tehsil", "parent": "Haripur",
     "expected": "resolved", "name": "Khanpur"},
    {"probe": "Sahiwal", "level": "tehsil", "expected": "ambiguous"},
    {"probe": "Dera Ghazi Khan", "level": "tehsil", "expected": "ambiguous"},
    {"probe": "Reykjavik", "level": "district", "expected": "not_found"},
    {"probe": "Atlantis", "level": "tehsil", "expected": "not_found"},
    {"probe": "Paris", "level": "tehsil", "expected": "not_found"},
    {"probe": "Kathmandu", "level": "tehsil", "expected": "not_found"},
    {"probe": "America", "level": "tehsil", "expected": "not_found"},
    {"probe": "London", "level": "district", "expected": "not_found"},
    {"probe": "Tokyo", "level": "district", "expected": "not_found"},
    {"probe": "Sydney", "level": "tehsil", "expected": "not_found"},
    {"probe": "", "level": "district", "expected": "not_found"},
)
