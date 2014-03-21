from datetime import datetime
import sys, re, math
import random


# Matches the size of the left-gap induced by alignment
gpfx = re.compile('^[-]+')

def len_gap_prefix (s):
    """Find length of gap prefix"""
    hits = gpfx.findall(s)
    if hits:
        return len(hits[0])
    else:
        return 0


# Matches 1+ occurences of a number, followed by a letter from {MIDNSHPX=}
cigar_re = re.compile('[0-9]+[MIDNSHPX=]')

def apply_cigar (cigar, seq, qual):
    """
    Parse SAM CIGAR and apply to the SAM nucleotide sequence.

    Input: cigar, sequence, and quality string from SAM.
    Output: shift (?), sequence with CIGAR incorporated + new quality string
    """
    newseq = ''
    newqual = ''
    tokens = cigar_re.findall(cigar)
    if len(tokens) == 0:
        return None, None, None

    # Account for removing soft clipped bases on left
    shift = 0
    if tokens[0].endswith('S'):
        shift = int(tokens[0][:-1])

    left = 0
    for token in tokens:
        length = int(token[:-1])

        # Matching sequence: carry it over
        if token[-1] == 'M':
            newseq += seq[left:(left+length)]
            newqual += qual[left:(left+length)]
            left += length

        # Deletion relative to reference: pad with gaps
        elif token[-1] == 'D':
            newseq += '-'*length
            newqual += ' '*length 		# Assign fake placeholder score (Q=-1)

        # Insertion relative to reference: skip it (excise it)
        elif token[-1] == 'I':
            left += length
            continue

        # Soft clipping leaves the sequence in the SAM - so we should skip it
        elif token[-1] == 'S':
            left += length
            continue

        else:
            print "Unable to handle CIGAR token: {} - quitting".format(token)
            sys.exit()

    return shift, newseq, newqual

def merge_pairs (seq1, seq2, qual1, qual2, q_cutoff=10, minimum_q_delta=5):
    """
    Merge two sequences that overlap over some portion (paired-end
    reads).  Using the positional information in the SAM file, we will
    know where the sequences lie relative to one another.  In the case
    that the base in one read has no complement in the other read
    (in partial overlap region), take that base at face value.

    q_cutoff =          minimum quality score to accept base call
    minimum_q_delta =   minimum difference in quality scores between mates
                        above which we take the higher quality base, and
                        below which both bases are discarded.
    """
    import logging

    mseq = ''   # the merged sequence

    if len(seq1) > len(seq2):
        # require seq2 to be the longer string, if strings are unequal lengths
        seq1, seq2 = seq2, seq1
        qual1, qual2 = qual2, qual1 # FIXME: quality strings must be concordant

    for i, c2 in enumerate(seq2):
        # FIXME: Track the q-score of each base at each position
        q2 = ord(qual2[i])-33   # ASCII to integer conversion, error prob. = 10^(-q2/10)

        if i < len(seq1):
            c1 = seq1[i]
            q1 = ord(qual1[i])-33

            # Gaps are given the lowest q-rank (q = -1) but are NOT N-censored
            if c1 == '-' and c2 == '-':
                mseq += '-'

            # Reads agree and at least one has sufficient confidence
            if c1 == c2:
                if q1 > q_cutoff or q2 > q_cutoff:
                    mseq += c1
                else:
                    # neither base is confident
                    mseq += 'N'
            else:
                # reads disagree
                if abs(q2 - q1) >= minimum_q_delta:
                    # given one base has substantially higher quality than the other
                    if q1 > max(q2, q_cutoff):
                        mseq += c1
                    elif q2 > max(q1, q_cutoff):
                        mseq += c2
                    else:
                        # neither quality score is sufficiently high
                        mseq += 'N'
                else:
                    # discordant bases are too similar in confidence to choose
                    mseq += 'N'
        else:
            # no mate in other read
            if q2 > q_cutoff:
                mseq += c2
            else:
                mseq += 'N'
    return mseq


def sam2fasta (infile, cutoff=10, mapping_cutoff = 5, max_prop_N=0.5):
    """
    Parse SAM file contents and return FASTA. For matched read pairs,
    merge the reads together into a single sequence
    """
    fasta = []
    lines = infile.readlines()

    # If this is a completely empty file, return
    if len(lines) == 0:
        return None

    # Skip top SAM header lines
    for start, line in enumerate(lines):
        if not line.startswith('@'):
            break   # exit loop with [start] equal to index of first line of data

    # If this is an empty SAM, return
    if start == len(lines)-1:
        return None

    i = start
    while i < len(lines):
        qname, flag, refname, pos, mapq, cigar, rnext, pnext, tlen, seq, qual = lines[i].strip('\n').split('\t')[:11]

        # If read failed to map or has poor mapping quality, skip it
        if refname == '*' or cigar == '*' or int(mapq) < mapping_cutoff:
            i += 1
            continue

        pos1 = int(pos)
        # shift = offset of read start from reference start
        shift, seq1, qual1 = apply_cigar(cigar, seq, qual)

        if not seq1:
            # failed to parse CIGAR string
            i += 1
            continue

        #seq1 = '-'*pos1 + censor_bases(seq1, qual1, cutoff)
        seq1 = '-'*pos1 + seq1     # FIXME: We no longer censor bases up front
        qual1 = '-'*pos1 + qual1    # FIXME: Give quality string the same offset


        # No more lines
        if (i+1) == len(lines):
            break

        # Look ahead in the SAM for matching read
        qname2, flag, refname, pos, mapq, cigar, rnext, pnext, tlen, seq, qual = lines[i+1].strip('\n').split('\t')[:11]

        if qname2 == qname:
            if refname == '*' or cigar == '*':
                # Second read failed to map - add unpaired read to FASTA and skip this line
                fasta.append([qname, seq1])
                i += 2
                continue

            pos2 = int(pos)
            shift, seq2, qual2 = apply_cigar(cigar, seq, qual)

            if not seq2:
                # Failed to parse CIGAR
                fasta.append([qname, seq1])
                i += 2
                continue

            #seq2 = '-'*pos2 + censor_bases(seq2, qual2, cutoff)
            seq2 = '-'*pos2 + seq2      # FIXME: We no longer censor bases up front
            qual2 = '-'*pos2 + qual2     # FIXME: Give quality string the same offset

            mseq = merge_pairs(seq1, seq2, qual1, qual2, cutoff)    # FIXME: We now feed these quality data into merge_pairs

            # Sequence must not have too many censored bases
            # TODO: garbage reads should probably be reported
            if mseq.count('N') / float(len(mseq)) < max_prop_N:
                fasta.append([qname, mseq])

            i += 2
            continue

        # ELSE no matched pair
        fasta.append([qname, seq1])
        i += 1

    return fasta


def samBitFlag (flag):
    """
    Interpret bitwise flag in SAM field as follows:

    Flag	Chr	Description
    =============================================================
    0x0001	p	the read is paired in sequencing
    0x0002	P	the read is mapped in a proper pair
    0x0004	u	the query sequence itself is unmapped
    0x0008	U	the mate is unmapped
    0x0010	r	strand of the query (1 for reverse)
    0x0020	R	strand of the mate
    0x0040	1	the read is the first read in a pair
    0x0080	2	the read is the second read in a pair
    0x0100	s	the alignment is not primary
    0x0200	f	the read fails platform/vendor quality checks
    0x0400	d	the read is either a PCR or an optical duplicate
    """
    labels = ['is_paired', 'is_mapped_in_proper_pair', 'is_unmapped', 'mate_is_unmapped',
            'is_reverse', 'mate_is_reverse', 'is_first', 'is_second', 'is_secondary_alignment',
            'is_failed', 'is_duplicate']

    binstr = bin(int(flag)).replace('0b', '')
    # flip the string
    binstr = binstr[::-1]
    # if binstr length is shorter than 11, pad the right with zeroes
    for i in range(len(binstr), 11):
        binstr += '0'

    bitflags = list(binstr)
    res = {}
    for i, bit in enumerate(bitflags):
        res.update({labels[i]: bool(int(bit))})

    return (res)


def sampleSheetParser (handle):
    """
    Parse the contents of SampleSheet.csv, convert contents into a
    Python dictionary object.
    Samples are tracked by sample name and sample number (e.g., S9).
    This is to distinguish replicates of the same sample.
    """

    # FIXME: Conan is going to start annotating samples as either amplicon or nextera
    # FIXME: We may need to change this code to handle this

    tag = None
    get_header = False
    header = [] # store Data block column labels
    sample_number = 1 # 1-indexing
    run_info = {} # return object

    for line in handle:
        # parse tags
        if line.startswith('['):
            tag = line.strip('\n').rstrip(',').strip('[]')
            if tag == 'Data':
                get_header = True
            continue

        # else not a tag line, parse contents
        tokens = line.strip('\n').split(',')

        # process tokens according to current tag
        if tag == 'Header':
            # inside [Header] block
            key, value = tokens[:2]
            run_info.update({key: value})

        elif tag == 'Data':
            # inside [Data] block
            if not run_info.has_key('Data'):
                run_info.update({'Data': {}})

            if get_header:
                # parse the first line as the header row
                header = tokens
                if not 'Sample_Name' in header:
                    sys.stderr.write("ERROR: SampleSheet.csv Data header does not include Sample_Name")
                    sys.exit()
                get_header = False
                continue

            index1 = tokens[header.index('index')]
            index2 = tokens[header.index('index2')]

            # parse Sample_Name field
            filename = tokens[header.index('Sample_Name')]
            clean_filename = re.sub('[_.;]', '-', filename)
            clean_filename += '_S%d' % sample_number # should correspond to FASTQ filename

            run_info['Data'].update({clean_filename: {'index1': index1,
                                                      'index2': index2}})

            # parse Description field
            # FIXME: currently this is partitioned by sub-samples (semi-colon delimited)
            # FIXME: but the pipeline does not support differential handling of sub-samples

            desc = tokens[header.index('Description')]
            desc_fields = desc.split() # whitespace-delimited
            for desc_field in desc_fields:
                desc_field_label = desc_field.split(':')[0]
                desc_subfields = desc_field.replace(desc_field_label+':', '').split(';')

                for desc_subfield in desc_subfields:
                    desc_subfield_tokens = desc_subfield.split(':')
                    sample_name = desc_subfield_tokens[0]
                    clean_sample_name = re.sub('[_.]', '-', sample_name)

                    if desc_field_label == 'Research':
                        is_research = (desc_subfield_tokens[1] == 'TRUE')
                        # would have been keying by clean_sample_name here and below
                        run_info['Data'][clean_filename].update({
                            'research': is_research,
                            'is_T_primer': 'TPRIMER' in desc_subfield_tokens})

                    if desc_field_label == 'Disablecontamcheck':
                        run_info['Data'][clean_filename].update({'disable_contamination_check': (desc_subfield_tokens[-1]=='TRUE')})

                    if desc_field_label == 'Comments':
                        run_info['Data'][clean_filename].update({'comments': desc_subfield_tokens[-1]})

                if not run_info['Data'][clean_filename].has_key('disable_contamination_check'):
                    # 'Disablecontamcheck' subfield not always under Description
                    # default to contamination check active
                    run_info['Data'][clean_filename].update({'disable_contamination_check': False})

                # FIXME: for the time being, apply ONLY first sub-sample description to entire sample
                break

            sample_number += 1

        else:
            # ignore other tags
            pass
    return run_info


def timestamp(message):
    curr_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')
    output = ' {} {}'.format(curr_time,message)
    print output
    sys.stdout.flush()
    return "{}\n".format(output)

def prop_x4 (v3prot_path, fpr_cutoff, min_count):
    """Determine proportion X4 from v3prot file"""

    import logging

    with open(v3prot_path, 'rU') as infile:
        try:
            logging.info("Reading {}".format(v3prot_path))
            fasta = convert_fasta(infile.readlines())
        except Exception as e:
            raise Exception("convert_fasta threw exception '{}'".format(str(e)))

    total_count = 0
    total_x4_count = 0

    # Example header: F00309-IL_variant_0_count_27_fpr_4.0
    for h, s in fasta:
        try:
            tokens = h.split('_')
            variant = int(tokens[tokens.index('variant')+1])
            count = int(tokens[tokens.index('count')+1])
            fpr = float(tokens[tokens.index('fpr')+1])
        except:
            continue

        if count < min_count:
            continue
        if fpr <= fpr_cutoff:
            total_x4_count += count
        total_count += count

    proportion_X4 = (float(total_x4_count) / float(total_count)) * 100
    return (proportion_X4, total_x4_count, total_count)

def poly2conseq(poly_file,alphabet='ACDEFGHIKLMNPQRSTVWY*-',minCount=3):
    """
    Given a poly file containing either amino or nucleotide data,
    and a minimum base cutoff, generate the conseq. If the number
    of chars does not exceed the min base cutoff, an 'N' is reported.

    Assumptions: 	poly CSV has (sample, region, coord) followed by
            each character in the alphabet
    """

    import os,sys
    from glob import glob

    infile = open(poly_file, 'rU')
    lines = infile.readlines()
    infile.close()

    # For each coord within the sample-specific poly
    char_freqs = {}
    conseq = ""
    for start, line in enumerate(lines):

        # Ignore the poly header
        if start == 0: continue

        # Get the coord, and the char frequency for this coord
        fields = line.rstrip("\n").split(',')
        coord = fields[2]
        for i, char in enumerate(alphabet): char_freqs[char] = fields[i+3]

        # And take the max (Find the consensus)
        max_char = max(char_freqs, key=lambda n: char_freqs[n])
        if int(char_freqs[max_char]) <= minCount: conseq += 'N'
        else: conseq += max_char

    return conseq


def convert_csf (csf_handle):
    """
    Extract header, offset, and seq from the CSF.
    The header is qname for Nextera, and rank_count for Amplicon.
    """
    left_gap_position = {}
    right_gap_position = {}

    fasta = []
    for line in csf_handle:
        fields = line.strip('\n').split(',')
        CSF_header, offset, seq = fields[0], fields[1], fields[2]
        fasta.append([CSF_header, seq])
        left_gap_position[CSF_header] = int(offset)
        right_gap_position[CSF_header] = left_gap_position[CSF_header] + len(seq)

    return fasta,left_gap_position,right_gap_position



def convert_fasta (lines):	
    blocks = []
    sequence = ''
    for i in lines:
        if i[0] == '$': # skip h info
            continue
        elif i[0] == '>' or i[0] == '#':
            if len(sequence) > 0:
                blocks.append([h,sequence])
                sequence = ''	# reset containers
                h = i.strip('\n')[1:]
            else:
                h = i.strip('\n')[1:]
        else:
            sequence += i.strip('\n')
    try:
        blocks.append([h,sequence])	# handle last entry
    except:
        raise Exception("convert_fasta(): Error appending to blocks [{},{}]".format(h, sequence))
    return blocks



def fasta2phylip (fasta, handle):
    ntaxa = len(fasta)
    nsites = len(fasta[0][1])
    handle.write(str(ntaxa)+' '+str(nsites)+'\n')
    for row in fasta:
        # phylip format uses space delimiters
        header = regex.sub('',row[0]).replace(' ','_')
        handle.write(header+' '+row[1]+'\n')


def convert_phylip (lines):
    """
    Convert line input from Phylip format file into
    Python list object.
    """
    res = []
    try:
        ntaxa, nsites = lines[0].strip('\n').split()
    except:
        print lines[0]
        raise

    if len(lines) != int(ntaxa) + 1:
        raise AssertionError ('Number of taxa does not equal header')

    for line in lines[1:]:
        header, seq = line.strip('\n').split()
        res.append( [header, seq] )

    return res



complement_dict = {'A':'T', 'C':'G', 'G':'C', 'T':'A', 
                    'W':'S', 'R':'Y', 'K':'M', 'Y':'R', 'S':'W', 'M':'K',
                    'B':'V', 'D':'H', 'H':'D', 'V':'B',
                    '*':'*', 'N':'N', '-':'-'}

def reverse_and_complement(seq):
    rseq = seq[::-1]
    rcseq = ''
    for i in rseq:	# reverse order
        rcseq += complement_dict[i]
    return rcseq



codon_dict = {'TTT':'F', 'TTC':'F', 'TTA':'L', 'TTG':'L',
                'TCT':'S', 'TCC':'S', 'TCA':'S', 'TCG':'S',
                'TAT':'Y', 'TAC':'Y', 'TAA':'*', 'TAG':'*',
                'TGT':'C', 'TGC':'C', 'TGA':'*', 'TGG':'W',
                'CTT':'L', 'CTC':'L', 'CTA':'L', 'CTG':'L',
                'CCT':'P', 'CCC':'P', 'CCA':'P', 'CCG':'P',
                'CAT':'H', 'CAC':'H', 'CAA':'Q', 'CAG':'Q',
                'CGT':'R', 'CGC':'R', 'CGA':'R', 'CGG':'R',
                'ATT':'I', 'ATC':'I', 'ATA':'I', 'ATG':'M',
                'ACT':'T', 'ACC':'T', 'ACA':'T', 'ACG':'T',
                'AAT':'N', 'AAC':'N', 'AAA':'K', 'AAG':'K',
                'AGT':'S', 'AGC':'S', 'AGA':'R', 'AGG':'R',
                'GTT':'V', 'GTC':'V', 'GTA':'V', 'GTG':'V',
                'GCT':'A', 'GCC':'A', 'GCA':'A', 'GCG':'A',
                'GAT':'D', 'GAC':'D', 'GAA':'E', 'GAG':'E',
                'GGT':'G', 'GGC':'G', 'GGA':'G', 'GGG':'G',
                '---':'-', 'XXX':'?'}

mixture_regex = re.compile('[WRKYSMBDHVN-]')

mixture_dict = {'W':'AT', 'R':'AG', 'K':'GT', 'Y':'CT', 'S':'CG', 
                'M':'AC', 'V':'AGC', 'H':'ATC', 'D':'ATG',
                'B':'TGC', 'N':'ATGC', '-':'ATGC'}

#mixture_dict_2 =  [ (set(v), k) for k, v in mixture_dict.iteritems() ]
ambig_dict = dict(("".join(sorted(v)), k) for k, v in mixture_dict.iteritems())


def translate_nuc (seq, offset, resolve=False):
    """
    Translate nucleotide sequence into amino acid sequence.
        offset by X shifts sequence to the right by X bases
    Synonymous nucleotide mixtures are resolved to the corresponding residue.
    Nonsynonymous nucleotide mixtures are encoded with '?'
    """

    seq = '-'*offset + seq

    aa_list = []
    aa_seq = ''	# use to align against reference, for resolving indels

    # loop over codon sites in nucleotide sequence
    for codon_site in xrange(0, len(seq), 3):
        codon = seq[codon_site:codon_site+3]

        if len(codon) < 3:
            break

        # note that we're willing to handle a single missing nucleotide as an ambiguity
        if codon.count('-') > 1 or '?' in codon:
            if codon == '---':	# don't bother to translate incomplete codons
                aa_seq += '-'
            else:
                aa_seq += '?'
            continue

        # look for nucleotide mixtures in codon, resolve to alternative codons if found
        num_mixtures = len(mixture_regex.findall(codon))

        if num_mixtures == 0:
            aa_seq += codon_dict[codon]

        elif num_mixtures == 1:
            resolved_AAs = []
            for pos in range(3):
                if codon[pos] in mixture_dict.keys():
                    for r in mixture_dict[codon[pos]]:
                        rcodon = codon[0:pos] + r + codon[(pos+1):]
                        if codon_dict[rcodon] not in resolved_AAs:
                            resolved_AAs.append(codon_dict[rcodon])
            if len(resolved_AAs) > 1:
                if resolve:
                    # for purposes of aligning AA sequences
                    # it is better to have one of the resolutions
                    # than a completely ambiguous '?'
                    aa_seq += resolved_AAs[0]
                else:
                    aa_seq += '?'
            else:
                aa_seq += resolved_AAs[0]

        else:
            aa_seq += '?'

    return aa_seq



def consensus(column, alphabet='ACGT', resolve=False):
    """
    Plurality consensus - nucleotide with highest frequency.
    In case of tie, report mixtures.
    """
    freqs = {}

    # Populate possible bases from alphabet
    for char in alphabet:
        freqs.update({char: 0})

    # Traverse the column...
    for char in column:

        # If the character is within the alphabet, keep it
        if char in alphabet:
            freqs[char] += 1

        # If there exists an entry in mixture_dict, take that
        # mixture_dict maps mixtures to bases ('-' maps to 'ACGT')
        elif mixture_dict.has_key(char):

            # Handle ambiguous nucleotides with equal weighting
            # (Ex: for a gap, add 1/4 to all 4 chars)
            resolutions = mixture_dict[char]
            for char2 in resolutions:
                freqs[char2] += 1./len(resolutions)
        else:
            pass

    # AT THIS POINT, NO GAPS ARE RETAINED IN FREQS - TRUE GAPS ARE REPLACED WITH 'ACGT' (N)


    # Get a base with the highest frequency
    # Note: For 2 identical frequencies, it will only return 1 base
    base = max(freqs, key=lambda n: freqs[n])
    max_count = freqs[base]

    # Return all bases (elements of freqs) such that the freq(b) = max_count
    possib = filter(lambda n: freqs[n] == max_count, freqs)

    # If there is only a single base with the max_count, return it
    if len(possib) == 1:
        return possib[0]

    # If a gap is in the list of possible bases... remove it unless it is the only base
    # CURRENTLY, THIS BRANCH IS NEVER REACHED
    elif "-" in possib:
        if resolve:
            possib.remove("-")
            if len(possib) == 0:
                return "-"
            elif len(possib) == 1:
                return possib[0]
            else:
                return ambig_dict["".join(sorted(possib))]

        # If resolve is turned off, gap characters override all ties
        else:
            return "-"
    else:
        return ambig_dict["".join(sorted(possib))]


def majority_consensus (fasta, threshold = 0.5, alphabet='ACGT', ambig_char = 'N'):
    """
    Return majority-rule consensus sequence.
    [threshold] = percentage of column that most common character must exceed
    [alphabet] = recognized character states
    """
    consen = []
    columns = transpose_fasta(fasta)
    for column in columns:
        consen.append(consensus(column, alphabet=alphabet, resolve=False))
    newseq = "".join(consen)
    return newseq


# =======================================================================

def transpose_fasta (fasta):
    """
    Returns an array of alignment columns.
    some checks to make sure the right kind of object is being sent
    """
    #
    if type(fasta) is not list:
        return None
    if type(fasta[0]) is not list or len(fasta[0]) != 2:
        return None

    # fasta[0][1] gets the length of the sequence in the first entry...?
    n_columns = len(fasta[0][1])
    res = []

    # For each coordinate, extract the character from each fasta sequence
    for c in range(n_columns):
        res.append ( [ s[c] for h, s in fasta ] )

    # Return list of lists: res[1] contains list of chars at position 1 of each seq
    return res

def untranspose_fasta(tfasta):
    nseq = len(tfasta[0])
    res = [ '' for s in range(nseq) ]
    for col in tfasta:
        for i in range(nseq):
            res[i] += col[i]
    return res



def entropy_from_fasta (fasta, alphabet = 'ACGT', counts = None):
    """
    Calculate the mean entropy over columns of an alignment
    passed as a FASTA object (list of lists).
    Defaults to the nucleotide alphabet.
    If a vector of counts is passed, then entropy calculations will
    be weighted by the frequency of each sequence.  Otherwise each
    sequence will be counted as one instance.

    NOTE: Non-alphabet characters (e.g., mixtures, gaps) are being simply ignored!

    Test code:
    infile = open('/Users/apoon/wip/etoi/screened/ACT 60690_NEF_forward.pre2.screen1', 'rU')
    fasta = convert_fasta(infile.readlines())
    infile.close()
    counts = [int(h.split('_')[1]) for h, s in fasta]
    """
    columns = transpose_fasta (fasta)
    ents = []
    for col in columns:
        ent = 0.

        # expand character count in vector if 'counts' argument is given
        if counts:
            new_col = []
            for i in range(len(col)):
                new_col.extend( [ col[i] for j in range(counts[i]) ] )
            col = new_col

        for char in alphabet:
            freq = float(col.count(char)) / len(col)
            if freq > 0:
                ent -= freq * math.log(freq, 2)

        ents.append(ent)

    mean_ent = sum(ents) / len(ents)
    return mean_ent



def bootstrap(fasta):
    """
    Random sampling of columns with replacement from alignment.
    Returns a FASTA (list of lists)
    """
    nsites = len(fasta[0][1])
    seqnames = [h for (h, s) in fasta]
    res = []
    tfasta = transpose_fasta(fasta)
    sample = []
    for j in range(nsites):
        sample.append(tfasta[random.randint(0, nsites-1)])

    seqs = untranspose_fasta(sample)
    for k, s in enumerate(seqs):
        res.append([seqnames[k], s])

    return res


def pileup_to_conseq (path_to_pileup, qCutoff):
    """
    Generate a consensus sequence from a pileup file produced by samtools mpileup.
    mpileup generates a massive file.
    A pileup file stores each aligned read for each position with respect to reference.
    [infile] should be an absolute or relative path.
    """
    import logging,re,sys

    indels_re = re.compile('\+[0-9]+|\-[0-9]+')	# Matches '+' or '-' followed by 1+ numbers
    conseq = ''
    to_skip = 0

    # For each line in the pileup (For a given coordinate in the reference)
    infile = open(path_to_pileup, 'rU')
    for line in infile:

        # Account for majority deletion in previous lines
        if to_skip > 0:
            to_skip -= 1
            continue

        # Extract pileup features
        label, pos, en, depth, astr, qstr = line.strip('\n').split('\t')
        pos = int(pos)
        alist = []  # alist stores all bases at a given coordinate
        i = 0       # Current index for astr
        j = 0       # Current index for qstr

        # WARNING: THE SAM FORMAT DIVERGES FROM THE SOURCEFORGE DOCUMENTATION
        # BRIEFLY, INSTEAD OF "." TO MEAN "MATCH" THE BASE IS NOW PLACED DIRECTLY
        # INSIDE OF THE FEATURE STRING (SO, THE REF BASE HAS NO REAL MEANING)

        # For each position in astr (Main pileup feature list)
        while i < len(astr):

            # '^' means this is a new read: ^7G means the new read starts with
            # 'G' with a quality of asc(7)-33 = 37-33 = 4 (ASCII code - 33 gives Q)
            if astr[i] == '^':
                q = ord(qstr[j])-33
                base = astr[i+2] if q >= qCutoff else 'N'
                alist.append(base)
                i += 3
                j += 1

            # '*' represents a deleted base
            # '$' represents the end of a read
            elif astr[i] in '*$':
                i += 1

            else:
                # "+[0-9]+[ACGTN]+" denotes an insertion ("-[0-9]+[ACGTN]+" denotes deletion)
                # Ex: +2AG means there is an insert of "AG"
                if i < len(astr)-1 and astr[i+1] in '+-':

                    # From "+2AG...." extract out "+2"
                    # (re.match searches only BEGINNING of string)
                    m = indels_re.match(astr[i+1:])

                    # Get the length of the indel ("2" from "+2")
                    indel_len = int(m.group().strip('+-'))

                    # If this were "+19AGGACCA" then len would evaluate to 3
                    # So, left is exactly the index, plus the +- sign, plus the
                    # number of digits related to the size of this indel
                    left = i+1 + len(m.group())

                    # The insertion characters start from left and proceeds to left+len
                    insertion = astr[left:(left+indel_len)]

                    q = ord(qstr[j])-33
                    base = astr[i].upper() if q >= qCutoff else 'N'

                    # Ex token: A+3tgt
                    token = base + m.group() + insertion
                    alist.append(token)

                    i += len(token)
                    j += 1

                else:
                    # Operative case: sequence matches reference (And no indel ahead)
                    q = ord(qstr[j])-33
                    base = astr[i].upper() if q >= qCutoff else 'N'
                    alist.append(base)
                    i += 1
                    j += 1

        # Is this position dominated by an insertion or deletion?
        insertions = [x for x in alist if '+' in x]
        deletions = [x for x in alist if '-' in x]
        non_indel = sum([alist.count(nuc) for nuc in 'ACGT'])

        if len(insertions) > non_indel:
            intermed = [(insertions.count(token), token) for token in set(insertions)]
            intermed.sort(reverse=True)

            # Add most frequent insertion to consensus
            count, token = intermed[0]
            m = indels_re.findall(token)[0] # \+[0-9]+
            conseq += token[0] + token[1+len(m):]
            continue

        if len(deletions) > non_indel:
            # skip this line and the next N lines as necessary
            intermed = [(deletions.count(token), token) for token in set(deletions)]
            intermed.sort(reverse=True)
            count, token = intermed[0]

            m = indels_re.findall(token)[0]
            to_skip = int(m.strip('-')) - 1 # omitting this line counts as one
            continue

        # For this coordinate (line in the pileup), alist now contains all characters that occured
        counts = [(nuc, alist.count(nuc)) for nuc in 'ACGTN']
        intermed = [(v,k) for k, v in counts] # Store in intermed so we can take the majority base
        intermed.sort(reverse=True)
        conseq += intermed[0][1]

    infile.close()

    # Get the prefix from the pileup file
    prefix = path_to_pileup.split('/')[-1].split('_')[0]
    outpath = path_to_pileup+'.conseq'
    confile = open(outpath, 'w')
    confile.write(">{}\n{}\n".format(prefix, conseq))
    confile.close()

    logging.info("Conseq: {}".format(conseq))

    return outpath


def parse_fasta (handle):
    """
    Read lines from a FASTA file and return as a list of
    header, sequence tuples.
    """
    res = []
    sequence = ''
    for line in handle:
        if line.startswith('$'): # skip annotations
            continue
        elif line.startswith('>') or line.startswith('#'):
            if len(sequence) > 0:
                res.append((h, sequence))
                sequence = ''   # reset containers
            h = line.lstrip('>#').rstrip('\n')
        else:
            sequence += line.strip('\n')

    res.append((h, sequence)) # handle last entry
    return res
