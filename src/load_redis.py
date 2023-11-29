# Given KGX jsonl files, load them into Redis
# Usage: python load_redis.py <path_to_kgx_jsonl_files> <redis_host> <redis_port> <redis_password>

import argparse
import json
from collections import defaultdict

from redis_connector import RedisConnection
from keymaster import create_pq, create_query_pattern
from descender import Descender

def fixnode(node):
    # The jsonl nodes don't validate TRAPI.   There are several problems:
    # 1. We call it "category" instead of "categories"
    # 2. We have an "id" in the node, there should not be one
    # 3. All the properties _except_ category and name should be in an "attributes" object
    # The node is a dictionary.  We will fix it in place
    # 1. Change "category" to "categories"
    node["categories"] = node["category"]
    del node["category"]
    # 2. We could delete the node id.  But this is tough because the maps in the redis db are based on
    # an index rather than the node ids.  So reconstructing the ids is hard.  We will leave ID on the
    # node and remove it at query time
    # del node["id"]
    # 3. Move all the properties except category and name into an "attributes" object
    attributes = []
    for k,v in node.items():
        if k not in ["categories", "name",  "id"]:
            attributes.append({"attribute_type_id":k, "value": v})
    node["attributes"] = attributes
    for a in attributes:
        k  = a["attribute_type_id"]
        del node[k]

def fixedge(edge):
    # The jsonl edges don't validate TRAPI.   There are several problems:
    # 1. The jsonl edges don't have "biolink" on the qualifiers.
    # 2. The jsonl properties are attached directly to the edge rather than being in an "attributes" object
    new_edge = {"attributes": [], "qualifiers": [], "sources": []}
    for k,v in edge.items():
        if k in ["subject", "predicate", "object"]:
            new_edge[k] = v
        elif k.endswith("_qualifier"):
            new_edge["qualifiers"].append({"qualifier_type_id":"biolink:"+k, "qualifier_value": v})
        elif k == "biolink:primary_knowledge_source":
            new_edge["sources"].append({"resource_role": "primary_knowledge_source", "resource_id": v})
        else:
            new_edge["attributes"].append({"attribute_type_id":k, "value": v})
    return new_edge


def load_nodes(nodepath, host, port, password):
    # Load jsonl files into Redis
    # The redis database is structured as follows:
    # db0 contains a map from a text node id to an integer node_id.  The int node_id is defined
    #  by this code and is used to index into the other databases.
    # db1 contains a map from the integer node_id to a node.  The node is a json object.
    #  This db is used to pull the big string for the TRAPI response.
    # db2 contains a map from categories to an integer category_id.  This is used to save memory
    # As we parse the nodes, we also want to extract the biolink category for each one and
    #  create a dictionary from (original) node_id to category.  We also need to keep a dictionary
    #  in python with the node_id->integer node id mapping.  We will use this to create the edges.

    descender = Descender()

    with RedisConnection(host, port, password) as rc:
        pipelines = rc.get_pipelines()

        nodeid_to_categories = defaultdict(list)
        nodeid_to_intnodeid = {}
        categories_to_id = {}

        last_node_id = 0

        # for loading performance, we want to pipeline the loads
        with open(nodepath) as f:
            for line in f:
                record = json.loads(line)
                record_id = record['id']
                fixnode(record)
                last_node_id += 1
                # We need to look for conflated things like gene/protein. It will have multiple categories
                categories = descender.get_deepest_types(record['categories'])
                for category in categories:
                    if category not in categories_to_id:
                        category_id = len(categories_to_id)
                        categories_to_id[category] = category_id
                    category_id = categories_to_id[category]
                    pipelines[2].set(category, category_id)
                    nodeid_to_categories[last_node_id].append(categories_to_id[category])
                nodeid_to_intnodeid[record_id] = last_node_id
                pipelines[0].set(record_id, last_node_id)
                pipelines[1].set(last_node_id, json.dumps(record))
                if last_node_id % 10000 == 0:
                    print("Node", last_node_id)
                    rc.flush_pipelines()
    return nodeid_to_categories, nodeid_to_intnodeid


def load_edges(edgepath, nodeid_to_categories, nodeid_to_intnodeid, host, port, password):
    # Load an edge jsonl into redis.  Edges are specified for query by a combination of
    #  predicate and qualifiers, denoted pq.   The databases are structured as:
    # db3: pq -> integer_id_for_pq (for saving mem in the other dbs)
    # db4: integer_edge_id -> edge (for pulling the big string for the TRAPI response)
    # A query pattern will be either (subject_int_id, pq_int_id, type_int_id) or
    #   (type_int_id, -pq_int_id, object_int_id).  The latter is for reverse edges.
    # db5: query_pattern -> list of integer_edge_ids
    # db6: int_node_id -> list of subclass integer_node_ids

    with RedisConnection(host, port, password) as rc:
        pipelines = rc.get_pipelines()

        last_edge_id = 0
        pq_to_intpq = {}

        # read the file
        with open(edgepath) as f:
            for line in f:
                record = json.loads(line)
                fixed_record = fixedge(record)
                last_edge_id += 1
                s_int = nodeid_to_intnodeid[record['subject']]
                o_int = nodeid_to_intnodeid[record['object']]
                # Handle subclass of edges differently.
                if record["predicate"] == "biolink:subclass_of":
                    if s_int != o_int:
                        # Eat the self subclasses
                        pipelines[6].rpush(o_int, s_int)
                else:
                    pq = create_pq(fixed_record)
                    if pq not in pq_to_intpq:
                        # We can't start at 0 because we are going to use negative numbers to indicate the opposite direction
                        pq_intid = len(pq_to_intpq) + 1
                        pq_to_intpq[pq] = pq_intid
                        pipelines[3].set(pq, pq_intid)
                    pq_intid = pq_to_intpq[pq]
                    pipelines[4].set(last_edge_id, json.dumps(fixed_record))
                    s_cat_ints = nodeid_to_categories[s_int]
                    o_cat_ints = nodeid_to_categories[o_int]
                    for s_cat_int in s_cat_ints:
                        for o_cat_int in o_cat_ints:
                            spattern = create_query_pattern(s_int, pq_intid, o_cat_int)
                            opattern = create_query_pattern(s_cat_int, -pq_intid, o_int)
                            pipelines[5].rpush(spattern, last_edge_id)
                            pipelines[5].rpush(spattern, o_int)
                            pipelines[5].rpush(opattern, last_edge_id)
                            pipelines[5].rpush(opattern, s_int)
                if last_edge_id % 10000 == 0:
                    print("Edge", last_edge_id)
                    rc.flush_pipelines()


def load(nodepath, edgepath, host, port, password):
    nodeid_to_categories, nodeid_to_intnodeid = load_nodes(nodepath, host, port, password)
    load_edges(edgepath, nodeid_to_categories, nodeid_to_intnodeid, host, port, password)


if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Load KGX jsonl files into Redis')
    parser.add_argument('nodepath', help='path to KGX jsonl node file')
    parser.add_argument('edgepath', help='path to KGX jsonl edge file')
    parser.add_argument('host', help='Redis host')
    parser.add_argument('port', help='Redis port')
    parser.add_argument('password', help='Redis password')
    args = parser.parse_args()
    load(args.nodepath, args.edgepath,  args.host, args.port, args.password)
