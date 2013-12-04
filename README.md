evalb-lcfrs
===========

Authors: Wolfgang Maier <maierw@hhu.de>,
Andreas van Cranenburgh <a.w.vancranenburgh@uva.nl>

Extension of the evalb program, to evaluate the output of a PLCFRS parser.
In the context-free case, this program should yield the same results as
evalb, but you should check that for yourself. This program returns 
only recall, precision and f-measure. It expects its input data to be in 
export format (Brants 1997) V3 (no lemma field).

Comparsion is done on the basis of "signatures", sets of bracketings
for non-terminals. Tagging is not evaluated. To match the sentences which 
are to be compared, the program uses the export sentence numbering.

Current version (check git tags) is from December 04, 2013. The program
is licensed under GPL V2.  