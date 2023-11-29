# This assumes that you have a redis server running on localhost:6379 and that you have run
# python src/load_redis.py nodes.jsonl edges.jsonl 127.0.0.1 6379 nop
# Where nodes.jsonl and edges.jsonl are from gtopdb

from src.redis_connector import RedisConnection
from src.keymaster import create_pq
from src.query_redis import squery, oquery


def run_test():
    # Here's the edge:
    edge= {"subject":"PUBCHEM.COMPOUND:70701426","predicate":"biolink:affects","object":"NCBIGene:239",
     "biolink:primary_knowledge_source":"infores:gtopdb","primaryTarget":True,"affinityParameter":"pIC50",
     "endogenous":False,"affinity":6.46999979019165,"publications":["PMID:24393039"],
     "object_aspect_qualifier":"activity","object_direction_qualifier":"decreased",
     "qualified_predicate":"biolink:causes"}
    subject_id = edge['subject']
    object_type = "biolink:Gene"
    pq = create_pq(edge)

    rc = RedisConnection("localhost", 6379, "nop")
    input_nodes, output_nodes, edges= oquery([subject_id], pq, object_type, rc)
    print(len(input_nodes))
    print(len(output_nodes))
    print(len(edges))
    print(output_nodes[0])


if __name__ == "__main__":
    run_test()
