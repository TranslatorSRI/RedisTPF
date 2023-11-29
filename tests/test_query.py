# This assumes that you have a redis server running on localhost:6379 and that you have run
# python src/load_redis.py nodes.jsonl edges.jsonl 127.0.0.1 6379 nop
# Where nodes.jsonl and edges.jsonl are from gtopdb

import json

import pytest

from src.redis_connector import RedisConnection
from src.keymaster import create_pq
from src.query_redis import squery, oquery
from src.descender import Descender

# TODO : make rc, Desc into fixtures
@pytest.fixture(scope="module")
def rc():
    return RedisConnection("localhost", 6379, "nop")

@pytest.fixture(scope="module")
def descender():
    return Descender()

def test_simple_queries(rc, descender):
    # Given the edge defined in run_basic_tests, query for it by subject and object with exacty the
    # edge's types and predicate
    run_basic_tests(rc, descender)


def test_type_descendant_queries(rc, descender):
    # Given the edge defined in run_basic_tests, query for it by subject and object with super types
    run_basic_tests(rc, descender, subject_type = "biolink:NamedThing", object_type = "biolink:NamedThing")


def test_pq_descendant_queries(rc, descender):
    # Given the edge defined in run_basic_tests, query for it by subject and object with super types
    run_basic_tests(rc, descender, pq = create_pq({"predicate": "biolink:related_to"}))

def test_subclass(rc,descender):
    # The following edges exist:
    # {"subject":"PUBCHEM.COMPOUND:54454","predicate":"biolink:affects","object":"NCBIGene:3156","biolink:primary_knowledge_source":"infores:gtopdb","primaryTarget":true,"affinityParameter":"pIC50","endogenous":false,"affinity":7.920000076293945,"publications":["PMID:1433193","PMID:11349148"],"object_aspect_qualifier":"activity","object_direction_qualifier":"decreased","qualified_predicate":"biolink:causes"}
    # {"subject":"PUBCHEM.COMPOUND:54687","predicate":"biolink:affects","object":"NCBIGene:3156","biolink:primary_knowledge_source":"infores:gtopdb","primaryTarget":true,"affinityParameter":"pKi","endogenous":false,"affinity":6.989999771118164,"publications":["PMID:11392538","PMID:16128575","PMID:1597859"],"object_aspect_qualifier":"activity","object_direction_qualifier":"decreased","qualified_predicate":"biolink:causes"}
    # {"subject":"PUBCHEM.COMPOUND:54687","predicate":"biolink:subclass_of","object":"CHEBI:87633","biolink:primary_knowledge_source":"infores:sri-ontology"}
    # {"subject":"PUBCHEM.COMPOUND:54454","predicate":"biolink:subclass_of","object":"CHEBI:87633","biolink:primary_knowledge_source":"infores:sri-ontology"}
    # The two pubchem compounds are the only subclasses of CHEBI:87633 and both decrease the activity of NCBIGene:3156.
    # These are the only edges for those compounds (other than subclass edges)
    # So the query (CHEBI:87633, biolink:affects, biolink:Gene) should return both compounds, NCBI:3156, and the two edges with qualifiers
    input_nodes, output_nodes, edges = oquery(["CHEBI:87633"], create_pq({"predicate": "biolink:affects"}),
                                                "biolink:Gene", descender, rc)
    assert len(input_nodes) == 2
    assert len(output_nodes) == 1
    assert len(edges) == 2

    returned_nodes = set([json.loads(node)["id"] for node in input_nodes])
    assert "PUBCHEM.COMPOUND:54454" in returned_nodes
    assert "PUBCHEM.COMPOUND:54687" in returned_nodes
    assert json.loads(output_nodes[0])["id"] == "NCBIGene:3156"


def test_no_results_query(rc, descender):
    # Make sure that queries with no results don't crash
    input_nodes, output_nodes, edges= oquery(["FAKE:ID"], create_pq({"predicate": "biolink:related_to"}),
                                             "biolink:NamedThing", descender, rc)
    assert len(input_nodes) == 0
    assert len(output_nodes) == 0
    assert len(edges) == 0

def run_basic_tests(rc, descender, subject_type=None, object_type=None, pq=None):
    # Here's an edge.  That subject and object only appear once in the input data:
    edge= {"subject":"PUBCHEM.COMPOUND:70701426","predicate":"biolink:affects","object":"NCBIGene:239",
     "biolink:primary_knowledge_source":"infores:gtopdb","primaryTarget":True,"affinityParameter":"pIC50",
     "endogenous":False,"affinity":6.46999979019165,"publications":["PMID:24393039"],
     "biolink:object_aspect_qualifier":"activity","biolink:object_direction_qualifier":"decreased",
     "qualified_predicate":"biolink:causes"}

    subject_id = edge['subject']
    object_id = edge['object']
    if subject_type is None:
        subject_type = "biolink:SmallMolecule"
    if object_type is None:
        object_type = "biolink:Gene"
    if pq is None:
        pq = create_pq(edge)

    input_nodes, output_nodes, edges= oquery([subject_id], pq, object_type, descender, rc)
    assert len(input_nodes) == 1
    assert len(output_nodes) == 1
    node = output_nodes[0]
    assert json.loads(node)["id"] == object_id
    assert len(edges) == 1

    input_nodes, output_nodes, edges= squery([object_id], pq, subject_type, descender, rc)
    assert len(input_nodes) == 1
    assert len(output_nodes) == 1
    node = output_nodes[0]
    assert json.loads(node)["id"] == subject_id
    assert len(edges) == 1

