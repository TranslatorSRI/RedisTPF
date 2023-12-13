import json

types = set()
with open("robokop_nodes.jsonl","r") as inf:
    for line in inf:
        s = json.loads(line)
        type = s["category"][0]
        if type not in types:
            print(type, len(types))
            types.add(type)