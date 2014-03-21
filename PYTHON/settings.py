"""
settings_default.py
To make pipeline portable, allow user to specify
"""

# MISEQ_MONITOR settings
delay = 3600                            # Delay for polling for unprocessed runs
home = '/data/miseq/'                   # Local path on cluster for writing data
macdatafile_mount = '/media/RAW_DATA/'
NEEDS_PROCESSING = 'needsprocessing'
ERROR_PROCESSING = 'errorprocessing'

# MISEQ_PIPELINE settings
path_to_fifo_scheduler = '/usr/local/share/fifo_scheduler'

# Mapping parameters
mapping_factory_resources = [('bpsh -1', 3), ('bpsh 0', 3), ('bpsh 1', 4), ('bpsh 2', 4), ('bpsh -1', 2), ('bpsh 0', 2), ('bpsh 1', 3), ('bpsh 2', 3)]
mapping_ref_path = "/usr/local/share/miseq/development/reference_sequences/cfe" # location of .bt2 files
bowtie_threads = 4                      # Bowtie performance roughly scales with number of threads
min_mapping_efficiency = 0.95           # Fraction of fastq reads mapped needed
max_remaps = 10                         # Number of remapping attempts if mapping efficiency unsatisfied
consensus_q_cutoff = 15                 # Min Q for base to contribute to conseq (pileup2conseq)

# sam2csf parameters
single_thread_resources = [("bpsh -1", 23), ("bpsh 0", 23), ("bpsh 1", 31), ("bpsh 2", 31)]
sam2csf_q_cutoffs = [10,15,20,25,30,35]	       # Q-cutoff for base censoring
max_prop_N = 0.5                               # Drop reads with more censored bases than this proportion
read_mapping_cutoff = 10                       # Minimum bowtie read mapping quality

# g2p parameters (Amplicon only)
g2p_alignment_cutoff = 50                      # Minimum alignment score during g2p scoring
g2p_fpr_cutoffs = [2,2.5,3,3.5,4,4.5,5]        # FPR cutoff to determine R5/X4 tropism
v3_mincounts = [0,50,100,150,200,250,500,1000] # Min number of reads to contribute to %X4 calculation

# csf2counts parameters
conseq_mixture_cutoffs = [0.01,0.02,0.05,0.1,0.2,0.25]
final_alignment_ref_path = mapping_ref_path.replace('/cfe', '/csf2counts_amino_refseqs.csv')

# Intermediary files to delete when done processing this run
file_extensions_to_delete = ['bam', 'bt2', 'bt2_metrics', 'counts', 'csf', 'pileup', 'sam']
