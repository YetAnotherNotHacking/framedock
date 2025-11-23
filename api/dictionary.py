import csv
import sys
csv.field_size_limit(sys.maxsize)

data = {}

def import_dictionary():
    with open("dict.csv", newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            w = row["word"].lower()
            if w not in data:
                data[w] = []
            data[w].append({
                "part_of_speech": row["pos"],
                "definition": row["definition"]
            })
    return data