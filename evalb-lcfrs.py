#!/usr/bin/python
""" Evaluation of discontinuous bracketings. See USAGE. """

# Authors: Wolfgang Maier <maierw@hhu.de>,
# Andreas van Cranenburgh <a.w.vancranenburgh@uva.nl>

# Version: January 24, 2014

from __future__ import print_function, division
import io
import sys
import getopt
from collections import defaultdict, Counter as multiset

USAGE = """Usage: %s [OPTIONS]

Extension of the evalb program, to evaluate discontinuous constituency trees.
In the absence of discontinuity, this program should yield the same results as
EVALB, but you should check that for yourself. This program returns precision,
recall, f-measure and exact match. It expects its input data to be in export
format (Brants 1997).

Comparsion is done on the basis of "signatures", bags of labeled bracketings
for non-terminals. To match the sentences which are to be compared, the program
uses the export sentence numbering. Missing sentences in answer affect the
result. An EVALB parameter file can be specified (e.g., the included file
``proper.prm`` to ignore root node & punctuation).

[OPTIONS]
    -k key file (gold data)
    -a answer file (parser output)
    -p evalb parameter file (optional)
    -u unlabeled evaluation
    -l limit sentence length (e.g., 40; default is unlimited)
    -e encoding (e.g., 'latin1'; default 'utf8')
    -h show help

Brants, T. (1997). The NeGra Export format. CLAUS Report 98, Computational
Linguistics Department, Saarland University, Saarbruecken, Germany.

""" % sys.argv[0]
# Constants for the Export format:
NUMFIELDS = 6
WORD, LEMMA, TAG, MORPH, FUNC, PARENT = tuple(range(NUMFIELDS))
NODE = WORD  # alias for readability: non-terminal node number vs terminal


class Bracketing():
    """Represents a single bracketing by a set of terminals indices and the
    label of a non-terminal which dominates those terminals."""
    def __init__(self, label, terminals):
        self.label = label
        self.terminals = frozenset(terminals)

    def __hash__(self):
        return hash((self.label, self.terminals))

    def __eq__(self, other):
        if not isinstance(other, Bracketing):
            return False
        return self.terminals == other.terminals and self.label == other.label

    def __repr__(self):
        return 'Bracketing(%r, %r)' % (self.label, self.terminals)


def read_param(filename):
    """Read an EVALB-style parameter file and return a dictionary."""
    param = defaultdict(list)
    # NB: we ignore MAX_ERROR, we abort immediately on error.
    # only DELETE_LABEL is implemented for now.
    validkeysonce = ('DEBUG', 'MAX_ERROR', 'CUTOFF_LEN', 'LABELED',
            'DISC_ONLY', 'TED', 'DEP')
    param = {'DEBUG': 0, 'MAX_ERROR': 10, 'CUTOFF_LEN': 9999,
                'LABELED': 1, 'DELETE_LABEL_FOR_LENGTH': set(),
                'DELETE_LABEL': set(), 'DELETE_WORD': set(),
                'EQ_LABEL': set(), 'EQ_WORD': set(),
                'DISC_ONLY': 0, 'TED': 0, 'DEP': 0}
    seen = set()
    for a in io.open(filename, encoding='utf8') if filename else ():
        line = a.strip()
        if line and not line.startswith('#'):
            key, val = line.split(None, 1)
            if key in validkeysonce:
                if key in seen:
                    raise ValueError('cannot declare %s twice' % key)
                seen.add(key)
                param[key] = int(val)
            elif key in ('DELETE_LABEL', 'DELETE_LABEL_FOR_LENGTH',
                    'DELETE_WORD'):
                param[key].add(val)
            elif key in ('EQ_LABEL', 'EQ_WORD'):
                # these are given as undirected pairs (A, B), (B, C), ...
                try:
                    b, c = val.split()
                except ValueError:
                    raise ValueError('%s requires two values' % key)
                param[key].add((b, c))
            else:
                raise ValueError('unrecognized parameter key: %s' % key)
    return param


def export_split(line):
    """ Take a line in export format and split into fields,
    add dummy fields lemma. Now ignoring everything behind parent
    number, such as sec. edge and comments, because 1. secondary edges
    are generally not used in parsing, and 2. unlike defined in Brants
    (1997), in TueBa-D/Z 8 the fields in question are used for
    anaphora annotation and not for secondary edges. """ 
    if "%%" in line:  # we don't want comments.
        line = line[:line.index("%%")]
    fields = line.split()
    # if 5th field is a number (the parent number), assume that 
    # we have no lemma field
    if fields[4].isdigit():
        fields[1:1] = ['']
    fields = fields[:6]
    # check first field
    if fields[NODE].startswith('#'):
        nodenum = int(fields[NODE][1:])
        if not (nodenum == 0 or 500 <= nodenum <= 999):
            raise ValueError("node number must >= 500 and <= 999")
    # make sure the parent number is valid
    parent = int(fields[PARENT])
    if not (500 <= parent <= 999 or parent == 0):
        raise ValueError("the parent number must be "
                "0 or >= 500 and <= 999, got %s" % parent)
    return fields


def export_process_sentence(sentence, labels_by_nodenum, tuples_by_nodenum,
        pos_tags, nodenum, param, delete_pos):
    """In a syntactic tree given in export-format as a list of lines in the
    array sentence, recursively determine top-down which are the terminals
    dominated by the node with the number nodenum."""
    # get the label
    label = labels_by_nodenum[nodenum]
    # get the terminals
    tuples_by_nodenum[nodenum] = (label, set())
    for linenum, fields in enumerate(sentence):
        parent = int(fields[PARENT])
        if parent == nodenum:
            if fields[NODE].startswith('#'):
                # recursion: non-terminal
                childnum = int(fields[NODE][1:])
                export_process_sentence(sentence, labels_by_nodenum,
                        tuples_by_nodenum, pos_tags, childnum, param,
                        delete_pos)
                tuples_by_nodenum[nodenum][1].update(
                        tuples_by_nodenum[childnum][1])
            else:
                # base case: terminal
                # only add terminals with non-deleted POS tags
                if fields[TAG] not in param.get('DELETE_LABEL', ()):
                    tuples_by_nodenum[nodenum][1].add(linenum + 1)
                # for key file length calculation is based on
                # DELETE_LABEL_FOR_LENGTH
                if fields[TAG] not in param.get(delete_pos, ()):
                    pos_tags.add((linenum, fields[TAG]))


def read_from_export(filename, param, delete_pos, encoding):
    """Read a signature from an export-format file.
    Returns a dict which maps sentence numbers to lists of bracketings."""
    # will be returned
    signatures = {}
    pos_tags = {}
    # for reading export data
    within_sentence = False
    sentence = []
    # stores tuples of terminals dominated by node
    tuples_by_nodenum = {}
    for line in io.open(filename, 'r', encoding=encoding):
        line = line.strip()
        if not within_sentence:
            if line.startswith("#BOS"):
                within_sentence = True
                sentence.append(line)
        else:
            sentence.append(line)
            if line.startswith("#EOS"):
                # complete sentence collected, process it
                within_sentence = False
                # get the sentence number from the EOS line
                sent_num = int(line.split(None, 1)[1])
                # remove BOS and EOS lines, split lines into fields
                sentence = [export_split(a) for a in sentence[1:-1]]
                # extract all non-terminal labels
                labels_by_nodenum = {int(fields[NODE][1:]): fields[TAG]
                        for fields in sentence if fields[NODE].startswith('#')}
                labels_by_nodenum[0] = u"VROOT"
                # intialize bracketing store for this sentence
                signatures[sent_num] = multiset()
                pos_tags[sent_num] = set()
                # get the non-terminal labels and the terminals which the
                # corresponding nodes dominate
                export_process_sentence(sentence, labels_by_nodenum,
                        tuples_by_nodenum, pos_tags[sent_num], 0, param,
                        delete_pos)
                for nodenum in tuples_by_nodenum:
                    # the label of a nonterminal
                    label = tuples_by_nodenum[nodenum][0]
                    # the terminals dominated by this nonterminal
                    terminals = tuples_by_nodenum[nodenum][1]
                    # only add non-deleted, non-empty bracketings
                    if (label not in param.get('DELETE_LABEL', ())
                            and terminals):
                        bracketing = Bracketing(
                                label if param['LABELED'] else 'X',
                                terminals)
                        signatures[sent_num][bracketing] += 1
                # reset
                sentence = []
                tuples_by_nodenum = {}
    return signatures, pos_tags


def evaluate(key, answer, param, encoding):
    """Initiate evaluation of answer file against key file (gold)."""
    # read signature from key file
    key_sig, key_tags = read_from_export(key, param,
            "DELETE_LABEL_FOR_LENGTH", encoding)
    # read signature from answer file
    answer_sig, answer_tags = read_from_export(answer, param,
            "DELETE_LABEL", encoding)

    if not key_sig:
        raise ValueError("no sentences in key")
    if len(answer_sig) > len(key_sig):
        raise ValueError("more sentences in answer than key")
    print("""\
 sent.  prec.   rec.       F1  match   gold test words matched tags
====================================================================""")

    # missing sentences
    missing = 0
    # number of matching bracketings (labeled)
    total_match = 0
    # total number of brackets in key
    total_key = 0
    # total number of brackets in answer
    total_answer = 0
    total_exact = 0
    total_words = total_matched_pos = total_sents = 0
    # get all sentence numbers from gold
    for sent_num in sorted(key_sig):
        if len(key_tags[sent_num]) > param['CUTOFF_LEN']:
            continue
        total_sents += 1
        sent_match = 0
        # get bracketings for key
        # there must be something for every sentence in key
        if sent_num not in key_sig:
            raise ValueError("no data for sent. %d in key" % sent_num)
        key_sent_sig = key_sig[sent_num]
        # get bracketings for answer
        answer_sent_sig = None
        if sent_num in answer_sig:
            answer_sent_sig = answer_sig[sent_num]
        else:
            answer_sent_sig = multiset()
            missing += 1
        # compute matching brackets
        sent_match = sum((key_sent_sig & answer_sent_sig).values())
        if key_sent_sig == answer_sent_sig:
            total_exact += 1
        sent_answer = sum(answer_sent_sig.values())
        sent_prec = 0.0
        if len(answer_sent_sig) > 0:
            sent_prec = 100 * sent_match / sent_answer
        sent_key = sum(key_sent_sig.values())
        sent_rec = 0.0
        if len(key_sent_sig) > 0:
            sent_rec = 100 * sent_match / sent_key
        sent_fb1 = 0.0
        if sent_prec + sent_rec > 0:
            sent_fb1 = 2 * sent_prec * sent_rec / (sent_prec + sent_rec)
        tag_match = len(key_tags[sent_num] & answer_tags[sent_num])
        print("%4d  %6.2f  %6.2f  %6.2f    %3d    %3d  %3d  %3d  %3d" % (
                sent_num, sent_prec, sent_rec, sent_fb1,
                sent_match, sent_key, sent_answer, 
                len(answer_tags[sent_num]), tag_match))
        total_match += sent_match
        total_key += sent_key
        total_answer += sent_answer
        total_matched_pos += tag_match
        total_words += len(key_tags[sent_num])

    prec = 0.0
    if total_answer > 0:
        prec = 100 * total_match / total_answer
    rec = 0.0
    if total_key > 0:
        rec = 100 * total_match / total_key
    fb1 = 0.0
    if prec + rec > 0:
        fb1 = 2 * prec * rec / (prec + rec)

    labeled = ('unlabeled', 'labeled')[param['LABELED']]
    print("===========================================================")
    print()
    print()
    print("Summary (%s, <= %d):" % (labeled, param['CUTOFF_LEN']))
    print("===========================================================")
    print()
    print("Sentences in key".ljust(30), ":", total_sents)
    print("Sentences missing in answer".ljust(30), ":", missing)
    print()
    print("Total edges in key".ljust(30), ":", total_key)
    print("Total edges in answer".ljust(30), ":", total_answer)
    print("Total matching edges".ljust(30), ":", total_match)
    print()
    print("POS : %6.2f %%" % (100 * total_matched_pos / total_words))
    print("%sP  : %6.2f %%" % (labeled[0].upper(), prec))
    print("%sR  : %6.2f %%" % (labeled[0].upper(), rec))
    print("%sF1 : %6.2f %%" % (labeled[0].upper(), fb1))
    print("EX  : %6.2f %%" % (100 * total_exact / total_sents))


def main():
    """Run bracketing evaluation on two export-format files"""
    try:
        opts, args = getopt.getopt(sys.argv[1:], "huk:a:p:e:l:",
            ["help", "unlabeled", "key=", "answer=", "param=", "encoding=",
                "limit="])
        opts = dict(opts)
    except getopt.GetoptError as err:
        sys.stderr.write(str(err) + "\n")
        print(USAGE)
        sys.exit(1)
    if args:
        print("unexpected argument")
        print(USAGE)
        sys.exit(1)
    keyfile = answerfile = paramfile = None
    if "-h" in opts or "--help" in opts:
        print(USAGE)
        sys.exit()
    keyfile = opts.get("-k", opts.get("--key"))
    answerfile = opts.get("-a", opts.get("--answer"))
    paramfile = opts.get("-p", opts.get("--param"))
    # Export is formally latin1, but let's promote utf8 proliferation
    encoding = opts.get("-e", opts.get("--encoding", "utf8"))
    if keyfile is None or answerfile is None:
        raise ValueError("you must provide both a key and an answer file")
    param = read_param(paramfile)
    if "-u" in opts or "--unlabeled" in opts:
        param['LABELED'] = 0
    if "-l" in opts or "--limit" in opts:
        param['CUTOFF_LEN'] = int(opts.get("--limit", opts["-l"]))
    evaluate(keyfile, answerfile, param, encoding)

if __name__ == "__main__":
    main()
