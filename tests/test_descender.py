import pytest
from src.descender import Descender
def test_deepest_types():
    dec = Descender()
    # Find Gene in a haystack
    typelist = ["biolink:MacromolecularMachineMixin","biolink:GenomicEntity","biolink:PhysicalEssenceOrOccurrent","biolink:Gene","biolink:BiologicalEntity","biolink:ChemicalEntityOrGeneOrGeneProduct","biolink:Entity","biolink:OntologyClass","biolink:GeneOrGeneProduct","biolink:ThingWithTaxon","biolink:NamedThing","biolink:PhysicalEssence"]
    assert dec.get_deepest_types(typelist) == ["biolink:Gene"]
    # Find when there are multiple deepest types
    typelist = ["biolink:MacromolecularMachineMixin","biolink:GenomicEntity","biolink:PhysicalEssenceOrOccurrent","biolink:Gene","biolink:Protein","biolink:BiologicalEntity","biolink:Polypeptide","biolink:ChemicalEntityOrGeneOrGeneProduct","biolink:ChemicalEntityOrProteinOrPolypeptide","biolink:Entity","biolink:OntologyClass","biolink:GeneOrGeneProduct","biolink:ThingWithTaxon","biolink:NamedThing","biolink:GeneProductMixin","biolink:PhysicalEssence"]
    assert dec.get_deepest_types(typelist) == ["biolink:Gene", "biolink:Protein"]

