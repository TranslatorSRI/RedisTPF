# This assumes that you have a redis server running on localhost:6379 and that you have run
# python src/load_redis.py nodes.jsonl edges.jsonl 127.0.0.1 6379 nop
# Where nodes.jsonl and edges.jsonl are from gtopdb

import json

import pytest

from copy import deepcopy
from fastapi.testclient import TestClient
from src.server import APP

client = TestClient(APP)

def test_simple_queries():
    # Given the edge defined in run_basic_tests, query for it by subject and object with exacty the
    # edge's types and predicate
    run_basic_tests()


def test_profile_asthma():
    # This query assumes that robokop-KG is loaded into redis.
    query_graph = {
      "message": {
        "query_graph": {
          "nodes": {
            "subnode": {
              "ids": [
                "MONDO:0004979"
              ]
            },
            "objnode": {
              "categories": [
                "biolink:NamedThing"
              ]
            }
          },
          "edges": {
            "the_edge": {
              "subject": "subnode",
              "object": "objnode",
              "predicates": [
                "biolink:related_to"
              ]
            }
          }
        }
      }
    }

    response = client.post("/query", json= query_graph).json()
    print("How many results?",len(response["message"]["results"]))

def test_affects():
    m = {
      "message": {
        "query_graph": {
          "nodes": {
            "subnode": {
              "ids": [
                "PUBCHEM.COMPOUND:70701426"
              ]
            },
            "objnode": {
              "categories": [
                "biolink:Gene"
              ]
            }
          },
          "edges": {
            "the_edge": {
              "subject": "subnode",
              "object": "objnode",
              "predicates": [
                "biolink:affects"
              ],
              "qualifier_constraints": [
                {
                  "qualifier_set": [
                    {
                      "qualifier_type_id": "biolink:object_aspect_qualifier",
                      "qualifier_value": "activity"
                    },
                    {
                      "qualifier_type_id": "biolink:object_direction_qualifier",
                      "qualifier_value": "decreased"
                    }
                  ]
                }
              ]
            }
          }
        }
      }
    }
    response = client.post("/query", json=m)
    print("How many results?",len(response.json()["message"]["results"]))
    assert response.status_code == 200

def test_500():
    # This is giving a 500, seems like it's getting into the double ended query by mistake.
    m = {
      "message": {
        "query_graph": {
          "nodes": {
            "chemical": {
              "categories": ["biolink:ChemicalEntity"],
              "is_set": False,
              "constraints": []
            },
            "f": {
              "ids": ["MONDO:0005737"],
              "is_set": False,
              "constraints": []
            }
          },
          "edges": {
            "edge_1": {
              "subject": "chemical",
              "object": "f",
              "predicates": ["biolink:treats"],
              "attribute_constraints": [],
              "qualifier_constraints": []
            }
          }
        }
      }
    }
    response = client.post("/query", json=m)
    assert response.status_code == 200

def xtest_type_descendant_queries(rc, descender):
    # Given the edge defined in run_basic_tests, query for it by subject and object with super types
    run_basic_tests(rc, descender, subject_type = "biolink:NamedThing", object_type = "biolink:NamedThing")


def xtest_pq_descendant_queries(rc, descender):
    # Given the edge defined in run_basic_tests, query for it by subject and object with super types
    run_basic_tests(rc, descender, pq = create_pq({"predicate": "biolink:related_to"}))

def xtest_subclass(rc,descender):
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


def xtest_no_results_query(rc, descender):
    # Make sure that queries with no results don't crash
    input_nodes, output_nodes, edges= oquery(["FAKE:ID"], create_pq({"predicate": "biolink:related_to"}),
                                             "biolink:NamedThing", descender, rc)
    assert len(input_nodes) == 0
    assert len(output_nodes) == 0
    assert len(edges) == 0

def run_basic_tests(subject_type=None, object_type=None, pq=None):
    # Here's an edge.  That subject and object only appear once in the input data:
    edge= {"subject":"PUBCHEM.COMPOUND:70701426","predicate":"biolink:affects","object":"NCBIGene:239",
     "biolink:primary_knowledge_source":"infores:gtopdb","primaryTarget":True,"affinityParameter":"pIC50",
     "endogenous":False,"affinity":6.46999979019165,"publications":["PMID:24393039"],
     "object_aspect_qualifier":"activity","object_direction_qualifier":"decreased",
     "qualified_predicate":"biolink:causes"}

    query_graph = {"nodes": {"subnode": {}, "objnode": {}},
                   "edges": {"the_edge": {"subject": "subnode", "object": "objnode"}}}

    if pq is None:
        query_graph["edges"]["the_edge"]["predicates"] = [edge["predicate"]]
        query_graph["edges"]["the_edge"]["qualifier_constraints"]= [
            {
                "qualifier_set": [
                    {
                        "qualifier_type_id": "biolink:object_aspect_qualifier",
                        "qualifier_value": "activity"
                    },
                    {
                        "qualifier_type_id": "biolink:object_direction_qualifier",
                        "qualifier_value": "decreased"
                    }
                ]
            }
        ]

    subject_id = edge['subject']
    object_id = edge['object']
    if subject_type is None:
        subject_type = "biolink:SmallMolecule"
    if object_type is None:
        object_type = "biolink:Gene"

    tquery = deepcopy(query_graph)
    tquery["nodes"]["subnode"]["ids"] = [subject_id]
    tquery["nodes"]["objnode"]["categories"] = [object_type]
    response = client.post("/query", json={"message": {"query_graph": tquery}}).json()
    KG = response["message"]["knowledge_graph"]
    assert len(KG["nodes"]) == 2
    assert object_id in KG["nodes"]
    assert subject_id in KG["nodes"]
    assert len(KG["edges"]) == 1
    assert len(response["message"]["results"]) == 1
    assert response["message"]["results"][0]["node_bindings"]["subnode"][0]["id"] == subject_id
    assert response["message"]["results"][0]["node_bindings"]["objnode"][0]["id"] == object_id
    assert response["message"]["results"][0]["analyses"][0]["edge_bindings"]["the_edge"][0]["id"] in KG["edges"]

    #input_nodes, output_nodes, edges= squery([object_id], pq, subject_type, descender, rc)
    #assert len(input_nodes) == 1
    #assert len(output_nodes) == 1
    #node = output_nodes[0]
    #assert json.loads(node)["id"] == subject_id
    #assert len(edges) == 1
