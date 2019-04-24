#! /bin/bash
# /dev/stdin: file one
# $1: file two
# $2: n-lines

cat /dev/stdin | head -n $2 | diff --strip-trailing-cr -u -w - <(head -n $2 $1) 
# watch -t -d -n 1 "python ../syntax_analyser.py Square.jack | diff --strip-trailing-cr -u -w - Square.xml"
