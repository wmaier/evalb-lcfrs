evalb-lcfrs
===========

Description
-----------

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

Installation
------------

You can install the script by typing 

    $ python setup.py install --user

If you have super user privileges and want to perform a system-wide
installation, omit the `--user` option.


Version and License
-------------------

Current version (check git tags) is from January 24, 2014. The program
is licensed under GPL V2.
