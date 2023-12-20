# Convenience class for loading biolink and coming up with all the descendants of pq and
# types.

from bmt import Toolkit
import jsonpickle
from collections import defaultdict

from src.keymaster import create_pq

class Descender:
    def __init__(self,rc = None):
        """Descender can be loaded from redis (r) or if no redis is provided, it will load from bmt.
        When we load from redis, we also pull in the s and o partial patterns which are used to filter at q time.
        If you are creating descender with an rc, you also need to call setup on it asynchronously."""
        if rc is not None:
            #db = rc.r[7]
            #self.pq_to_descendants = jsonpickle.decode(db.get("pq_to_descendants"))
            self.pq_to_descendants = None
            #self.type_to_descendants = jsonpickle.decode(db.get("type_to_descendants"))
            self.type_to_descendants = None
            #self.predicate_is_symmetric = jsonpickle.decode(db.get("predicate_symmetries"))
            self.predicate_is_symmetric = None
            #self.s_partial_patterns = jsonpickle.decode(db.get("s_partial_patterns"))
            self.s_partial_patterns = None
            #self.o_partial_patterns = jsonpickle.decode(db.get("o_partial_patterns"))
            self.o_partial_patterns = None
            self.pq_to_descendant_int_ids = None
            #Need to hang onto this b/c we are going to lazy load pq_to_descendant_int_ids.  Doing it here is a pain from an async perspective
            self.rc = rc
        else:
            self.t = Toolkit()
            self.type_to_descendants = self.create_type_to_descendants()
            self.pq_to_descendants = self.create_pq_to_descendants()
            self.predicate_is_symmetric = self.create_is_symmetric()
            self.deeptypescache = {}

    async def get_s_partial_patterns(self):
        if self.s_partial_patterns is None:
            self.s_partial_patterns = jsonpickle.decode(await self.rc.r[7].get("s_partial_patterns"))
        return self.s_partial_patterns

    async def get_o_partial_patterns(self):
        if self.o_partial_patterns is None:
            self.o_partial_patterns = jsonpickle.decode(await self.rc.r[7].get("o_partial_patterns"))
        return self.o_partial_patterns

    async def is_symmetric(self, predicate):
        if self.predicate_is_symmetric is None:
            self.predicate_is_symmetric = jsonpickle.decode(await self.rc.r[7].get("predicate_symmetries"))
        return self.predicate_is_symmetric[predicate]
    def create_is_symmetric(self):
        # Create a dictionary from predicate to whether it is symmetric
        # The symmetric nature of an edge is completely determined by the predicate.
        # I don't think it's possible for a symmetric predicate to be made asymmetric by the
        # addition of qualifiers.
        p_is_symmetric = {}
        for p in self.t.get_descendants('biolink:related_to',formatted=True):
            try:
                p_element = self.t.get_element(p)
                if p_element.symmetric is None:
                    p_is_symmetric[p] = False
                else:
                    p_is_symmetric[p] = p_element.symmetric
            except:
                print("Error 2 with predicte: " + p)
                pass
        return p_is_symmetric
    def create_type_to_descendants(self):
        # Create a dictionary from type to all of its descendants
        type_to_descendants = {}
        for t in self.t.get_descendants('biolink:NamedThing',formatted=True):
            try:
                type_to_descendants[t] = self.t.get_descendants(t,formatted=True)
            except:
                print("Error with type: " + t)
                pass
        return type_to_descendants
    #TODO: This doesn't handle mixins :(
    def create_pq_to_descendants(self):
        # Create a dictionary from pq to all of its descendants
        pq_to_descendants = {}
        for predicate in self.t.get_descendants("biolink:related_to", formatted=True):
            pq = create_pq({"predicate":predicate})
            try:
                pq_to_descendants[pq] = { create_pq({"predicate":p}) for p in self.t.get_descendants(predicate,formatted=True) }
            except:
                print("Error with predicate: " + pq)
                pass
        # Now, we don't handle the qualifiers.  BMT is not super helpful here.  bmt-lite is a bit better, but
        # still not great.  So, we'll just add the qualifiers we know about.  Fortunately, these only go onto
        # biolink:affects and biolink:regulates predicates.
        # We have 4 qualifiers: subject_aspect_qualifier, object_aspect_qualifier, subject_direction_qualifier, object_direction_qualifier
        # The direction qualifiers are goofy because they contain both the directions used in affects ("increased" and "decreased")
        #  as well as the directions used in regulates ("upregulated" and "downregulated"). So rather than get the mixed
        #  list out of BMT and spearate it out somehow dumb, we'll just construct it by hand.
        affects_directions = {"None": ["increased", "decreased"]}
        regulates_directions = {"None": ["upregulated", "downregulated"]}
        aspect_enums = self.t.get_element("GeneOrGeneProductOrChemicalEntityAspectEnum").permissible_values
        #We need to parse out the aspect tree into a dictionary of lists of aspects
        aspects = defaultdict(list)
        for aspect_key, aspect in aspect_enums.items():
            if aspect.is_a is None:
                aspects["None"].append(aspect_key)
            else:
                aspects[aspect.is_a].append(aspect_key)
        for predicate,predicate_directions,predicate_aspects in [("biolink:regulates", regulates_directions,{"None": []}),
                                                                 ("biolink:affects", affects_directions, aspects)]:
            decs = defaultdict(set)
            e = {"predicate": predicate}
            original_pk = create_pq(e)
            add_all_decs(e, predicate_directions, predicate_aspects, decs)
            # add_all_decs isn't fully redundant, need to make it so by adding grand descendants etc
            decs = redundantize_decs(decs, original_pk)
            for k,v in decs.items():
                pq_to_descendants[k] = v
            #Connect the new descendants to the ancestors of the original pq
            for k,v in pq_to_descendants.items():
                if original_pk in v:
                    pq_to_descendants[k].update(decs[original_pk])
        return pq_to_descendants
    async def get_type_descendants(self, t):
        if self.type_to_descendants is None:
            self.type_to_descendants = jsonpickle.decode(await self.rc.r[7].get("type_to_descendants"))
        return self.type_to_descendants[t]
    #async def get_pq_descendants(self, pq):
    #    try:
    #        if self.pq_to_descendants is None:
    #            self.pq_to_descendants = await self.create_pq_to_descendants(self.rc)
    #        return self.pq_to_descendants[pq]
    #    except:
    #        return [pq]
    async def create_pq_to_descendant_int_ids(self,rc):
        # Create a dictionary from pq to all of its descendant integer ids
        # First, pull the integer id for every pq
        # Lazy create pq_to_descendants by puling it from redis
        if self.pq_to_descendants is None:
            pkl = await self.rc.r[7].get("pq_to_descendants")
            self.pq_to_descendants = jsonpickle.decode(pkl)
        pql = list(self.pq_to_descendants.keys())
        pq_int_ids = await rc.pipeline_gets(3, pql, True)
        # now convert pq_to_descendants into int id values
        pq_to_descendant_int_ids = {}
        for pq in self.pq_to_descendants:
            descendants = self.pq_to_descendants[pq]
            pq_to_descendant_int_ids[pq] = set()
            for desc in descendants:
                # Not every possible descendant is in the database, and the point here is to filter it down to the ones that are.
                try:
                    pq_to_descendant_int_ids[pq].add(pq_int_ids[desc])
                except KeyError:
                    # This is totally expected
                    pass
        return pq_to_descendant_int_ids
    async def get_pq_descendant_int_ids(self, pq):
        if self.pq_to_descendant_int_ids is None:
            self.pq_to_descendant_int_ids = await self.create_pq_to_descendant_int_ids(self.rc)
        return self.pq_to_descendant_int_ids[pq]
    def get_deepest_types(self, typelist):
        """Given a list of types, examine self.type_to_descendants and return a list of the types
        from typelist that do not have a descendant in the list"""
        # Let's have a cache because we see the same lists over and over and hitting BMT is slow
        fs = frozenset(typelist)
        if fs in self.deeptypescache:
            return self.deeptypescache[fs]
        deepest_types = []
        for t in typelist:
            if t not in self.type_to_descendants:
                # This covers mixins
                # deepest_types.append(t)
                continue
            descendants = self.type_to_descendants[t]
            # 1 because the descendants include the type itself
            if len(set(typelist).intersection(descendants)) == 1:
                deepest_types.append(t)
        self.deeptypescache[fs] = deepest_types
        return deepest_types

def add_all_decs(edge, directions, aspects, decs):
    pq = create_pq(edge)
    decs[pq].add(pq) # We're going to get the pq by looking at the decendent list so we want pq itself
    next_children = get_decs(edge, directions, aspects)
    for child in next_children:
        child_pq = create_pq(child)
        decs[pq].add(child_pq)
        add_all_decs(child, directions, aspects, decs)

def get_decs(edge, directions, aspects):
    # Given an edge, a dictionary of directions, and a dictionary of aspects, return a list of all
    # possible edges that could be created from the edge by going one level deeper on either a direction or an aspect.
    # The directions and aspect dictionaries represent subclasses.  The key is the parent class and the value is a list
    # of subclasses.  The root class is represented by the key "None", because in the top level predicate, there
    # will not be that qualifier.  There are 4 qualifiers that can be added to each edge: "subject_aspect_qualifier",
    # "object_aspect_qualifier", "subject_direction_qualifier", "object_direction_qualifier".

    new_qualifier_dict= {}
    for qualifier_name, qualifier_dict in [("biolink:subject_aspect_qualifier",aspects),
                                           ("biolink:object_aspect_qualifier", aspects),
                                           ("biolink:subject_direction_qualifier", directions),
                                           ("biolink:object_direction_qualifier", directions)]:
        if qualifier_name in edge:
            qualifier = edge[qualifier_name]
        else:
            qualifier = "None"
        try:
            possible_qualifiers = qualifier_dict[qualifier]
        except KeyError:
            # We hit the bottom of the list
            continue
        new_qualifier_dict[qualifier_name] = possible_qualifiers

    new_edges = []
    for qualifier_name in ["biolink:subject_aspect_qualifier", "biolink:object_aspect_qualifier",
                           "biolink:subject_direction_qualifier", "biolink:object_direction_qualifier"]:
        if qualifier_name not in new_qualifier_dict:
            continue
        for qualifier in new_qualifier_dict[qualifier_name]:
            new_edge = edge.copy()
            new_edge[qualifier_name] = qualifier
            new_edges.append(new_edge)

    return new_edges

def redundantize_decs(decs, root, processed=None):
    # given a dictionary from a member to a set of immediate descendants d, and a root node, return a dictionary
    # from the member to a set of all descendants. Note that a member is a descendent of itself.
    # For instance, if decs is {a: {a,b,c}, b: {b,d}, c: {c,e}, d:{d}, e:{e}}, then the return value will be
    # {a: {a,b,c,d,e}, b: {b,d}, c: {c,e}, d:{d}, e:{e}}.
    # This is a recursive function.  It returns a dictionary.
    # The base case is when the root is not in the dictionary.  In this case, we return the dictionary.
    # The recursive case is when the root is in the dictionary.  In this case, we add the descendants of the
    # root to the root's descendants, and then call the function on the root's descendants.
    # Note that this function is not efficient.  It is O(n^2) in the number of edges.  However, we don't expect
    # the number of edges to be very large, so this should be fine.
    if processed is None:
        processed = set()

    # If the root has been processed or is not in decs, return an empty dict
    if root in processed or root not in decs:
        return {}

    # Add root to processed set
    processed.add(root)

    # Copy the immediate descendants to avoid modifying the input dictionary
    all_descendants = set(decs[root])

    # Iterate over a copy of the immediate descendants
    for dec in decs[root].copy():
        if dec not in processed:
            # Recursively get all descendants of the current descendant
            dec_descendants = redundantize_decs(decs, dec, processed)
            # Update the all_descendants set
            all_descendants.update(dec_descendants[dec])

    # Update the decs dictionary for the root
    decs[root] = all_descendants

    return decs



if __name__ == "__main__":
    descender = Descender()
    print(len(descender.type_to_descendants))
    print(len(descender.pq_to_descendants))
    print(descender.type_to_descendants['biolink:NamedThing'])
    print(descender.pq_to_descendants[create_pq({"predicate":'biolink:related_to'})])
