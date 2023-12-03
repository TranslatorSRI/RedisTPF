from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from reasoner_pydantic import Response as PDResponse, Result as PDResult, Analysis as PDAnalysis, KnowledgeGraph as PDKG
from src.redis_connector import RedisConnection
from src.descender import Descender
from src.keymaster import create_trapi_pq
from src.query_redis import squery, oquery, bquery

import json

RTPF_VERSION = '0.0.1'

APP = FastAPI(
    title='TRAPI Pattern Fragment Server',
    version=RTPF_VERSION
)

APP.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

descender = Descender()
rc = RedisConnection("localhost", 6379, "nop")


@APP.post("/query", tags=["Query"], response_model=PDResponse, response_model_exclude_none=True, status_code=200)
async def query_handler(request: PDResponse):
    """ Query operations. """
    dict_request = request.to_dict()
    # Check the query graph for basic validity
    query_graph = dict_request['message']['query_graph']
    if len(query_graph['edges']) != 1:
        raise ValueError("Only one edge is supported")
    if len(query_graph['nodes']) != 2:
        raise ValueError("Only two nodes are supported")

    # Get the pq
    query_edge = list(query_graph['edges'].keys())[0]
    pq = create_trapi_pq(list(query_graph['edges'].values())[0])

    # Figure out if this is (subject, get object) or (object, get subject)
    subject_query_node = query_graph["edges"][query_edge]["subject"]
    object_query_node = query_graph["edges"][query_edge]["object"]
    subject_node = query_graph["nodes"][subject_query_node]
    object_node = query_graph["nodes"][object_query_node]

    # Initialize reverse edges
    input_nodes_r = []
    output_nodes_r = []
    edges_r = []
    q_pred = list(query_graph['edges'].values())[0]["predicates"][0]

    # Do the query
    if "ids" in subject_node and "ids" in object_node:
        subject_curies = subject_node["ids"]
        object_curies = object_node["ids"]
        input_nodes, output_nodes, edges = bquery(subject_curies, pq, object_curies, descender, rc)
        # TODO: this is an opportunity for speedup because there is some duplicated work here.
        if descender.is_symmetric(q_pred):
            output_nodes_r, input_nodes_r, edges_r = bquery(object_curies, pq, subject_curies, descender, rc)
    elif "ids" in subject_node:
        subject_curies = subject_node["ids"]
        input_nodes, output_nodes, edges = oquery(subject_curies, pq, object_node["categories"][0], descender, rc)
        if descender.is_symmetric(q_pred):
            output_nodes_r, input_nodes_r, edges_r = squery(subject_curies, pq, object_node["categories"][0], descender, rc)
    else:
        object_curies = object_node["ids"]
        input_nodes, output_nodes, edges = squery(object_curies, pq, subject_node["categories"][0], descender, rc)
        if descender.is_symmetric(q_pred):
            output_nodes_r, input_nodes_r, edges_r = oquery(object_curies, pq, subject_node["categories"][0], descender, rc)

    # Merge the results, but we need to worry about duplicating nodes.  The edges are by construction
    # pointing in the opposite directions, so there should be no overlap there.
    if len(edges_r) > 0:
        input_nodes = list(set(input_nodes + input_nodes_r))
        output_nodes = list(set(output_nodes + output_nodes_r))
        # Don't just merge the edge lists. We need to know which ones are pointing in the
        # opposite direction so that we can create the correct node_bindings
        # edges.extend(edges_r)

    # Create edge identifiers
    for eid, edge in enumerate(edges):
        print(type(json.loads(edge)))
        print(edge)
    edge_id_to_edge = { f"knowledge_edge_{i}":json.loads(edge) for i, edge in enumerate(edges)}
    # These edges are the ones that are going the same direction as the query
    forward_edge_ids = set(edge_id_to_edge.keys())
    # Now add the reverse edges. Make sure not to overwrite ids
    edge_id_to_edge.update({ f"knowledge_edge_{i+len(edges)}":json.loads(edge) for i, edge in enumerate(edges_r)})

    # Create the response
    dict_request["message"]["knowledge_graph"] ={"nodes":{}, "edges":{}}
    dict_request["message"]["results"] = []
    response = PDResponse(message=dict_request['message'])

    # KG Nodes
    for nodelist in (input_nodes, output_nodes):
        for node in nodelist:
            # The node id is on the node in the redis, but it's invalid TRAPI to have it there, so we remove it
            # now.  We could have removed it at load time, but then it's hard to recover because of the way that
            # we are indexing.
            jnode = json.loads(node)
            nid = jnode["id"]
            del jnode["id"]
            response.message.knowledge_graph.nodes[nid] = jnode

    # KG Edges
    response.message.knowledge_graph.edges = edge_id_to_edge

    # Results
    # Each edge is going to generate a result
    response.message.results = []
    for edge_id, edge in edge_id_to_edge.items():
        analysis = PDAnalysis(resource_id="infores:test", edge_bindings={query_edge: [{"id":edge_id}]})
        if edge_id in forward_edge_ids:
            result = PDResult(analyses=[analysis], node_bindings={subject_query_node:[{"id":edge["subject"]}],
                                                              object_query_node:[{"id":edge["object"]}]})
        else:
            result = PDResult(analyses=[analysis], node_bindings={subject_query_node:[{"id":edge["object"]}],
                                                              object_query_node:[{"id":edge["subject"]}]})
        response.message.results.append(result)

    return response

import uvicorn
if __name__ == "__main__":
    uvicorn.run(APP, host="0.0.0.0", port=8000)