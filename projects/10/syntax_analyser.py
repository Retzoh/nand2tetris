import re
import sys
from pathlib import Path


##############
# File parsing
##############


def get_file_name(path):
    return path.split('/')[-1].split('.jack')[0] 
 
 
def read_file(path):
    def read_caracters():
        return Path(path).expanduser().read_text()

    def remove_block_coments(blob):
        return re.sub('/\*(.*?)\*/', '', blob)

    def remove_line_comments(blob):
        return re.sub('//(.*?)\n', '\n', blob)

    def remove_blancks(blob):
        return re.sub('\n', '', blob)

    return remove_blancks(
        remove_line_comments(
            remove_block_coments(
                read_caracters())))


########
# Tokens
########


"""
keyword:
'class' | 'constructor' | 'function' | 'method' | 'field' | 'static' | 'var' | 'int' | 'char' | 'boolean' | 'void' | 'true' | 'false' | 'null' | 'this' | 'let' | 'do' | 'if' | 'else' | 'while' | 'return’
 symbol:
'{' | '}' | '(' | ')' | '[' | ']' | '. ' | ', ' | '; ' | '+' | '-' | '*' | '/' | '&' | '|' | '<' | '>' | '=' | '~'
integerConstant: a decimal number in the range 0 ... 32767
StringConstant: '"' a sequence of Unicode characters, not including double quote or newline '"'
identifier: a sequence of letters, digits, and underscore ( '_' ) not starting with a digit.
"""


def is_blank(c):
    return re.match('\s', c) is not None


def is_symbol(c):
    return c in {'{',  '}',  '(',  ')',  '[',  ']',  '.',  
        ',',  ';',  '+',  '-',  '*',  '/',  '&',  '|',  '<',  
        '>',  '=',  '~'}


def is_integer(c):
    try:
        int(c)
        return True
    except ValueError:
        return False


def is_string(c):
    return c=='"'


def is_keyword(string):
    return string in {'class',  'constructor',  'function',  'method',  
        'field',  'static',  'var',  'int',  'char',  'boolean',  
        'void',  'true',  'false',  'null',  'this',  'let',  'do',  
        'if',  'else',  'while',  'return'}


def is_identifier_char(c):
    return re.match('[_\w]', c) is not None


def eat_char(chars):
    return chars[0], chars[1:]


def eat_integer(chars, c):
    if not is_integer(chars[0]):
        return c, chars

    i=1
    while is_integer(chars[i]):
        i += 1
    return c+chars[:i], chars[i:]


def eat_string(chars, c):
    i=0
    while chars[i] != '"':
        i += 1
    return chars[:i], chars[i+1:]


def eat_identifier_or_keyword(chars, c):
    if not is_identifier_char(chars[0]):
        return c, chars
    i=1
    while is_identifier_char(chars[i]):
        i += 1
    return c+chars[:i], chars[i:]


def format_token(word, token_type):
    return f'<{token_type}> {word} </{token_type}>'


def tokenize(chars):
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
            word, chars = eat_string(chars, c)
            tokens += [format_token(word, 'stringConstant')]
            continue
        word, chars = eat_identifier_or_keyword(chars, c)
        if is_keyword(word):
            tokens += [format_token(word, 'keyword')]
        else:
            tokens += [format_token(word, 'identifier')]
                
    return tokens


#########
# Parsing
#########
"""
# Structure)
className, subroutineName, varName: identifier

# Statements:
statements: statement*
# Expressions:
expression: term (op term)?
term: integerConstant|stringConstant|keywordConstant|varName|varName'['expression']'|
    subroutineCall|'('expression')'|unaryOp term
subroutineCall: subroutineName '(' expressionList ')'|
    (className|varname)'.'subroutineName'('expressionList')'
expressionList: (expression (','expression)*)?
op: '+'|'-'|i'*'|'/'|'&'|'|'|'='|'>'|'<'
unaryOp: '-'|'~'
keywordConstant: 'true'|'false'|'null'|'this'

"""


def indent(token, level=1):
    return ' '*2*level + token


def is_of_val(value, t, token):
    return token == format_token(value, t)


def is_of_type(t, token):
    return (token.split('<')[1].split('>')[0] == t 
        and token.split('</')[1].split('>')[0] == t)


def eat_by_value(tokens, expected_value, expected_type, indent_level=1, optional=False):
    values = expected_value.split('|')
    if not any([tokens[0] == format_token(v, expected_type) 
            for v in values]):
        if optional:
            return None, tokens
        raise ValueError(f'Expected {expected_value} {expected_type},'
            f' found {tokens[0]}')
    return indent(tokens[0], indent_level), tokens[1:]


def eat_by_type(tokens, expected_type, indent_level=1, optional=False):
    types = expected_type.split('|')
    if not any([is_of_type(t, tokens[0]) for t in types]):
        if optional:
            return None, tokens
        raise ValueError(f'expected token of type {expected_type}, found {tokens[0]}')
    return indent(tokens[0], indent_level), tokens[1:]


def eat_type(tokens, indent_level, existing_classes, optional=False):
    # type: 'int'|'char'|'boolean'|className
    t, tokens =  eat_by_value(tokens, 
        'int|char|boolean|void|',
        'keyword',
        indent_level, optional=True)
    if t is not None: return t, tokens
    return eat_by_value(tokens,
        '|'.join(existing_classes), 'identifier', indent_level, optional=optional)


def eat_until_none(tokens, *eaters):
    eated = []
    for eater in eaters:
        new, tokens = eater(tokens)
        if new is None: return eated, tokens
        eated += [new]
    while new is not None:
        for eater in eaters:
            new, tokens = eater(tokens)
            if new is None: return eated, tokens
            eated += [new]
    return eated, tokens


def indented_tag(tag_name):
    def decorator(f):
        def helper(tokens, indent_level, *args, **kwargs):
            xml_lines, tokens = f(tokens, indent_level+1, *args, **kwargs)
            if xml_lines is None:
                return None, tokens
            return (
                [indent(f'<{tag_name}>', indent_level)] + 
                xml_lines + 
                [indent(f'</{tag_name}>', indent_level)]), tokens
        return helper
    return decorator


@indented_tag('classVarDec')
def eat_class_var_dec(tokens, indent_level):
    # classVarDec: ('static'|'field') type varName (',' varName)* ';'
    var_meta_type, tokens = eat_by_value(
        tokens, 'static|field', 'keyword', indent_level, optional=True)
    if var_meta_type is None:
        return None, tokens
    var_type, tokens = eat_type(tokens, indent_level, [])
    var_name, tokens = eat_by_type(tokens, 'identifier', indent_level)
    other_vars, tokens = eat_until_none(tokens, 
        lambda tokens: eat_by_value(tokens, ',', 'symbol', indent_level, optional=True),
        lambda tokens: eat_by_type(tokens, 'identifier', indent_level))
    semi_comma, tokens = eat_by_value(tokens, ';', 'symbol', indent_level)
    param_list, tokens = eat_param_list(tokens, indent_level)

    return (
        [var_meta_type, var_type, var_name] + 
        other_vars + [semi_comma]), tokens


@indented_tag('parameterList')
def eat_param_list(tokens, indent_level):
    # parameterList: ((type varName) (',' type varName)*)?
    first_type, tokens = eat_type(tokens, indent_level, ['Square'], optional=True)
    if first_type is None:
        return ([]), tokens
    first_name, tokens = eat_by_type(tokens, 'identifier', indent_level)

    params, tokens = eat_until_none(tokens, 
        lambda tokens: eat_by_value(tokens, ',', 'symbol', indent_level, optional=True),
        lambda tokens: eat_type(tokens, indent_level, ['Square']),
        lambda tokens: eat_by_type(tokens, 'identifier', indent_level),
    )
    return ([first_type, first_name] + params), tokens


def eat_var_dec(tokens, indent_level):
    # varDec: 'var' type varName (',' varName)* ';'
    var_meta_type, tokens = eat_by_value(
        tokens, 'var', 'keyword', indent_level+1, optional=True)
    if var_meta_type is None:
        return None, tokens
    var_type, tokens = eat_type(tokens, indent_level+1, [])
    var_name, tokens = eat_by_type(tokens, 'identifier', indent_level+1)
    other_vars, tokens = eat_until_none(tokens, 
        lambda tokens: eat_by_value(tokens, ',', 'symbol', indent_level+1, optional=True),
        lambda tokens: eat_by_type(tokens, 'identifier', indent_level+1))
    semi_comma, tokens = eat_by_value(tokens, ';', 'symbol', indent_level+1)
    param_list, tokens = eat_param_list(tokens, indent_level+1)

    return (
        [indent('<varDec>', indent_level)] + 
        [var_meta_type, var_type, var_name] + 
        other_vars + [semi_comma] +
        [indent('</varDec>', indent_level)]), tokens


def eat_let_statement(tokens, indent_level):
    # letStatement: 'let' varName '=' expression ';'
    let_kwd, tokens = eat_by_value(tokens, 'let', 'keyword', indent_level+1)
    identifier, tokens = eat_by_type(tokens, 'identifier', indent_level+1, ['Square'])
    equal, tokens = eat_by_value(tokens, '=', 'symbol', indent_level+1)
    return ( 
        [indent('<letStatement>', indent_level)] + 
        [let_kwd, identifier, equal] + 
        [indent('</letStatement>', indent_level)], tokens)


def eat_statement(tokens, indent_level):
    # statement: ifStatement | whileStatement | letStatement 
    #   | doStatement | returnStatement
    # ifStatement: 'if' '(' expression ')’ '{' statements '}’
    # whileStatement: 'while' '(' expression ')’ '{' statements '}’
    # doStatement: 'do' subroutineCall ';'
    # returnStatemen: 'return' expression? ';'

    if tokens[0] == format_token('if', 'keyword'):
        raise ValueError('If statement not implemented')
    if tokens[0] == format_token('while', 'keyword'):
        raise ValueError('While statement not implemented')
    if tokens[0] == format_token('let', 'keyword'):
        return eat_let_statement(tokens, indent_level)
    if tokens[0] == format_token('do', 'keyword'):
        raise ValueError('Do statement not implemented')
    if tokens[0] == format_token('return', 'keyword'):
        raise ValueError('Return statement not implemented')
    return None, tokens


def eat_statements(tokens, indent_level):
    statements, tokens = eat_until_none(tokens,
        lambda tokens: eat_statement(tokens, indent_level + 1)) 
    return (
        [indent('<statements>', indent_level)] +
        sum(statements, []) + 
        [indent('</statements>', indent_level)]), tokens


def eat_sub_routine_body(tokens, indent_level):
    # subroutineBody: '{' varDec* statements '}'
    bracket_o, tokens = eat_by_value(tokens, '{', 'symbol', indent_level+1)
    var_decs, tokens = eat_until_none(tokens,
        lambda tokens: eat_var_dec(tokens, indent_level+1))
    statements, tokens = eat_statements(tokens, indent_level+1)
    return (
        [indent('<subroutineBody>', indent_level)] + 
        [bracket_o] +
        var_decs + 
        statements + 
        [indent('</subroutineBody>', indent_level)]), tokens


def eat_sub_routine_dec(tokens, indent_level=1):
    # subroutineDec: ('constructor'|'function'|'method') ('void'|type) 
    #    subroutineName '(' parameterList ')' subroutineBody
    routine_meta_type, tokens = eat_by_value(tokens,
        'constructor|function|method', 'keyword', indent_level + 1, optional=True)
    if routine_meta_type is None:
        return None, tokens

    return_type, tokens = eat_type(tokens, indent_level+1, ['Square'])
    routine_name, tokens = eat_by_type(tokens, 'identifier', indent_level+1)
    parenthesis_o, tokens = eat_by_value(tokens, '(', 'symbol', indent_level+1)
    param_list, tokens = eat_param_list(tokens, indent_level + 1)
    parenthesis_c, tokens = eat_by_value(tokens, ')', 'symbol', indent_level+1)
    body, tokens = eat_sub_routine_body(tokens, indent_level+1)

    return (
        [indent('<subroutineDec>', indent_level)] +
        [routine_meta_type, return_type, routine_name, parenthesis_o] +
        param_list +
        [parenthesis_c] + body + 
        [indent('</subroutineDec>', indent_level)]), tokens
 

def eat_class(tokens):
    # class: 'class' className '{' classVarDec*, subroutineDec* '}'
    class_keyword, tokens = eat_by_value(tokens, 'class', 'keyword', indent_level=1)
    class_name, tokens = eat_by_type(tokens, 'identifier', indent_level=1)
    bracket_o, tokens = eat_by_value(tokens, '{', 'symbol', 1)
    class_var_decs, tokens = eat_until_none(tokens, 
        lambda tokens: eat_class_var_dec(tokens, 1))
    sub_routine_dec, tokens = eat_until_none(tokens, eat_sub_routine_dec)
    
    return (['<class>'] + 
        [class_keyword, class_name, bracket_o] + 
        sum(class_var_decs, []) +
        sum(sub_routine_dec, []) + 
        tokens +
        ['</class>'])


#################
# Syntax analysis
#################


project_path = Path(sys.argv[1])
if project_path.is_file(): # Single file translation
    print('\n'.join(eat_class(tokenize(read_file(project_path)))))
else: # Folder
    print('folder not yet supported')
