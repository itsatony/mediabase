# Data Source Schemas and Integration Strategy

## Current Data Sources Analysis

### 1. GENCODE GTF (Transcripts Module)

#### Source Details
- **URL:** `https://ftp.ebi.ac.uk/pub/databases/gencode/Gencode_human/release_47/gencode.v47.basic.annotation.gtf.gz`
- **Update Frequency:** Every 6 months (following Ensembl releases)
- **Coverage:** ~60,000 human gene transcripts
- **File Size:** ~50MB compressed, ~400MB uncompressed
- **Format:** GTF (Gene Transfer Format)

#### Sample Record
```gtf
chr1	HAVANA	transcript	11869	14409	.	+	.	gene_id "ENSG00000290825.1"; transcript_id "ENST00000456328.2"; gene_type "lncRNA"; gene_name "DDX11L2"; transcript_type "lncRNA"; transcript_name "DDX11L2-202"; level 2; transcript_support_level "1"; hgnc_id "HGNC:37102"; havana_gene "OTTHUMG00000000961.2"; havana_transcript "OTTHUMT00000362751.1";
```

#### Integration Strategy
- **Primary Key:** `transcript_id` (ENST IDs)
- **Join Fields:** `gene_id` (ENSG), `gene_name` (symbol)
- **Extracted Fields:** All attributes in the 9th column
- **Current Issues:** Only extracting 2-3 attributes, missing many IDs

#### Enhanced Schema Extraction
```python
extracted_fields = {
    'transcript_id': 'ENST00000456328.2',
    'gene_id': 'ENSG00000290825.1', 
    'gene_name': 'DDX11L2',
    'gene_type': 'lncRNA',
    'transcript_type': 'lncRNA',
    'transcript_support_level': '1',  # MISSING currently
    'hgnc_id': 'HGNC:37102',         # MISSING currently
    'havana_gene': 'OTTHUMG00000000961.2',    # MISSING currently
    'havana_transcript': 'OTTHUMT00000362751.1', # Partially extracted
    'level': '2'                      # MISSING currently
}
```

### 2. UniProt ID Mapping (ID Enrichment Module)

#### Source Details
- **URL:** `https://ftp.uniprot.org/pub/databases/uniprot/current_release/knowledgebase/idmapping/by_organism/HUMAN_9606_idmapping.dat.gz`
- **Update Frequency:** Monthly
- **Coverage:** ~20,000 human proteins with comprehensive ID mappings
- **File Size:** ~15MB compressed
- **Format:** Tab-separated (UniProt_ID, ID_type, External_ID)

#### Sample Records
```tsv
P31946	Gene_Name	YWHAB
P31946	GeneID	7529
P31946	Ensembl	ENSG00000166913
P31946	Ensembl	ENST00000300161
P31946	RefSeq	NP_003395.1
P31946	HGNC	HGNC:12849
P31946	MIM	601066
```

#### Integration Strategy
- **Join Strategy:** Gene_Name → gene_symbol in our database
- **Coverage Issue:** Only ~60-70% of our genes have UniProt mappings
- **ID Types Extracted:** 8 types currently

### 3. Gene Ontology OBO + GOA (GO Terms Module)

#### GO OBO Source
- **URL:** `http://purl.obolibrary.org/obo/go.obo`
- **Format:** OBO (Ontology format)
- **Coverage:** ~44,000 GO terms with relationships

#### Sample GO OBO Record
```obo
[Term]
id: GO:0008150
name: biological_process
namespace: biological_process
def: "A biological process is the execution of a genetically-encoded biological function or the carrying out of a biological function by a cellular or organism-level process." [GOC:pdt]
subset: goslim_plant
```

#### GOA Source  
- **URL:** `http://ftp.ebi.ac.uk/pub/databases/GO/goa/HUMAN/goa_human.gaf.gz`
- **Format:** GAF (Gene Association Format)
- **Coverage:** ~540,000 gene-GO associations

#### Sample GOA Record
```gaf
UniProt	UniProtKB	DDX11L2	DDX11L2		GO:0003674	GO_REF:0000015	ND		F	DEAD/H-box helicase 11 like 2	DDX11L2|LOC100288069	gene	taxon:9606	20120615	UniProt
```

#### Integration Issues
- **Gene Matching:** GAF uses gene symbols but not always current/standard
- **Evidence Quality:** Not weighting evidence codes properly
- **Coverage:** Missing many genes due to symbol mismatches

### 4. Reactome Pathways (Pathways Module)

#### Source Details
- **URL:** `https://reactome.org/download/current/NCBI2Reactome_All_Levels.txt`
- **Format:** Tab-separated
- **Coverage:** ~13,000 pathway-gene associations

#### Sample Record
```tsv
1	R-HSA-169911	Membrane Trafficking	Homo sapiens
1	R-HSA-1640170	Cell Cycle	Homo sapiens
7529	R-HSA-162582	Signal Transduction	Homo sapiens
```

#### Integration Issues
- **ID Mismatch:** Uses NCBI Gene IDs but we primarily have Ensembl
- **Limited Coverage:** Only ~30% of our genes have pathway associations
- **No Evidence Scores:** Missing strength of pathway associations

### 5. DrugCentral (Drugs Module)

#### Source Details
- **URL:** `https://unmtid-shinyapps.net/download/drugcentral.dump.05102023.sql.gz`
- **Format:** PostgreSQL dump
- **Coverage:** ~4,800 drugs with targets

#### Sample Records (from SQL dump)
```sql
INSERT INTO structures (id, name, smiles) VALUES (1, 'Aspirin', 'CC(=O)OC1=CC=CC=C1C(=O)O');
INSERT INTO drug_class (id, name, is_group) VALUES (1, 'Non-steroidal anti-inflammatory drugs', false);
INSERT INTO target_class (id, name, parent_id) VALUES (1, 'Enzyme', NULL);
```

#### Integration Issues
- **Complex Schema:** SQL dump requires database setup
- **Limited Clinical Data:** Missing clinical trial phases
- **Gene Symbol Mapping:** Inconsistent gene naming

## Missing Critical Data Sources

### 1. NCBI Gene2Ensembl (PRIORITY 1)

#### Why Critical
- **Authoritative Mapping:** Official NCBI to Ensembl gene mapping
- **High Coverage:** Maps >95% of genes between databases
- **Bidirectional:** Allows mapping in both directions

#### Source Details
- **URL:** `https://ftp.ncbi.nlm.nih.gov/gene/DATA/gene2ensembl.gz`
- **Update Frequency:** Weekly
- **File Size:** ~8MB compressed
- **Format:** Tab-separated

#### Sample Record
```tsv
tax_id	GeneID	Ensembl_gene_identifier	RNA_nucleotide_accession.version	Ensembl_rna_identifier	protein_accession.version	Ensembl_protein_identifier
9606	1	ENSG00000121410	NM_130786.3	ENST00000263100	NP_570602.2	ENSP00000263100
9606	7529	ENSG00000166913	NM_003404.6	ENST00000300161	NP_003395.1	ENSP00000300161
```

#### Integration Strategy
```python
# This would fix 90% of our ID mapping issues
def integrate_gene2ensembl():
    """Map between NCBI Gene IDs and Ensembl IDs."""
    mapping = {}
    for record in gene2ensembl_data:
        if record['tax_id'] == '9606':  # Human
            ensembl_gene = record['Ensembl_gene_identifier'] 
            ncbi_gene = record['GeneID']
            ensembl_transcript = record['Ensembl_rna_identifier']
            
            mapping[ensembl_gene] = {
                'ncbi_gene_id': ncbi_gene,
                'ensembl_transcript_id': ensembl_transcript,
                'refseq_mrna': record['RNA_nucleotide_accession.version']
            }
    return mapping
```

### 2. HGNC Complete Dataset (PRIORITY 1)

#### Why Critical
- **Official Gene Symbols:** Authoritative human gene nomenclature
- **Alias Resolution:** Maps old/alternative gene symbols
- **Cross-References:** Links to all major databases

#### Source Details
- **URL:** `https://www.genenames.org/cgi-bin/download/custom?col=gd_hgnc_id&col=gd_app_sym&col=gd_aliases&col=gd_pub_ensembl_id&status=Approved&hgnc_dbtag=on&order_by=gd_app_sym_sort&format=text&submit=submit`
- **Format:** Tab-separated text
- **Coverage:** ~43,000 approved human gene symbols

#### Sample Record
```tsv
hgnc_id	symbol	alias_symbol	ensembl_gene_id
HGNC:5	A1BG	A1B|ABG|GAB	ENSG00000121410
HGNC:37102	DDX11L2	LOC100288069	ENSG00000290825
HGNC:24086	YWHAB	14-3-3-beta	ENSG00000166913
```

#### Integration Strategy
```python
def resolve_gene_symbols_with_hgnc():
    """Use HGNC to resolve alternative gene symbols."""
    symbol_mapping = {}
    for record in hgnc_data:
        official_symbol = record['symbol']
        aliases = record['alias_symbol'].split('|') if record['alias_symbol'] else []
        
        # Map all aliases to official symbol
        for alias in [official_symbol] + aliases:
            symbol_mapping[alias] = official_symbol
            
    return symbol_mapping
```

### 3. ChEMBL Target Data (PRIORITY 1)

#### Why Better Than DrugCentral
- **Clinical Phases:** Includes clinical trial phases
- **Mechanism of Action:** Detailed MOA descriptions  
- **Activity Data:** Binding affinities and IC50 values
- **Regular Updates:** Monthly releases

#### Source Details
- **URL:** `https://ftp.ebi.ac.uk/pub/databases/chembl/ChEMBLdb/latest/chembl_33_mysql.tar.gz`
- **Alternative API:** `https://www.ebi.ac.uk/chembl/api/data/`
- **Format:** MySQL dump or JSON API

#### Sample API Response
```json
{
  "molecule_chembl_id": "CHEMBL25",
  "pref_name": "ASPIRIN",
  "max_phase": 4,
  "therapeutic_flag": true,
  "targets": [{
    "target_chembl_id": "CHEMBL204", 
    "pref_name": "Cyclooxygenase-1",
    "target_type": "SINGLE PROTEIN",
    "organism": "Homo sapiens"
  }],
  "mechanisms": [{
    "mechanism_of_action": "Cyclooxygenase inhibitor",
    "action_type": "INHIBITOR"
  }]
}
```

### 4. ClinicalTrials.gov API (PRIORITY 2)

#### Why Critical for Clinical Evidence
- **Clinical Validation:** Real clinical trial data
- **Current Status:** Ongoing vs completed trials
- **Gene-Drug Associations:** Mentions of genes in trials

#### API Details
- **URL:** `https://clinicaltrials.gov/api/v2/studies`
- **Rate Limit:** 1000 requests/hour
- **Format:** JSON

#### Sample API Response
```json
{
  "protocolSection": {
    "identificationModule": {
      "nctId": "NCT04123456",
      "briefTitle": "Aspirin in Cancer Prevention"
    },
    "statusModule": {
      "overallStatus": "COMPLETED",
      "studyFirstSubmitDate": "2019-10-09"
    },
    "interventionModule": {
      "interventions": [{
        "type": "DRUG",
        "name": "Aspirin",
        "description": "Low-dose aspirin 81mg daily"
      }]
    },
    "conditionsModule": {
      "conditions": ["Colorectal Cancer", "Cardiovascular Disease"]
    }
  }
}
```

#### Integration Strategy
```python
def get_clinical_evidence_for_gene(gene_symbol: str):
    """Query ClinicalTrials.gov for gene mentions."""
    search_url = f"https://clinicaltrials.gov/api/v2/studies?query.term={gene_symbol}"
    response = requests.get(search_url)
    
    clinical_evidence = []
    for study in response.json()['studies']:
        evidence = {
            'nct_id': study['protocolSection']['identificationModule']['nctId'],
            'title': study['protocolSection']['identificationModule']['briefTitle'],
            'status': study['protocolSection']['statusModule']['overallStatus'],
            'conditions': study['protocolSection']['conditionsModule']['conditions'],
            'interventions': [i['name'] for i in study['protocolSection']['interventionModule']['interventions']]
        }
        clinical_evidence.append(evidence)
    
    return clinical_evidence
```

## Recommended Schema Updates for README

Add this section to README.md:

```markdown
## Data Sources and Integration

### Primary Sources

| Source | URL | Coverage | Update Frequency | Primary Use |
|--------|-----|----------|------------------|-------------|
| GENCODE GTF | https://ftp.ebi.ac.uk/pub/databases/gencode/ | 60k transcripts | 6 months | Base gene/transcript data |
| NCBI Gene2Ensembl | https://ftp.ncbi.nlm.nih.gov/gene/DATA/ | 95% gene mapping | Weekly | ID mapping |
| HGNC Complete | https://www.genenames.org/ | 43k gene symbols | Monthly | Gene symbol resolution |
| UniProt Mapping | https://ftp.uniprot.org/ | 20k proteins | Monthly | Protein-centric IDs |
| GO OBO/GOA | http://geneontology.org/ | 44k terms, 540k assocs | Weekly | Functional annotation |
| Reactome | https://reactome.org/ | 13k pathway-gene links | Quarterly | Pathway data |
| ChEMBL | https://www.ebi.ac.uk/chembl/ | 2M compounds, 15k targets | Monthly | Drug-target data |
| ClinicalTrials.gov | https://clinicaltrials.gov/ | 400k+ trials | Daily | Clinical evidence |

### Integration Strategy

#### Phase 1: ID Resolution
1. **GENCODE GTF** → Extract base transcript/gene data
2. **NCBI Gene2Ensembl** → Map Ensembl ↔ NCBI Gene IDs  
3. **HGNC Complete** → Resolve gene symbol aliases
4. **UniProt Mapping** → Add protein-centric IDs

#### Phase 2: Functional Annotation  
5. **GO Terms** → Functional classification (leveraging improved IDs)
6. **Reactome Pathways** → Biological pathways (using NCBI Gene IDs)

#### Phase 3: Clinical Data
7. **ChEMBL** → Drug-target interactions with clinical phases
8. **ClinicalTrials.gov** → Clinical trial evidence

### Sample Integrated Record
```json
{
  "transcript_id": "ENST00000300161",
  "gene_symbol": "YWHAB", 
  "gene_id": "ENSG00000166913",
  "ncbi_gene_id": "7529",
  "hgnc_id": "HGNC:12849",
  "uniprot_ids": ["P31946"],
  "go_terms": {
    "molecular_function": ["GO:0019904", "GO:0008601"],
    "biological_process": ["GO:0007165", "GO:0019725"],
    "cellular_component": ["GO:0005737", "GO:0005634"]
  },
  "pathways": ["R-HSA-162582", "R-HSA-392451"],
  "drugs": {
    "CHEMBL25": {
      "name": "Aspirin",
      "max_phase": 4,
      "mechanism": "Cyclooxygenase inhibitor"
    }
  },
  "clinical_trials": [
    {
      "nct_id": "NCT04123456",
      "title": "Aspirin in Cancer Prevention", 
      "status": "COMPLETED"
    }
  ]
}
```
```

