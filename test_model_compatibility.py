"""Test that UniProt and STRING-DB use the same Pydantic models."""

import sys


def test_model_compatibility():
    """Verify both clients use the same model classes."""
    
    print("\n" + "="*60)
    print("Testing Model Compatibility")
    print("="*60)
    
    # Import models from both clients
    from app.uniprot_client import (
        ProteinFeature as UniProtFeature,
        GOTerm as UniProtGOTerm,
        GOTermsByDomain as UniProtGOTermsByDomain,
        ProteinFeatureData as UniProtFeatureData,
        ProteinFeaturesResponse as UniProtResponse,
    )
    
    from app.stringdb_client import (
        ProteinFeature as StringDBFeature,
        GOTerm as StringDBGOTerm,
        GOTermsByDomain as StringDBGOTermsByDomain,
        ProteinFeatureData as StringDBFeatureData,
    )
    
    # Check if they're the same classes
    tests = [
        ("ProteinFeature", UniProtFeature, StringDBFeature),
        ("GOTerm", UniProtGOTerm, StringDBGOTerm),
        ("GOTermsByDomain", UniProtGOTermsByDomain, StringDBGOTermsByDomain),
        ("ProteinFeatureData", UniProtFeatureData, StringDBFeatureData),
    ]
    
    all_pass = True
    for name, uniprot_cls, stringdb_cls in tests:
        if uniprot_cls is stringdb_cls:
            print(f"✓ {name}: Same class (id: {id(uniprot_cls)})")
        else:
            print(f"✗ {name}: Different classes!")
            print(f"  UniProt: {uniprot_cls} (id: {id(uniprot_cls)})")
            print(f"  StringDB: {stringdb_cls} (id: {id(stringdb_cls)})")
            all_pass = False
    
    print("\n" + "="*60)
    if all_pass:
        print("✓ All models are compatible!")
        print("="*60 + "\n")
        return True
    else:
        print("✗ Model compatibility issues found!")
        print("="*60 + "\n")
        return False


if __name__ == "__main__":
    success = test_model_compatibility()
    sys.exit(0 if success else 1)
