#!/usr/bin/python

# -*- coding: utf-8 -*-

# Author: Wolfgang Maier <maierw@hhu.de>

# Extension of the evalb program, to evaluate the output of a PLCFRS parser.
# In the context-free case, this program should yield the same results as
# evalb, but you should check that for yourself. This program returns 
# only recall, precision and f-measure. It expects its input data to be in 
# export format (Brants 1997) V3 (no lemma field).
#
# Comparsion is done on the basis of "signatures", sets of bracketings
# for non-terminals. Tagging is not evaluated.
# To match the sentences which are to be compared, the program uses the export
# sentence numbering

# Version: October 17, 2011

import sys
import getopt

class Bracket():
    """Represents a single bracket by list of terminals and the label of a 
    non-terminal which dominates those terminals. The result field is 
    for bookkeeping during evaluation"""
    def __init__(self, label, terminals):
        self.label = label
        self.terminals = terminals
        self.result = False
        self.result_u = False

    def labeled_equals(self, other):
        return self.unlabeled_equals(other) and self.label == other.label

    def unlabeled_equals(self, other):
        if not isinstance(other, Bracket):
            return false
        return self.terminals == other.terminals

def export_check_line(line):
    """Checks some properties of a splitted export format node line"""
    # make sure there were enough fields
    assert len(line) > 4, "line seems to be lacking fields: " + line
    # check first field 
    if line[0].startswith('#'):
        assert len(line[0]) == 4 and line[0][1:].isdigit(), \
            "first field looks wrong: " + line
    # make sure the parent number is three digits long
    assert line[4].isdigit(), "5th field must contain parent number: " + line
    # make sure it's usable
    parent = int(line[4])
    assert parent >= 500 or parent == 0, "the parent number must be "\
        + ">= 500 or = 0, got " + str(parent)
    

def export_process_sentence(sentence, labels_by_nodenum, tuples_by_nodenum, 
                            nodenum):
    """In a syntactic tree given in export-format as a list of lines in the 
    array sentence, recursively determine top-down which are the terminals
    dominated by the node with the number nodenum."""
    # make sure the node number refers a non-terminal
    assert nodenum == 0 or nodenum >= 500
    # get the label
    label = labels_by_nodenum[nodenum]
    # get the terminals
    tuples_by_nodenum[nodenum] = (label, [])
    for linenum in range(len(sentence)):
        line = sentence[linenum].split()
        export_check_line(line)
        parent = int(line[4])
        if parent == nodenum:
            if line[0].startswith('#'):
                # recursion: non-terminal
                childnum = int(line[0][1:])
                export_process_sentence(sentence, labels_by_nodenum, 
                                        tuples_by_nodenum, childnum)
                tuples_by_nodenum[nodenum][1].\
                    extend(tuples_by_nodenum[childnum][1])
            else:
                # base case: terminal
                tuples_by_nodenum[nodenum][1].append(linenum + 1)
    
def read_from_export(filename):
    """Read a signature from an export-format file. Checks for word equality.
    Returns a dict which maps sentence numbers on lists of brackets."""
    # will be returned
    result = {}
    # for reading export data
    within_sentence = False
    sentence = []
    # stores tuples of terminals dominated by node
    tuples_by_nodenum = {}
    with open(filename, 'r') as f:
        for line in f.readlines():
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
                    sentnum = int(line.split()[1])
                    # remove BOS and EOS lines
                    sentence = sentence[1:-1]
                    # extract all non-terminal labels
                    labels_by_nodenum = dict([(int(nodeline.split()[0][1:]), 
                                               nodeline.split()[1]) 
                                              for nodeline in sentence
                                              if nodeline.startswith('#')])
                    labels_by_nodenum[0] = "VROOT"
                    # intialize bracketing store for this sentence
                    result[sentnum] = []
                    # get the non-terminal labels and the terminals which the
                    # corresponding nodes dominate
                    export_process_sentence(sentence, labels_by_nodenum, 
                                            tuples_by_nodenum, 0)
                    for nodenum in tuples_by_nodenum:
                        # the label of a nonterminal
                        label = tuples_by_nodenum[nodenum][0]
                        # the terminals dominated by this nonterminal
                        terminals = tuples_by_nodenum[nodenum][1]
                        terminals.sort()
                        result[sentnum].append(Bracket(label, terminals))
                    # reset
                    sentence = []
                    tuples_by_nodenum = {}
    return result

def evaluate(k, a):
    """Initiate evaluation of answer file a against key file (gold) k."""
    # read signature from key file
    key_sig = read_from_export(k)
    # read signature from answer file
    answer_sig = read_from_export(a)

    assert len(key_sig) > 0, "no sentences in key"
    assert len(answer_sig) <= len(key_sig), "more sentences in answer than key"
    print\
"""
 sent. prec.  rec.   fb1     uprec.  urec. ufb1    match umatch  gold  test
============================================================================"""

    # missing sentences
    missing = 0
    # number of matching bracketings (labeled)
    total_match = 0
    # number of matching bracketings (unlabeled)
    total_match_u = 0
    # total number of brackets in key 
    total_key = 0
    # total number of brackets in answer
    total_answer = 0
    # get all sentence numbers from gold
    for sent_num in range(1, len(key_sig) + 1):
        sent_match = 0
        sent_match_u = 0
        sent_key = 0
        sent_answer = 0
        # get bracketings for key
        # there must be something for every sentence in key
        assert sent_num in key_sig, "no data for sent. " + str(sent_num) \
            + "in key"
        key_sent_sig = key_sig[sent_num]
        # get bracketings for answer
        answer_sent_sig = None
        if sent_num in answer_sig:
            answer_sent_sig = answer_sig[sent_num]
        else:
            answer_sent_sig = []
            missing += 1
        # compute matching brackets
        for key_brack_ind in range(len(key_sent_sig)):
            key_brack = key_sent_sig[key_brack_ind]
            for answer_brack_ind in range(len(answer_sent_sig)):
                answer_brack = answer_sent_sig[answer_brack_ind]
                if key_brack.labeled_equals(answer_brack) \
                        and not key_brack.result \
                        and not answer_brack.result:
                    answer_sent_sig[answer_brack_ind].result = True
                    key_sent_sig[key_brack_ind].result = True
                    sent_match += 1
                if key_brack.unlabeled_equals(answer_brack) \
                        and not key_brack.result_u \
                        and not answer_brack.result_u:
                    answer_sent_sig[answer_brack_ind].result_u = True
                    key_sent_sig[key_brack_ind].result_u = True
                    sent_match_u += 1
        sent_prec = 0.0
        if len(answer_sent_sig) > 0:
            sent_prec = 100 * (sent_match / float(len(answer_sent_sig)))
        sent_rec = 0.0
        if len(key_sent_sig) > 0:
            sent_rec = 100 * (sent_match / float(len(key_sent_sig)))
        sent_fb1 = 0.0
        if sent_prec + sent_rec > 0:
            sent_fb1 = 2 * sent_prec * sent_rec / (sent_prec + sent_rec)
        sent_uprec = 0.0
        if len(answer_sent_sig) > 0:
            sent_uprec = 100 * (sent_match_u / float(len(answer_sent_sig)))
        sent_urec = 0.0
        if len(key_sent_sig) > 0:
            sent_urec = 100 * (sent_match_u / float(len(key_sent_sig)))
        sent_ufb1 = 0.0
        if sent_uprec + sent_urec > 0:
            sent_ufb1 = 2 * sent_uprec * sent_urec / (sent_uprec + sent_urec)
        print "%4d %6.2f %6.2f %6.2f   %6.2f %6.2f %6.2f    %3d    %3d    %3d  %3d" % \
            (sent_num, sent_prec, sent_rec, sent_fb1,\
                 sent_uprec, sent_urec, sent_ufb1,\
                 sent_match, sent_match_u,\
                 len(key_sent_sig), len(answer_sent_sig))
        total_match += sent_match
        total_match_u += sent_match_u
        total_key += len(key_sent_sig)
        total_answer += len(answer_sent_sig)

    prec = 0.0
    if total_answer > 0:
        prec = 100 * (total_match / float(total_answer))
    rec = 0.0
    if total_key > 0:
        rec = 100 * (total_match / float(total_key))
    fb1 = 0.0
    if prec + rec > 0:
        fb1 = (2 * prec * rec / (prec + rec)) 
    uprec = 0.0
    if total_answer > 0:
        uprec = 100 * (total_match_u / float(total_answer))
    urec = 0.0
    if total_key > 0:
        urec = 100 * (total_match_u / float(total_key))
    ufb1 = 0.0
    if uprec + urec > 0:
        ufb1 = (2 * uprec * urec / (uprec + urec)) 

    print "=======================================" \
        + "====================================="
    print
    print
    print "Summary: "
    print "========="
    print
    print "Sentences missing in answer    :", missing
    print
    print "Total edges in key             :", total_key
    print "Total edges in answer          :", total_answer
    print "Total matching edges (labeled) :", total_match
    print "Total matching edges (unlab.)  :", total_match_u
    print
    print "LP  : %6.2f " % prec
    print "LR  : %6.2f " % rec
    print "LF1 : %6.2f " % fb1
    print "UP  : %6.2f " % uprec
    print "UR  : %6.2f " % urec
    print "UF1 : %6.2f " % ufb1


def usage():
    """Print usage information"""
    print """ Usage: evalb-lcfrs.py [OPTIONS]

    Extension of the evalb program, to evaluate the output of a PLCFRS parser.
    In the context-free case, this program should yield the same results as
    evalb, but you should check that for yourself. This program returns 
    only recall, precision and f-measure. It expects its input data to be in 
    export format (Brants 1997).

    Comparsion is done on the basis of "signatures", sets of bracketings
    for non-terminals. Tagging is not evaluated.
    To match the sentences which are to be compared, the program uses the export
    sentence numbering, missing sentences in answer affect the result.

    [OPTIONS]
        -k key file (gold data)
        -a answer file (parser output)
        -h show help
    
    Brants, T. (1997). The NeGra Export format. CLAUS Report 98, Compu-
    tational Linguistics Department, Saarland University, Saarbruecken, Ger-
    many.

    """

def main():
    """Run parenthesis evaluation on two export-format files"""
    try:
        opts, args = getopt.getopt(sys.argv[1:], "hk:a:", 
                                   ["help", "key=", "answer="])
    except getopt.GetoptError, err:
        sys.stderr.write(str(err) + "\n")
        usage()
        sys.exit(1)
    keyfile = None
    answerfile = None
    for o, a in opts:
        if o in ("-h", "--help"):
            usage()
            sys.exit()
        elif o in ("-k", "--key"):
            keyfile = a
        elif o in ("-a", "--answer"):
            answerfile = a
        else:
            assert False, "unhandled option"
    assert not (keyfile == None or answerfile == None), \
    "you must provide both a key and an answer file"
    evaluate(keyfile, answerfile)
    

if __name__ == "__main__":
    main()
