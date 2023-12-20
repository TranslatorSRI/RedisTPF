import json

def create_pq(record):
    # Given an edge json record, create a string that represents the predicate and qualifiers
    # it needs to be created such that the order is specified - even if the input qualifiers are in a different
    # order, the string should be the same.
    pq = {"predicate":record['predicate']}
    # If the qualifiers are in the record, use them.  Otherwise, look for the _qualifier fields
    if "qualifiers" in record:
        for qualifier in record["qualifiers"]:
            pq[qualifier["qualifier_type_id"]] = qualifier["qualifier_value"]
    else:
        for propname, propval in record.items():
            if propname.endswith("_qualifier"):
                pq[propname] = propval
    # THis has to be json instead of orjson because we need to sort the keys
    return json.dumps(pq, sort_keys=True)

def create_trapi_pq(trapi_edge):
    # Given a trapi edge, create a string that represents the predicate and qualifiers
    # We need to transform the way trapi qualifiers are represented into the way that
    # they are represented in jsonl
    # TODO: Handle multiple predicates
    new_edge = {"predicate":trapi_edge['predicates'][0]}
    if ("qualifier_constraints" in trapi_edge) and (len(trapi_edge["qualifier_constraints"]) > 0):
        if len(trapi_edge["qualifier_constraints"]) > 1:
            raise ValueError("I don't know how to handle more than one qualifier constraint")
        qualifier_set = trapi_edge["qualifier_constraints"][0]["qualifier_set"]
        for qualifier in qualifier_set:
            new_edge[qualifier["qualifier_type_id"]] = qualifier["qualifier_value"]
    return create_pq(new_edge)

def create_query_pattern(s_int, pq_int, o_int):
    return f"{s_int},{pq_int},{o_int}"
