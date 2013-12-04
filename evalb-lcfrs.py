#!/usr/bin/python
""" Evaluation of discontinuous bracketings. See USAGE. """

# Authors: Wolfgang Maier <maierw@hhu.de>,
# Andreas van Cranenburgh <a.w.vancranenburgh@uva.nl>

# Version: December 04, 2013

from __future__ import print_function, division
import io
import sys
import getopt
from collections import defaultdict, Counter  # multiset implementation

USAGE = """Usage: %s [OPTIONS]

Extension of the evalb program, to evaluate discontinuous constituency trees.
In the absence of discontinuity,this program should yield the same results as
evalb, but you should check that for yourself. This program returns
precision, recall, f-measure and exact match. It expects its input data to be
in export format (Brants 1997).

Comparsion is done on the basis of "signatures", sets of bracketings
for non-terminals. Tagging accuracy is not evaluated.
To match the sentences which are to be compared, the program uses the
export sentence numbering. Missing sentences in answer affect the result.

[OPTIONS]
    -k key file (gold data)
    -a answer file (parser output)
    -p evalb parameter file (optional)
    -u unlabeled evaluation
    -e encoding (e.g., 'latin1'; default 'utf8')
    -h show help

Brants, T. (1997). The NeGra Export format. CLAUS Report 98, Computational
Linguistics Department, Saarland University, Saarbruecken, Germany.

""" % sys.argv[0]
#    -l limit sentence length (e.g., 40; default is unlimited)
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
    param = {'DEBUG': 0, 'MAX_ERROR': 10, 'CUTOFF_LEN': 40,
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
                assert key not in seen, 'cannot declare %s twice' % key
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


def exportsplit(line):
    """ Take a line in export format and split into fields,
    add dummy fields lemma, sec. edge if those fields are absent. """
    if "%%" in line:  # we don't want comments.
        line = line[:line.index("%%")]
    fields = line.split()
    fieldlen = len(fields)
    if fieldlen == 5:
        fields[1:1] = ['']
        fields.extend(['', ''])
    elif fieldlen == 6:
        fields.extend(['', ''])
    elif fieldlen < 8 or fieldlen & 1:
        # NB: zero or more sec. edges come in pairs of parent id and label
        raise ValueError(
                'expected 5 or 6+ even number of columns: %r' % fields)
    return fields


def export_check_line(line):
    """Checks some properties of a splitted export format node line"""
    # make sure there were enough fields
    assert len(line) > 4, "line seems to be lacking fields: " + line
    # check first field
    if line[NODE].startswith('#'):
        assert len(line[NODE]) == 4 and line[NODE][1:].isdigit(), (
            "first field looks wrong: " + line)
    # make sure the parent number is three digits long
    assert line[PARENT].isdigit(), (
            "6th field must contain parent number: %s" % line)
    # make sure it's usable
    parent = int(line[PARENT])
    assert parent >= 500 or parent == 0, ("the parent number must be "
            ">= 500 or = 0, got %s" % parent)


def export_process_sentence(sentence, labels_by_nodenum, tuples_by_nodenum,
        nodenum, param):
    """In a syntactic tree given in export-format as a list of lines in the
    array sentence, recursively determine top-down which are the terminals
    dominated by the node with the number nodenum."""
    # make sure the node number refers a non-terminal
    assert nodenum == 0 or nodenum >= 500
    # get the label
    label = labels_by_nodenum[nodenum]
    # get the terminals
    tuples_by_nodenum[nodenum] = (label, set())
    for linenum, line in enumerate(sentence):
        fields = exportsplit(line)
        export_check_line(fields)
        parent = int(fields[PARENT])
        if parent == nodenum:
            if fields[NODE].startswith('#'):
                # recursion: non-terminal
                childnum = int(fields[NODE][1:])
                export_process_sentence(sentence, labels_by_nodenum,
                        tuples_by_nodenum, childnum, param)
                tuples_by_nodenum[nodenum][1].update(
                        tuples_by_nodenum[childnum][1])
            elif fields[TAG] not in param.get('DELETE_LABEL', ()):
                # base case: terminal
                # only add terminals with non-deleted POS tags
                tuples_by_nodenum[nodenum][1].add(linenum + 1)


def read_from_export(filename, param, encoding='utf8'):
    """Read a signature from an export-format file.
    Returns a dict which maps sentence numbers to lists of bracketings."""
    # will be returned
    result = {}
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
                sentnum = int(line.split(None, 1)[1])
                # remove BOS and EOS lines
                sentence = sentence[1:-1]
                # extract all non-terminal labels
                labels_by_nodenum = dict(
                        (int(exportsplit(nodeline)[NODE][1:]),
                        exportsplit(nodeline)[TAG])
                        for nodeline in sentence
                        if nodeline.startswith('#'))
                labels_by_nodenum[0] = u"VROOT"
                # intialize bracketing store for this sentence
                result[sentnum] = Counter()
                # get the non-terminal labels and the terminals which the
                # corresponding nodes dominate
                export_process_sentence(sentence, labels_by_nodenum,
                        tuples_by_nodenum, 0, param)
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
                        result[sentnum][bracketing] += 1
                # reset
                sentence = []
                tuples_by_nodenum = {}
    return result


def evaluate(k, a, param, encoding):
    """Initiate evaluation of answer file ``a``
    against key file (gold) ``k``."""
    # read signature from key file
    key_sig = read_from_export(k, param, encoding)
    # read signature from answer file
    answer_sig = read_from_export(a, param, encoding)

    assert len(key_sig) > 0, "no sentences in key"
    assert len(answer_sig) <= len(key_sig), "more sentences in answer than key"
    print("""
 sent.  prec.   rec.       F1  match   gold test
=================================================
""", end='')

    # missing sentences
    missing = 0
    # number of matching bracketings (labeled)
    total_match = 0
    # total number of brackets in key
    total_key = 0
    # total number of brackets in answer
    total_answer = 0
    exact = 0
    #total_words = matched_pos = 0
    # get all sentence numbers from gold
    for sent_num in sorted(key_sig):
        sent_match = 0
        # get bracketings for key
        # there must be something for every sentence in key
        assert sent_num in key_sig, (
                "no data for sent. %d in key" % sent_num)
        key_sent_sig = key_sig[sent_num]
        # get bracketings for answer
        answer_sent_sig = None
        if sent_num in answer_sig:
            answer_sent_sig = answer_sig[sent_num]
        else:
            answer_sent_sig = Counter()
            missing += 1
        # compute matching brackets
        sent_match = len(key_sent_sig & answer_sent_sig)
        if key_sent_sig == answer_sent_sig:
            exact += 1
        sent_prec = 0.0
        if len(answer_sent_sig) > 0:
            sent_prec = 100 * sent_match / len(answer_sent_sig)
        sent_rec = 0.0
        if len(key_sent_sig) > 0:
            sent_rec = 100 * sent_match / len(key_sent_sig)
        sent_fb1 = 0.0
        if sent_prec + sent_rec > 0:
            sent_fb1 = 2 * sent_prec * sent_rec / (sent_prec + sent_rec)
        print("%4d  %6.2f  %6.2f  %6.2f    %3d    %3d  %3d" % (
                sent_num, sent_prec, sent_rec, sent_fb1,
                sent_match, len(key_sent_sig), len(answer_sent_sig)))
        total_match += sent_match
        total_key += len(key_sent_sig)
        total_answer += len(answer_sent_sig)

    prec = 0.0
    if total_answer > 0:
        prec = 100 * total_match / total_answer
    rec = 0.0
    if total_key > 0:
        rec = 100 * total_match / total_key
    fb1 = 0.0
    if prec + rec > 0:
        fb1 = 2 * prec * rec / (prec + rec)

    print("=================================================")
    print()
    print()
    print("Summary: ")
    print("=========")
    print()
    print("Sentences missing in answer    :", missing)
    print()
    print("Total edges in key             :", total_key)
    print("Total edges in answer          :", total_answer)
    print("Total matching edges           :", total_match)
    print()
    #print("POS  : %6.2f " % (100 * matched_pos / total_words))
    labeled = 'UL'[param['LABELED']]
    print("%sP  : %6.2f %%" % (labeled, prec))
    print("%sR  : %6.2f %%" % (labeled, rec))
    print("%sF1 : %6.2f %%" % (labeled, fb1))
    print("EX  : %6.2f %%" % (100 * exact / len(key_sig)))


def main():
    """Run bracketing evaluation on two export-format files"""
    try:
        opts, args = getopt.getopt(sys.argv[1:], "huk:a:p:e:l:",
            ["help", "unlabeled", "key=", "answer=", "param=", "encoding=",
                "limit="])
        assert len(args) == 0
    except getopt.GetoptError as err:
        sys.stderr.write(str(err) + "\n")
        print(USAGE)
        sys.exit(1)
    keyfile = answerfile = paramfile = None
    # Export is formally latin1, but let's promote utf8 proliferation
    encoding = 'utf8'
    for opt, val in opts:
        if opt in ("-h", "--help"):
            print(USAGE)
            sys.exit()
        elif opt in ("-k", "--key"):
            keyfile = val
        elif opt in ("-a", "--answer"):
            answerfile = val
        elif opt in ("-p", "--param"):
            paramfile = val
        elif opt in ("-e", "--encoding"):
            encoding = val
    assert keyfile is not None and answerfile is not None, (
            "you must provide both a key and an answer file")
    param = read_param(paramfile)
    if "-u" in opts or "--unlabeled" in opts:
        param['LABELED'] = 0
    #if "-l" in opts or "--limit" in opts:
    #    param['CUTOFF_LEN'] = int(val)
    evaluate(keyfile, answerfile, param, encoding)

if __name__ == "__main__":
    main()
