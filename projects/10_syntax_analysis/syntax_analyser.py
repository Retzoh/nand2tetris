"""Syntax analyzer for the jack language.

Usage:

python syntax_analyser.py path

If `path` is a jack file: directly outputs the analyzed syntax in xml format
If `path` is a folder: scans it for `.jack` files and outputs their analyzed
syntaxes in respective `.comp.xml` files.

Each file should contain one jack class having the same name as the file. 

The analyser is based on the concept of "eaters":
Given a list of elements, a eater scans them progressively while a specific rule
is satisfied. The elements following the rule are "eated" away from the initial 
list and processed. Eventually, the eater returns a tuple containing the result 
of the processing and the leftovers.

The initial jack code is eated once on a character basis to produce tokens. A 
second pass eats the tokens to produce the syntax analysis.

This file is organized in parts following those stages:

File parsing (line 99)
Tokens (line 147)
Utilities (line 285)
Structure (line 423)
Statements (line 603)
Expressions (line 789)
Analysis (line 966)

# Jack syntax specifications:

Notations:
`placeholder*`: `placeholder` may be present 0, 1 or more times
`placeholder?`: `placeholder` may be present 0 or 1 time
`placeholder1|placeholder2`: one of `placeholder1` and `placeholder2` is present

## Tokens
identifier:
    A sequence of letters, digits and underscores ('_') not starting with a 
    digit.
keyword:
    'class' | 'constructor' | 'function' | 'method' | 'field' | 'static' | 'var'
    | 'int' | 'char' | 'boolean' | 'void' | 'true' | 'false' | 'null' | 'this' 
    | 'let' | 'do' | 'if' | 'else' | 'while' | 'return'
 symbol:
    '{' | '}' | '(' | ')' | '[' | ']' | '.' | ',' | ';' | '+' | '-' | '*' | '/' 
    | '&' | '|' | '<' | '>' | '=' | '~'
    '&', '<', '>' will be parsed as resp. '&amp;', '&lt;', 'gt;'
stringConstant: 
    '"' a sequence of Unicode characters, not including double quote or 
    newline '"'
    In token form, the enclosing '"' are omitted.
integerConstant: a integer in the range 0...32767
keywordConstant: 'true'|'false'|'null'|'this'

## Structure
className: identifier
varName: identifier
subroutineName: identifier
type: 'int'|'char'|'boolean'|className

class: 'class' className '{' classVarDec*, subroutineDec* '}'
classVarDec: ('static'|'field') type varName (',' varName)* ';'
subroutineDec:
    ('constructor'|'function'|'method') ('void'|type) subroutineName
    '(' parameterList ')' subroutineBody
parameterList: ((type varName) (',' type varName)*)?
subroutineBody: '{' varDec* statements '}'
varDec: 'var' type varName (',' varName)* ';'

## Statements
statements: statement*
statement: ifStatement|whileStatement|letStatement|doStatement|returnStatement
ifStatement: 
    'if' '(' expression ')’ '{' statements '}’ (else '{' statements '})?
whileStatement: 'while' '(' expression ')’ '{' statements '}’
letStatement: 'let' varName '=' expression ';'
doStatement: 'do' subroutineCall ';'
returnStatement: 'return' expression? ';'

## Expressions
expressionList: (expression (',' expression)*)?
expression: terp (op term)*
op: '+'|'-'|i'*'|'/'|'&'|'|'|'='|'>'|'<'
unaryOp: '-'|'~'
subroutineCall: subroutineName '(' expressionList ')'
    | (className|varName)'.'subroutineName'('expressionList')'
term: integerConstant | stringConstant | keywordConstant | varName
    | varName'['expression']' | subroutineCall | '('expression')' | unaryOp term
"""
import re
import sys
from pathlib import Path


##############
# File parsing
##############


def read_file(path):
    """Read file into a string and preprocess it

    Preprocessing includes:
    * Remove block comments : /* ... */ (possibly spanning multiple lines)
    * Remove line comments : // ... END_OF_LINE
    * Merge all lines together
    """
    def read_caracters():
        return Path(path).expanduser().read_text()

    def remove_block_coments(string):
        """Remove block comments by replacing them with an empty string

        Matches string that:
        * Start with /*: `/\*`
        * Containing any caracters, including new lines...: `(.|\s)`
        * ...0, 1 or multiple times but look for the smallest set: `(...*?)`
        * And end with */: `\*/`
        """
        return re.sub('/\*((.|\s)*?)\*/', '', string)

    def remove_line_comments(string):
        """Remove line comments by replacing them with a new line character
        
        Matches string that:
        * Start with //: `//`
        * Containing any caracters except new lines...: `.`
        * ...0, 1 or multiple times but look for the smallest set: `(...*?)`
        * And end with a new line: `\n`
        """
        return re.sub('//(.*?)\n', '\n', string)

    def remove_new_lines(string):
        """Remove new lines by replacing them with an empty string"""
        return re.sub('(\r)?\n', '', string)

    return remove_new_lines(
        remove_line_comments(
            remove_block_coments(
                read_caracters())))


########
# Tokens
########


def is_blank(c):
    """Test if one character is blank"""
    return re.match('\s', c) is not None


def is_symbol(c):
    """Test if one character is a symbol"""
    return c in {'{',  '}',  '(',  ')',  '[',  ']',  '.',  
        ',',  ';',  '+',  '-',  '*',  '/',  '&',  '|',  '<',  
        '>',  '=',  '~'}


def is_integer(c):
    """Test if one character is an integer"""
    try:
        int(c)
        return True
    except ValueError:
        return False


def is_string(c):
    """Test if one character delimits the start or end of a string"""
    return c=='"'


def is_keyword(string):
    """Test if a string is a keyword"""
    return string in {'class',  'constructor',  'function',  'method',  
        'field',  'static',  'var',  'int',  'char',  'boolean',  
        'void',  'true',  'false',  'null',  'this',  'let',  'do',  
        'if',  'else',  'while',  'return'}


def is_identifier_char(c):
    """Test if a character is valid inside an identifier definition"""
    return re.match('[_\w]', c) is not None


def eat_char(chars):
    """Return the first character of a string, and the rest"""
    return chars[0], chars[1:]


def eat_integer(chars, first_digit):
    """Eat an integerConstant

    integerConstant: a integer in the range 0...32767
    """
    if not is_integer(chars[0]):
        return first_digit, chars
    i=1
    while is_integer(chars[i]):
        i += 1
    if int(first_digit+chars[:i]) > 32767:
        raise ValueError(f"Found an integerConstant greater than 32767, which "
        f"is the maximum: `{first_digit+chars[:i]}`.")
    return first_digit+chars[:i], chars[i:]


def eat_string(chars):
    """Eat a stringConstant

    stringConstant: 
        '"' a sequence of Unicode characters, not including double quote or 
        newline '"'
        In token form, the enclosing '"' are omitted.
    """
    i=0
    while chars[i] != '"':
        i += 1
    return chars[:i], chars[i+1:]


def eat_identifier_or_keyword(chars, first_char):
    """Eat a identifier or keyword

    identifier:
        A sequence of letters, digits and underscores ('_') not starting with a 
        digit.
    keyword:
        'class' | 'constructor' | 'function' | 'method' | 'field' | 'static' 
        | 'var' | 'int' | 'char' | 'boolean' | 'void' | 'true' | 'false' 
        | 'null' | 'this' | 'let' | 'do' | 'if' | 'else' | 'while' | 'return'
    """
    if not is_identifier_char(chars[0]):
        return first_char, chars
    i=1
    while is_identifier_char(chars[i]):
        i += 1
    return first_char+chars[:i], chars[i:]


def format_token(word, token_type):
    """Return an xml representation of `word`, with the tag `token_type`"""
    return f'<{token_type}> {word} </{token_type}>'


def tokenize(chars):
    """Recognize and split the individual tokens in `chars`

    Eats `chars` progressively, one character at a time.
    Infer the type of the current token from its first character and eat the 
    rest of it.

    The tokens are then returned as a list of xml lines: `<type> token </type>`
    """
    tokens=[]
    token_type=None
    left=""
    while len(chars) > 0:
        c, chars = eat_char(chars)
        if is_blank(c):
            continue
        if is_symbol(c):
            tokens += [format_token(c, 'symbol')]
            continue
        if is_integer(c):
            word, chars = eat_integer(chars, c)
            tokens += [format_token(word, 'integerConstant')]
            continue
        if is_string(c):
            word, chars = eat_string(chars)
            tokens += [format_token(word, 'stringConstant')]
            continue
        word, chars = eat_identifier_or_keyword(chars, c)
        if is_keyword(word):
            tokens += [format_token(word, 'keyword')]
        else:
            tokens += [format_token(word, 'identifier')]
    return tokens


###########
# Utilities
###########


def indent(token, level=1):
    "Inent a token to specified level with 2 space tabs"""
    return ' '*2*level + token


def is_of_type(t, token):
    """Test if a token is of desired type"""
    return (token.split('<')[1].split('>')[0] == t 
        and token.split('</')[1].split('>')[0] == t)

def delay_token_application(f):
    """Decorate f to make it a "delayed" function waiting for tokens"""
    def helper(*args, **kwargs):
        return lambda tokens: f(tokens, *args, **kwargs)
    return helper


@delay_token_application
def eat_by_value(tokens, expected_value, expected_type, n_indent=1, 
        optional=False):
    """Eat the specified token from `tokens` and indent it.
    
    Individual tokens are parsed following the "<type> value </type>" format.

    To recognise the "|" value, "&OR" should be specified.

    Args:
        tokens (list): tokens left in the current class
        expected_value (str): desired token value. Multiple acceptable values 
            can be specified with a pipe "|" separator. To recognize the "|" 
            value, "&OR" should be specified.
        expected_type (str): desired token type. Only one type may be specified.
        n_indent(int): desired indent level
        optional (bool, default=False): Action to do if desired token is not 
            present: If True, return None, else raise an error
    Returns:
        (indented_token, rest of the tokens)
    """
    values = [v.replace('&OR', '|') for v in expected_value.split('|')]
    if not any([tokens[0] == format_token(v, expected_type) for v in values]):
        if optional:
            return None, tokens
        raise ValueError(f'Expected {expected_value} {expected_type}'
            f' found {tokens[0]}')
    return [indent(tokens[0], n_indent)], tokens[1:]


@delay_token_application
def eat_by_type(tokens, expected_type, n_indent=1, optional=False):
    """Eat the specified token from `tokens` and indent it.
    
    Individual tokens are parsed following the "<type> value </type>" format.

    Args:
        tokens (list): tokens left in the current class
        expected_type (str): desired token type. Multiple types may be 
            specified, separated with pipes "|".
        n_indent(int): desired indent level
        optional (bool, default=False): Action to do if desired token is not 
            present: If True, return None, else raise an error
        Returns:
            (indented_token, rest of the tokens)
    """
    types = expected_type.split('|')
    if not any([is_of_type(t, tokens[0]) for t in types]):
        if optional:
            return None, tokens
        raise ValueError(f'expected token of type {expected_type}, found '
            f'{tokens[0]}')
    return [indent(tokens[0], n_indent)], tokens[1:]


@delay_token_application
def apply_eaters(tokens, *eaters, break_on_none=True):
    """Apply specified eaters, break on `None` returns"""
    eated_tokens = []
    for eater in eaters:
        newly_eated, tokens = eater(tokens)
        if newly_eated is None:
            if break_on_none: break
            else: continue
        eated_tokens += newly_eated
    return (eated_tokens if len(eated_tokens)>0 else None), tokens


@delay_token_application
def eat_until_none(tokens, *eaters):
    """Apply specified eaters cyclically until a `None` value is returned"""
    eated_tokens = []
    for eater in eaters:
        newly_eated, tokens = eater(tokens)
        if newly_eated is None: break
        eated_tokens += [newly_eated]
    while newly_eated is not None:
        for eater in eaters:
            newly_eated, tokens = eater(tokens)
            if newly_eated is None: break
            eated_tokens += [newly_eated]
    return sum(eated_tokens, []), tokens


def indented_tag(tag_name, expand_none=False):
    """Wrapping the tokens eated by the decorated function in desired meta-token

    Ex: applied on `eat_class` with the "class" tag name, cat following outputs:
    '''
    class_token_start
    ...
    class_token_end
    '''
    And turn them into:
    '''
    <class>
      class_token_start
      ...
      class_token_end
    </class>
    """
    def decorator(f):
        def helper(tokens, n_indent, *args, **kwargs):
            xml_lines, tokens = f(tokens, n_indent+1, *args, **kwargs)
            if xml_lines is None and expand_none:
                xml_lines = []
            if xml_lines is None:
                return None, tokens
            return (
                [indent(f'<{tag_name}>', n_indent)] + 
                xml_lines + 
                [indent(f'</{tag_name}>', n_indent)]), tokens
        return helper
    return decorator


###########
# Structure
###########


@delay_token_application
def eat_type(tokens, n_indent, existing_classes, optional=False):
    """Eat a token corresponding to a type

    Recognized syntax:
    'int'|'char'|'boolean'|className

    First tries to eat one of the pre-defined types (int / char / boolean).
    If unsuccessful, look for user-defined classes.
    """
    t, tokens =  eat_by_value('int|char|boolean|void','keyword', n_indent, 
        optional=True)(tokens)
    if t is not None: return t, tokens
    return eat_by_value('|'.join(existing_classes), 'identifier', n_indent, 
        optional=optional)(tokens)


@indented_tag('class')
def eat_class(tokens, n_indent, existing_classes):
    """Eat tokens corresponding to a class declaration
    
    Recognized syntax:
    'class' className '{' classVarDec*, subroutineDec* '}'
    
    Args:
        tokens (list): tokens to analyse a class declaration from
        n_indent (int): desired indent level (kept for compatibility with 
            the indented_tag decorator)
        existing_classes (list): list of class names existing in the scope of
            the program. They should thus be recognized as valid data types.
    Returns:
        (indented tokens of the declaration, other tokens)
    """
    return apply_eaters( 
        eat_by_value('class', 'keyword',n_indent),
        eat_by_type('identifier', n_indent),
        eat_by_value('{', 'symbol', n_indent),
        eat_until_none(eat_class_var_dec(n_indent, existing_classes)),
        eat_until_none(eat_sub_routine_dec(n_indent, existing_classes)),
        eat_by_value('}', 'symbol', n_indent))(tokens)


@delay_token_application
@indented_tag('classVarDec')
def eat_class_var_dec(tokens, n_indent, existing_classes):
    """Eat tokens corresponding to class variables declaration

    Recognized syntax:
        ('static'|'field') type varName (',' varName)* ';'
     
    Args:
        tokens (list): tokens to analyse a class declaration from
        n_indent (int): desired indent level (kept for compatibility with 
            the indented_tag decorator)
        existing_classes (list): list of class names existing in the scope of
            the program. They should thus be recognized as valid data types.
    Returns:
        (indented tokens of the declaration, other tokens)
    """
    return apply_eaters(
        eat_by_value('static|field', 'keyword', n_indent, optional=True),
        eat_type(n_indent, existing_classes),
        eat_by_type('identifier', n_indent),
        eat_until_none(
            eat_by_value(',', 'symbol', n_indent,optional=True),
            eat_by_type('identifier', n_indent)),
        eat_by_value(';', 'symbol', n_indent))(tokens)


@delay_token_application
@indented_tag('subroutineDec')
def eat_sub_routine_dec(tokens, n_indent, existing_classes):
    """Eat tokens corresponding to subroutine declarations

    Recognized syntax:
        ('constructor'|'function'|'method') ('void'|type)
             subroutineName '(' parameterList ')' subroutineBody
     
    Args:
        tokens (list): tokens to analyse a class declaration from
        n_indent (int): desired indent level (kept for compatibility with 
            the indented_tag decorator)
        existing_classes (list): list of class names existing in the scope of
            the program. They should thus be recognized as valid data types.
    Returns:
        (indented tokens of the declaration, other tokens)
    """
    return apply_eaters(
        eat_by_value('constructor|function|method', 'keyword', n_indent, 
            optional=True),
        eat_type(n_indent, existing_classes),
        eat_by_type('identifier', n_indent),
        eat_by_value('(', 'symbol', n_indent),
        eat_param_list(n_indent, existing_classes),
        eat_by_value(')', 'symbol', n_indent),
        eat_sub_routine_body(n_indent, existing_classes))(tokens)


@delay_token_application
@indented_tag('parameterList', expand_none=True)
def eat_param_list(tokens, n_indent, existing_classes):
    """Eat tokens corresponding to parameter lists

    Recognized syntax:
        ((type varName) (',' type varName)*)?
     
    Args:
        tokens (list): tokens to analyse a class declaration from
        n_indent (int): desired indent level (kept for compatibility with 
            the indented_tag decorator)
        existing_classes (list): list of class names existing in the scope of
            the program. They should thus be recognized as valid data types.
    Returns:
        (indented tokens of the declaration, other tokens)
    """
    return apply_eaters(
        eat_type(n_indent, existing_classes, optional=True),
        eat_by_type('identifier', n_indent),
        eat_until_none(
            eat_by_value(',', 'symbol', n_indent, optional=True),
            eat_type(n_indent, existing_classes),
            eat_by_type('identifier', n_indent)))(tokens)


@delay_token_application
@indented_tag('subroutineBody')
def eat_sub_routine_body(tokens, n_indent, existing_classes):
    """Eat tokens corresponding to a subroutine body

    Recognized syntax:
        '{' varDec* statements '}'
     
    Args:
        tokens (list): tokens to analyse a class declaration from
        n_indent (int): desired indent level (kept for compatibility with 
            the indented_tag decorator)
        existing_classes (list): list of class names existing in the scope of
            the program. They should thus be recognized as valid data types.
    Returns:
        (indented tokens of the declaration, other tokens)
    """
    return apply_eaters(
        eat_by_value('{', 'symbol', n_indent),
        eat_until_none(eat_var_dec(n_indent, existing_classes)),
        eat_statements(n_indent, existing_classes),
        eat_by_value('}', 'symbol', n_indent))(tokens)


@delay_token_application
@indented_tag('varDec')
def eat_var_dec(tokens, n_indent, existing_classes):
    """Eat tokens corresponding to variable declarations

    Recognized syntax:
        'var' type varName (',' varName)* ';'
     
    Args:
        tokens (list): tokens to analyse a class declaration from
        n_indent (int): desired indent level (kept for compatibility with 
            the indented_tag decorator)
        existing_classes (list): list of class names existing in the scope of
            the program. They should thus be recognized as valid data types.
    Returns:
        (indented tokens of the declaration, other tokens)
    """
    return apply_eaters(
        eat_by_value('var', 'keyword', n_indent, optional=True),
        eat_type(n_indent, existing_classes),
        eat_by_type('identifier', n_indent),
        eat_until_none(
            eat_by_value(',', 'symbol', n_indent, optional=True),
            eat_by_type('identifier', n_indent)),
        eat_by_value(';', 'symbol', n_indent))(tokens)


############
# Statements
############


@delay_token_application
@indented_tag('statements')
def eat_statements(tokens, n_indent, existing_classes):
    """Eat tokens corresponding to statements

    Recognized syntax:
        statement*
     
    Args:
        tokens (list): tokens to analyse a class declaration from
        n_indent (int): desired indent level (kept for compatibility with 
            the indented_tag decorator)
        existing_classes (list): list of class names existing in the scope of
            the program. They should thus be recognized as valid data types.
    Returns:
        (indented tokens of the declaration, other tokens)
    """
    return eat_until_none(eat_statement(n_indent, existing_classes))(tokens)


@delay_token_application
def eat_statement(tokens, n_indent, existing_classes):
    """Eat tokens corresponding to a statement

    Recognized syntax:
        ifStatement | whileStatement | letStatement | doStatement 
            | returnStatement
     
    Args:
        tokens (list): tokens to analyse a class declaration from
        n_indent (int): desired indent level (kept for compatibility with 
            the indented_tag decorator)
        existing_classes (list): list of class names existing in the scope of
            the program. They should thus be recognized as valid data types.
    Returns:
        (indented tokens of the declaration, other tokens)
    """
    if tokens[0] == format_token('if', 'keyword'):
        return eat_if_statement(n_indent, existing_classes)(tokens)
    if tokens[0] == format_token('while', 'keyword'):
        return eat_while_statement(n_indent, existing_classes)(tokens)
    if tokens[0] == format_token('let', 'keyword'):
        return eat_let_statement(n_indent, existing_classes)(tokens)
    if tokens[0] == format_token('do', 'keyword'):
        return eat_do_statement(n_indent)(tokens)
    if tokens[0] == format_token('return', 'keyword'):
        return eat_return_statement(n_indent)(tokens)
    return None, tokens


@delay_token_application
@indented_tag('ifStatement')
def eat_if_statement(tokens, n_indent, existing_classes):
    """Eat tokens corresponding to a if statement

    Recognized syntax:
        'if' '(' expression ')’ '{' statements '}’ (else '{' statements '})?
     
    Args:
        tokens (list): tokens to analyse a class declaration from
        n_indent (int): desired indent level (kept for compatibility with 
            the indented_tag decorator)
        existing_classes (list): list of class names existing in the scope of
            the program. They should thus be recognized as valid data types.
    Returns:
        (indented tokens of the declaration, other tokens)
    """
    return apply_eaters(
        eat_by_value('if', 'keyword', n_indent),
        eat_by_value('(', 'symbol', n_indent),
        eat_expression(n_indent, optional=True),
        eat_by_value(')', 'symbol', n_indent),
        eat_by_value('{', 'symbol', n_indent),
        eat_statements(n_indent, existing_classes),
        eat_by_value('}', 'symbol', n_indent),
        eat_by_value('else', 'keyword', n_indent, optional=True),
        eat_by_value('{', 'symbol', n_indent),
        eat_statements(n_indent, existing_classes),
        eat_by_value('}', 'symbol', n_indent))(tokens)


@delay_token_application
@indented_tag('whileStatement')
def eat_while_statement(tokens, n_indent, existing_classes):
    """Eat tokens corresponding to a if statement

    Recognized syntax:
        'while' '(' expression ')’ '{' statements '}’
     
    Args:
        tokens (list): tokens to analyse a class declaration from
        n_indent (int): desired indent level (kept for compatibility with 
            the indented_tag decorator)
        existing_classes (list): list of class names existing in the scope of
            the program. They should thus be recognized as valid data types.
    Returns:
        (indented tokens of the declaration, other tokens)
    """
    return apply_eaters(
        eat_by_value('while', 'keyword', n_indent),
        eat_by_value('(', 'symbol', n_indent),
        eat_expression(n_indent, optional=True),
        eat_by_value(')', 'symbol', n_indent),
        eat_by_value('{', 'symbol', n_indent),
        eat_statements(n_indent, existing_classes),
        eat_by_value('}', 'symbol', n_indent))(tokens)


@delay_token_application
@indented_tag('letStatement')
def eat_let_statement(tokens, n_indent, existing_classes):
    """Eat tokens corresponding to a let statement

    Recognized syntax:
        'let' varName '=' expression ';'
     
    Args:
        tokens (list): tokens to analyse a class declaration from
        n_indent (int): desired indent level (kept for compatibility with 
            the indented_tag decorator)
        existing_classes (list): list of class names existing in the scope of
            the program. They should thus be recognized as valid data types.
    Returns:
        (indented tokens of the declaration, other tokens)
    """
    return apply_eaters(
        eat_by_value('let', 'keyword', n_indent),
        eat_by_type('identifier', n_indent),
        apply_eaters(
            eat_by_value('[', 'symbol', n_indent, optional=True),
            eat_expression(n_indent),
            eat_by_value(']', 'symbol', n_indent)),
        eat_by_value('=', 'symbol', n_indent),
        eat_expression(n_indent),
        eat_by_value(';', 'symbol', n_indent),
        break_on_none=False)(tokens)


@delay_token_application
@indented_tag('doStatement')
def eat_do_statement(tokens, n_indent):
    """Eat tokens corresponding to a do statement

    Recognized syntax:
        'do' subroutineCall ';'
     
    Args:
        tokens (list): tokens to analyse a class declaration from
        n_indent (int): desired indent level (kept for compatibility with 
            the indented_tag decorator)
    Returns:
        (indented tokens of the declaration, other tokens)
    """
    return apply_eaters(
        eat_by_value('do', 'keyword', n_indent),
        eat_subroutine_call(n_indent),
        eat_by_value(';', 'symbol', n_indent))(tokens)


@delay_token_application
@indented_tag('returnStatement')
def eat_return_statement(tokens, n_indent):
    """Eat tokens corresponding to a return statement

    Recognized syntax:
        returnStatemen: 'return' expression? ';'

    Args:
        tokens (list): tokens to analyse a class declaration from
        n_indent (int): desired indent level (kept for compatibility with 
            the indented_tag decorator)
    Returns:
        (indented tokens of the declaration, other tokens)
    """
    return apply_eaters(
        eat_by_value('return', 'keyword', n_indent),
        eat_expression(n_indent, optional=True),
        eat_by_value(';', 'symbol', n_indent),
        break_on_none=False)(tokens)


#############
# Expressions
#############


@delay_token_application
@indented_tag('expressionList', expand_none=True)
def eat_expression_list(tokens, n_indent):
    """Eat tokens corresponding to a return statement

    Recognized syntax:
        (expression (',' expression)*)?

    Args:
        tokens (list): tokens to analyse a class declaration from
        n_indent (int): desired indent level (kept for compatibility with 
            the indented_tag decorator)
    Returns:
        (indented tokens of the declaration, other tokens)
    """
    return apply_eaters(
        eat_expression(n_indent, optional=True),
        eat_until_none(
            eat_by_value(',', 'symbol', n_indent, optional=True),
            eat_expression(n_indent)))(tokens)


@delay_token_application
@indented_tag('expression')
def eat_expression(tokens, n_indent, optional=False):
    """Eat tokens corresponding to an expression

    Recognized syntax:
         term (op term)*

    Args:
        tokens (list): tokens to analyse a class declaration from
        n_indent (int): desired indent level (kept for compatibility with 
            the indented_tag decorator)
        optional (bool): continue silently if no expression wath found
    Returns:
        (indented tokens of the declaration, other tokens)
    """
    return apply_eaters(
        eat_term(n_indent, optional=optional),
        eat_until_none(
            eat_op(n_indent, optional=True),
            eat_term(n_indent)))(tokens)


@delay_token_application
def eat_op(tokens, n_indent, optional=False):
    """Eat tokens corresponding to an operation symbol

    Recognized syntax:
        '+'|'-'|i'*'|'/'|'&'|'|'|'='|'>'|'<'

    Args:
        tokens (list): tokens to analyse a class declaration from
        n_indent (int): desired indent level (kept for compatibility with 
            the indented_tag decorator)
        optional (bool): continue silently if no expression wath found
    Returns:
        (indented tokens of the declaration, other tokens)
    """
    return eat_by_value('+|-|*|/|&|&OR|=|>|<', 'symbol', n_indent, 
        optional=optional)(tokens)


@delay_token_application
def eat_subroutine_call(tokens, n_indent):
    """Eat tokens corresponding to a sub-routine call

    Recognized syntax:
        subroutineName '(' expressionList ')' 
            | (className|varname)'.'subroutineName'('expressionList')'

    Args:
        tokens (list): tokens to analyse a class declaration from
        n_indent (int): desired indent level (kept for compatibility with 
            the indented_tag decorator)
    Returns:
        (indented tokens of the declaration, other tokens)
    """
    identifier, tokens = eat_by_type('identifier', n_indent)(tokens)
    dot, tokens = eat_by_value('.', 'symbol', n_indent, 
        optional=True)(tokens)
    if dot is not None:
        f_name, tokens = eat_by_type('identifier', n_indent)(tokens)
    else:
        f_name=None
    f_call, tokens = apply_eaters(
        eat_by_value('(', 'symbol', n_indent),
        eat_expression_list(n_indent),
        eat_by_value(')', 'symbol', n_indent)
    )(tokens)

    func_call = identifier
    if dot is not None:
        func_call += dot + f_name

    return func_call + f_call, tokens


@delay_token_application
@indented_tag('term')
def eat_term(tokens, n_indent, optional=False):
    """Eat tokens corresponding to a term

    Recognized syntax:
        integerConstant | stringConstant | keywordConstant | varName
            | varName'['expression']' | subroutineCall | '('expression')' 
            | unaryOp term

    Args:
        tokens (list): tokens to analyse a class declaration from
        n_indent (int): desired indent level (kept for compatibility with 
            the indented_tag decorator)
        optional (bool): continue silently if no expression wath found
    Returns:
        (indented tokens of the declaration, other tokens)
    """

    integer_constant, tokens = eat_by_type('integerConstant', n_indent, 
        optional=True)(tokens)
    if integer_constant is not None:
        return integer_constant, tokens 

    string_constant, tokens = eat_by_type('stringConstant', n_indent, 
        optional=True)(tokens)
    if string_constant is not None:
        return string_constant, tokens

    # keywordConstant: 'true'|'false'|'null'|'this'
    keyword_constant, tokens = eat_by_value('true|false|null|this', 'keyword', 
        n_indent, optional=True)(tokens)
    if keyword_constant is not None:
        return keyword_constant, tokens

    # varName|varName'['expression']|subroutineCall'
    initial_token = tokens[0:1]
    identifier, tokens = eat_by_type('identifier', n_indent, optional=True)(
        tokens)
    if identifier is not None:
        if tokens[0] == format_token('[', 'symbol'):
            return apply_eaters(
                eat_by_type('identifier', n_indent, optional=True),
                eat_by_value('[', 'symbol', n_indent),
                eat_expression(n_indent),
                eat_by_value(']', 'symbol', n_indent))(initial_token + tokens)
        if (tokens[0] == format_token('.', 'symbol') 
                or tokens[0] == format_token('(', 'symbol')):
            return eat_subroutine_call(n_indent)(initial_token + tokens)
        return identifier, tokens

    # '('expression')'
    expression, tokens = apply_eaters(
        eat_by_value('(', 'symbol', n_indent, optional=True),
        eat_expression(n_indent),
        eat_by_value(')', 'symbol', n_indent))(tokens)
    if expression is not None:
        return expression, tokens

    # unaryOp term
    # unaryOp: '-'|'~'
    unary_term, tokens = apply_eaters(
        eat_by_value('-|~', 'symbol', n_indent, optional=True),
        eat_term(n_indent))(tokens)
    if unary_term is not None:
        return unary_term, tokens

    if optional:
        return None, tokens
    
    raise ValueError(f'Expected a term, found `{tokens[:5]}...`')


#################
# Syntax analysis
#################


def post_process(token):
    return token.replace(
        '<symbol> < </symbol>', '<symbol> &lt; </symbol>').replace(
        '<symbol> > </symbol>', '<symbol> &gt; </symbol>').replace(
        '<symbol> & </symbol>', '<symbol> &amp; </symbol>')


def post_process_tokens(tokens):
    return [post_process(token) for token in tokens]


def process_file(file_path, existing_classes):
    return '\n'.join(post_process_tokens(eat_class(
       tokenize(read_file(file_path)),0,existing_classes)[0])) + '\n'


project_path = Path(sys.argv[1])

existing_classes = ['String', 'Array'] + [
    f.name[:-5]
    for f in project_path.parent.glob('*.jack')]

if project_path.is_file(): # Single file translation
    print(process_file(project_path, existing_classes))
else: # Folder
    to_process = project_path.parent.glob('*.jack')
    for file_path in to_process:
        output_file = Path(file_path.parent.expanduser() 
            / file_path.name.replace('.jack', '.comp.xml'))
        print('Analysing', file_path.name)
        output_file.write_text(process_file(file_path, existing_classes))
