import logging, miseq_logging, miseq_modules, os, sys

mapping_ref_path = sys.argv[1]			# Reference sequences (indexed bt2 files)
fastq = sys.argv[2]				# fastq file we want to perform mapping on
consensus_q_cutoff = int(sys.argv[3])		# Min Q for base to contribute to conseq (pileup2conseq)
mode = sys.argv[4]				# Amplicon or Nextera
is_t_primer = sys.argv[5]			# Does this have a T-primer?
min_mapping_efficiency = float(sys.argv[6])	# Fraction of fastq reads mapped needed
max_remaps = int(sys.argv[7])			# Number of remapping attempts if mapping efficiency unsatisfied
bowtie_threads = int(sys.argv[8])		# Bowtie performance scales linearly with number of threads

# Start logging but only to standard out - this will get cught by the outer call?
logger = miseq_logging.init_logging_console_only(logging.INFO)
logger.info("pid {}: miseq_modules.mapping({})".format(os.getpid(),fastq))
miseq_modules.mapping(mapping_ref_path, fastq, consensus_q_cutoff, mode, is_t_primer, min_mapping_efficiency, max_remaps, bowtie_threads)
logging.shutdown()
