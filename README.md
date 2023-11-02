# RedisTPF
Experimental Implementation of Redis-based TRAPI Pattern Fragments

Within a federated querying system, a large query is often broken down into single-hop queries to be sent to one of the underlying data sources.   If this underlying data source is configured to handle larger graph patterns (as is the case e.g. for RedisGraph and probably Neo4j), then it may have poor performance on single hops, as well as being potentially memory inefficient.

In RDF/SPARQL there is a technology called Triple Pattern Fragments that only handles single-triple queries rather than full SPARQL.  While the goal of TPF is less about performance and more about moving computation to the client, it and its frequent backing technology (HDT files) inspires the ideas explored here.

This is a redis-based version of a TPF server, but now the T stands for TRAPI.  We will also implement a version that uses an HDT file and RDF/TPF server for comparison.
