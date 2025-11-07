# UniProt Features Guide

## Overview

The protein comparison feature now fetches **comprehensive feature annotations** from the UniProt REST API, including structural, functional, and post-translational modification data.

## API Used

**UniProt REST API**: `https://rest.uniprot.org/uniprotkb`

UniProt (Universal Protein Resource) is the world's leading high-quality, comprehensive resource for protein sequence and functional information.

## Feature Types Fetched

### Structural Domains and Regions
- **Domain**: Specific combination of secondary structures organized into a characteristic three-dimensional structure
- **Region**: Region of interest in the sequence (e.g., "Disordered", "Low complexity")
- **Topological domain**: Location of non-membrane regions of membrane-spanning proteins
- **Zinc finger**: Small protein structural motif characterized by coordination of zinc ions

### Sequence Motifs and Repeats
- **Motif**: Short sequence motif of biological significance
- **Repeat**: Repeated sequence motifs or repeated domains
- **Compositional bias**: Region of compositional bias in the protein sequence

### Binding Sites
- **Binding site**: Binding site for any chemical group (co-enzyme, prosthetic group, etc.)
- **Active site**: Amino acid(s) directly involved in the activity of an enzyme
- **Metal binding**: Binding site for a metal ion
- **Nucleotide binding**: Nucleotide phosphate binding region
- **DNA binding**: DNA-binding domain
- **Calcium binding**: Calcium-binding region

### Sites and Post-Translational Modifications
- **Site**: Any interesting single amino acid site on the sequence
- **Modified residue**: Modified residues (phosphorylation, acetylation, etc.)
- **Lipidation**: Covalently attached lipid group(s)
- **Glycosylation**: Covalently attached glycan group(s)
- **Disulfide bond**: Cysteine residues participating in disulfide bonds
- **Cross-link**: Residues participating in covalent linkage(s) between proteins

### Membrane Features
- **Transmembrane**: Extent of a membrane-spanning region
- **Intramembrane**: Extent of a region located in a membrane without crossing it

### Signal Peptides and Processing
- **Signal peptide**: Sequence targeting proteins to the secretory pathway or periplasmic space
- **Transit peptide**: Extent of a transit peptide for organelle targeting
- **Propeptide**: Part of a protein that is cleaved during maturation or activation
- **Chain**: Extent of a polypeptide chain in the mature protein
- **Peptide**: Extent of an active peptide in the mature protein
- **Initiator methionine**: Cleavage of the initiator methionine

### Secondary Structure
- **Helix**: Helical regions within the experimentally determined protein structure
- **Beta strand**: Beta strand regions within the experimentally determined protein structure
- **Turn**: Turns within the experimentally determined protein structure
- **Coil**: Coil regions within the experimentally determined protein structure

### Sequence Variations
- **Sequence variant**: Natural variant of the protein
- **Natural variant**: Description of a natural variant
- **Mutagenesis**: Site which has been experimentally altered by mutagenesis
- **Sequence conflict**: Description of sequence discrepancies of unknown origin

## Why Some Proteins Have No Annotations

It's **completely normal** for many proteins to have no domain or region annotations. This happens because:

1. **Not all proteins have been structurally characterized**: Many proteins, especially from less-studied organisms, haven't been experimentally analyzed
2. **Some proteins are intrinsically disordered**: They don't have stable 3D structures
3. **Small proteins**: Very small proteins may not have distinct domains
4. **Novel proteins**: Newly discovered proteins may not have known functional domains yet
5. **Limited experimental data**: Not all proteins have been studied in detail

## What You'll Still See

Even if a protein has no domain annotations, you'll still see:
- **Sequence length**: Always available (shown as the horizontal bar)
- **Other feature types**: The protein might have binding sites, modifications, or other features even without domains
- **Comparison capability**: You can still compare proteins based on their sequence lengths

## Improved Coverage

With the expanded feature set, you should now see:
- **More annotations per protein**: Previously only fetching 6 feature types, now fetching 40+ types
- **Better functional insights**: Including binding sites, modifications, and structural features
- **More complete picture**: Comprehensive view of protein features beyond just domains

## Example Feature-Rich Proteins

Some proteins that typically have many annotations:
- **Kinases**: Active sites, binding sites, domains
- **Transcription factors**: DNA binding domains, zinc fingers
- **Membrane proteins**: Transmembrane regions, topological domains
- **Enzymes**: Active sites, binding sites, catalytic domains

## API Rate Limiting

- UniProt API has rate limits to prevent abuse
- The backend implements:
  - **24-hour caching**: Reduces repeated API calls
  - **Exponential backoff**: Handles rate limiting gracefully
  - **Parallel fetching**: Fetches multiple proteins simultaneously
  - **Error handling**: Continues with partial results if some proteins fail

## Testing the Improvements

To see the difference:
1. Try comparing well-studied proteins (e.g., kinases, transcription factors)
2. Look for proteins with known functions
3. Compare the same proteins before and after this update

You should see significantly more feature annotations now!

## Data Freshness

- **Cache TTL**: 24 hours
- **Update frequency**: UniProt is updated regularly with new experimental data
- **Manual refresh**: Clear browser cache or wait 24 hours to see updated annotations

## Further Reading

- UniProt Documentation: https://www.uniprot.org/help/
- UniProt REST API: https://www.uniprot.org/help/api
- Feature Types: https://www.uniprot.org/help/sequence_annotation
