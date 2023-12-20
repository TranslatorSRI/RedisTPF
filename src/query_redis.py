from src.keymaster import create_query_pattern

async def bquery(subjects, pq, objects, descender, rc):
    # Given a list of subject curies, a predicate/qualifier string, and a list of object curies,
    # return a list of TRAPI nodes and a list of trapi edges. If symmetric is true, then the
    # query is (subject, pq, object) or (object, pq, subject).  Otherwise, it is (subject, pq, object).
    # The strategy is to first figure out which of the subject or object curies is the smaller set.
    # TODO: can we constrain the object type from the TRAPI query? Or by looking at the objects?
    if len(subjects) < len(objects):
        return await oquery(subjects, pq, "biolink:NamedThing", descender, rc, objects)
    else:
        object_nodes, subject_nodes, edges =\
            await squery(objects, pq, "biolink:NamedThing", descender, rc, subjects)
        return subject_nodes, object_nodes, edges

async def oquery(subjects, pq, object_type, descender, rc, objects = None):
    # Given a list of subject curies, a predicate/qualifier string, and an object type, return a list of objects
    return await gquery(subjects, pq, object_type, True, descender, rc, objects)


async def squery(objects, pq, subject_type, descender, rc, subjects = None):
    return await gquery(objects, pq, subject_type, False, descender, rc, subjects)


async def gquery(input_curies, pq, output_type, input_is_subject, descender, rc, filter_curies = None):
    # Given a list of input curies, a predicate/qualifier string, and an output type, return a list of TRAPI
    # nodes and a list of trapi edges.
    # Optionally filter the output nodes by a list of curies (and their subclasses).
    # To do this, query the redis db, which has the following structure:
    # db0 contains a map from a text node id to an integer node_id.  The int node_id is defined
    #  by this code and is used to index into the other databases.
    # db1 contains a map from the integer node_id to a node.  The node is a json object.
    #  This db is used to pull the big string for the TRAPI response.
    # db2 contains a map from categories to an integer category_id.  This is used to save memory
    # db3: pq -> integer_id_for_pq (for saving mem in the other dbs)
    # db4: integer_edge_id -> edge (for pulling the big string for the TRAPI response)
    # A query pattern will be either (subject_int_id, pq_int_id, type_int_id) or
    #   (type_int_id, -pq_int_id, object_int_id).  The latter is for reverse edges.
    # db5: query_pattern -> interleaved list of integer_edge_ids and integer_node_ids
    #  In other words, [ edge_id, node_id, edge_id, node_id, ...]

    pipelines = rc.get_pipelines()

    input_int_ids = await rc.get_int_node_ids(input_curies)
    if filter_curies is not None:
        filter_int_ids = await rc.get_int_node_ids(filter_curies)

    # TODO: the int id for the pq and types should probably be cached somewhere, maybe in the Descender and
    #  looked up in redis at start time.

    # Get the int_id for the pq:
    pq_int_ids = await descender.get_pq_descendant_int_ids(pq)

    # Get the int_id for the output type and its descendants
    type_int_ids = await get_type_int_ids(descender, output_type, rc)

    # create_query_pattern
    iid_list = []
    query_patterns = []
    if input_is_subject:
        for type_int_id in type_int_ids:
            for pq_int_id in pq_int_ids:
                #Filter to the ones that are actually in the db
                if f"{pq_int_id},{type_int_id}" in descender.s_partial_patterns:
                    for iid in input_int_ids:
                        query_patterns.append(create_query_pattern(iid, pq_int_id, type_int_id))
                        iid_list.append(iid)
    else:
        for type_int_id in type_int_ids:
            for pq_int_id in pq_int_ids:
                #Filter to the ones that are actually in the db
                if f"{type_int_id},-{pq_int_id}" in descender.o_partial_patterns:
                    for iid in input_int_ids:
                        query_patterns.append(create_query_pattern(type_int_id, -pq_int_id, iid) )
                        iid_list.append(iid)
    # We need to make the iid_list in the same way as query_patterns so that we can
    # extract the iids that actually gave results to return them
    # iid_list = [iid for iid in input_int_ids for type_int_id in type_int_ids for pq_int_id in pq_int_ids]

    # Now, get the list of edge ids that match the query patterns
    results = await get_results_for_query_patterns(pipelines, query_patterns)
    # Keep the input_iids that returned results
    # This is kind of messy b/c you have to know if the iid is in the subject or object position of the query pattern
    input_int_ids = list(set([iid_list[i] for i in range(len(iid_list)) if len(results[i]) > 0]))
    # Flatten the list of lists into a single list:
    edge_and_outputnode_ids = [int(item) for sublist in results for item in sublist]
    # Deconvolve the edge ids from the output node ids
    edge_ids = edge_and_outputnode_ids[::2]
    output_node_ids = edge_and_outputnode_ids[1::2]

    if filter_curies is not None:
        # Now filter out the output nodes and associated edges that don't match the filter curies
        filtered_edge_ids = []
        filtered_output_node_ids = []
        for edge_id, output_node_id in zip(edge_ids, output_node_ids):
            if output_node_id in filter_int_ids:
                filtered_edge_ids.append(edge_id)
                filtered_output_node_ids.append(output_node_id)
        edge_ids = filtered_edge_ids
        output_node_ids = filtered_output_node_ids

    return await get_strings(input_int_ids, output_node_ids, edge_ids,rc)


async def get_results_for_query_patterns(pipelines, query_patterns):
    for qp in query_patterns:
        pipelines[5].lrange(qp, 0, -1)
    results = pipelines[5].execute()
    return results


async def get_type_int_ids(descender, output_type, rc):
    output_types = descender.get_type_descendants(output_type)
    res = await rc.pipeline_gets(2, output_types, True)
    type_int_ids = res.values()
    return type_int_ids




async def get_strings(input_int_ids, output_node_ids, edge_ids,rc):
    input_node_strings = rc.r[1].mget(set(input_int_ids))
    output_node_strings = rc.r[1].mget(set(output_node_ids))

    edge_strings = rc.r[4].mget(edge_ids)

    return input_node_strings, output_node_strings, edge_strings
