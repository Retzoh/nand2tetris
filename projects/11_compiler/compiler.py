"""Compiler for the jack language.

Usage:

python compiler.py path

If `path` is a jack file: directly outputs the compiled vm code
If `path` is a folder: scans it for `.jack` files and outputs their compiled
codes in respective `.vm` files.

Each file should contain one jack class having the same name as the file. 

The compiler is based on the concept of "eaters":
Given a list of elements, a eater scans them progressively while a specific rule
is satisfied. The elements following the rule are "eated" away from the initial 
list and processed. Eventually, the eater returns a tuple containing the result 
of the processing and the leftovers.

To pass context elements to the various eaters, a "scope" object is used: it 
contains the list of tokens that are yet to be eaten, and various context 
variables needed for compilation. The scope is passed from one eater to the 
next. For nested elements (while/if/functions inside one another), a stacking 
system copies the parent scope for each new child. Writing in the parent scope 
is thus prevented, except for specific keys (see `unstack_scope`).

The initial jack code is eated once on a character basis to produce tokens. A 
second pass eats the tokens to produce the vm code.

This file is organized in parts following those stages:

File parsing (line 107)
Tokens (line 155)
Utilities (line 301)
Scope (line 414)
Structure (line 551)
Statements (line 770)
Expressions (line 1059)
Compilation (line 1296)

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
    """Return (first character of a string, the rest)"""
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
        i+=1
    return first_char+chars[:i], chars[i:]


def tag_word(word, token_type):
    """Tag a word with a token type"""
    return (word, token_type)


def get_token_value(token):
    """Extract the value of a token"""
    return token[0]


def get_token_type(token):
    """Extract the type of a token"""
    return token[1]


def tokenize(chars):
    """Recognize and split the individual tokens in `chars`

    Eats `chars` progressively, one character at a time.
    Infer the type of the current token from its first character and eat the 
    rest of it.

    The tokens are then returned as a list of xml lines: `<type> token </type>`
    """
    tokens=[]
    while len(chars) > 0:
        c, chars = eat_char(chars)
        if is_blank(c):
            continue
        if is_symbol(c):
            tokens += [tag_word(c, 'symbol')]
            continue
        if is_integer(c):
            word, chars = eat_integer(chars, c)
            tokens += [tag_word(word, 'integerConstant')]
            continue
        if is_string(c):
            word, chars = eat_string(chars)
            tokens += [tag_word(word, 'stringConstant')]
            continue
        word, chars = eat_identifier_or_keyword(chars, c)
        if is_keyword(word):
            tokens += [tag_word(word, 'keyword')]
        else:
            tokens += [tag_word(word, 'identifier')]
    return tokens


###########
# Utilities
###########

def delay_scope_application(f):
    """Decorate f to make it a "delayed" function waiting for a scope to run"""
    def helper(*args, **kwargs):
        return lambda scope: f(scope, *args, **kwargs)
    return helper


@delay_scope_application
def eat_by_value(scope, expected_value, expected_type,
        optional=False, scope_key_to_update=None):
    """Eat the specified token from `scope`.

    Multiples accepted values can be passed using a "|" separator.
    To recognise the "|" value, "&OR" should be specified.

    Args:
        scope: scope to eat token from
        expected_value (str): desired token value. Multiple acceptable values 
            can be specified with a pipe "|" separator. To recognize the "|" 
            value, "&OR" should be specified.
        expected_type (str): desired token type. Only one type may be specified.
        optional (bool, default=False): Action to do if desired token is not 
            present: If True, return None, else raise an error
        scope_key_to_update (str, default=None): scope key to write the eated 
            value onto
    Returns:
        (token, rest of the scope)
    """
    values = [v.replace('&OR', '|') for v in expected_value.split('|')]
    if not any([scope["tokens"][0] == tag_word(v, expected_type) 
            for v in values]):
        if optional:
            return None, scope
        raise ValueError(f'Expected {expected_value} {expected_type}'
            f' found {scope["tokens"][0]}')
    if scope_key_to_update is None:
        return [''], pop_token(scope)
    return [''], set_scope_element(pop_token(scope), scope_key_to_update,
        get_token_value(scope["tokens"][0]))


@delay_scope_application
def eat_by_type(scope, expected_type, optional=False, scope_key_to_update=None):
    """Eat the specified token from `scope`.

    Multiple types can be specified with a "|" separator.

    Args:
        scope: scope left in the current class
        expected_type (str): desired token type. Multiple types may be 
            specified, separated with pipes "|".
        optional (bool, default=False): Action to do if desired token is not 
            present: If True, return None, else raise an error
        scope_key_to_update (str, default=None): scope key to write the eated 
            value onto
        Returns:
            (token, rest of the scope)
    """
    types = expected_type.split('|')
    if not any([t == get_token_type(scope["tokens"][0]) for t in types]):
        if optional:
            return None, scope
        raise ValueError(f'expected token of type {expected_type}, found '
            f'{scope["tokens"][0]}')
    if scope_key_to_update is None:
        return [scope["tokens"][0]], pop_token(scope)
    return [''], set_scope_element(pop_token(scope), scope_key_to_update, 
        get_token_value(scope["tokens"][0]))


@delay_scope_application
def apply_eaters(scope, *eaters, break_on_none=True):
    """Apply specified eaters once, break if one returns `None`"""
    eated_tokens = []
    for eater in eaters:
        newly_eated, scope = eater(scope)
        if newly_eated is None:
            if break_on_none: break
            else: continue
        eated_tokens += newly_eated
    return (eated_tokens if len(eated_tokens)>0 else None), scope


@delay_scope_application
def eat_until_none(scope, *eaters):
    """Apply specified eaters cyclically until one returns a `None` value"""
    eated_tokens = []
    for eater in eaters:
        newly_eated, scope = eater(scope)
        if newly_eated is None: break
        eated_tokens += [newly_eated]
    while newly_eated is not None:
        for eater in eaters:
            newly_eated, scope = eater(scope)
            if newly_eated is None: break
            eated_tokens += [newly_eated]
    return sum(eated_tokens, []), scope


def catch_none(f):
    """Decorator replacing `None` outputs with an empty list"""
    def helper(scope, *args, **kwargs):
        vm_lines, scope = f(scope, *args, **kwargs)
        if vm_lines is None:
            vm_lines = []
        return vm_lines, scope
    return helper


#######
# Scope
#######


def new_scope(tokens, scope_stack=None):
    """Create a new scope

    Scope elements:
    - class: name of the current class
    - function: name of the current function
    - function_type: type of the current function (function|method|constructor)
    - local: variables on the `local` segment (ordered by segment index)
    - argument: variables on the `argument` segment (ordered by segment index)
    - static: variables on the `static` segment (ordered by segment index)
    - field: variables on the `field` segment (ordered by segment index)
    - variables: store the `variables: type` pairs 
        class, which is not a variable.
    - n_args: store the amount of arguments declared in the current signature 
        (subroutine_dec)
    - loop: tracks if we are in a `if` or `while` statement.
    - n_while: store the amount of `while` statements encountered. This entry is
        shared between all statements inside a same function 
        (see `unstack_scope`)
    - n_if: store the amount of `if` statements encountered. This entry is 
        shared between all statements inside a same function 
        (see `unstack_scope`)
    - current_if: identifier of the current `if` statement
    - current_while: identifier of the current `while` loop
    - array_dest: for `let` statements, tracks if the destination is inside an
        array
    - tokens: list of tokens yet to be eaten
    - stack: parent scopes that are stacked, waiting for the current instruction
        to be compiled
    """
    return {
        'class': '',
        'function': '',
        'function_type': '',
        'local': [],
        'argument': [],
        'static': [],
        'field': [],
        'variables': {},
        'n_args': 0,
        'loop': '',
        'n_while': -1,
        'n_if': -1,
        'current_if': -1,
        'current_while': -1,
        'array_dest': False,
        'tokens': tokens, 
        'stack': scope_stack}


def inc_n_counter(scope):
    """Increment the `if` or `while` counter and set current if/while-id"""
    scope=scope.copy()
    scope[f'n_{scope["loop"]}'] += 1
    scope[f'current_{scope["loop"]}'] = scope[f'n_{scope["loop"]}']
    return [''], scope


def set_scope_element(scope, key, value):
    """Copy the scope and sets the desired key-value pair"""
    scope=scope.copy()
    scope[key] = value
    return scope


@delay_scope_application
def inc_scope_element(scope, key):
    """Increment a scope counter, typically `n_args`"""
    scope=scope.copy()
    scope[key] += 1
    return [''], scope


def clean_scope_tokens(scope):
    """Remove the `tokens` entry from a scope"""
    scope = scope.copy()
    scope.pop('tokens')
    return scope


def stack_scope(scope):
    """Make a copy of a scope for a child and stack the parent scope in it"""
    return set_scope_element(scope.copy(), 'stack', 
        clean_scope_tokens(scope.copy()))


def unstack_scope(scope):
    """Reset the stacked scope and update its tokens and if/while counters
    
    if/while counters should only be updated if we stay inside a function,
    thus the check on `function_type`: it is only empty at the class-level.
    """
    tokens = scope['tokens']
    n_if = scope['n_if']
    n_while = scope['n_while']
    scope = scope['stack'].copy()
    scope['tokens'] = tokens
    if scope['function_type'] != '':
        scope['n_while'] = n_while
        scope['n_if'] = n_if
    return scope


def nested_scope(f):
    """Decorator stacking the scope before calls to f and unstacking it after"""
    def helper(scope, *args, **kwargs):
        tokens, scope = f(stack_scope(scope), *args, **kwargs)
        return tokens, unstack_scope(scope)
    return helper


def pop_token(scope):
    """Remove the first token from the scope"""
    scope = scope.copy()
    scope['tokens'] = scope['tokens'][1:]
    return scope


def no_scope_update(f):
    """Decorator for the use of scope-read-only functions with `apply_eaters`"""
    def helper(scope, *args, **kwargs):
        return f(scope, *args, **kwargs), scope
    return helper


def no_scope(f):
    """Decorator for the use of no-scope functions with `apply_eaters`"""
    def helper(scope, *args, **kwargs):
        return f(*args, **kwargs), scope
    return helper


###########
# Structure
###########


@delay_scope_application
def eat_type(scope, existing_classes, optional=False):
    """Eat a token corresponding to a type

    Recognized jack syntax:
    'int'|'char'|'boolean'|className

    First tries to eat one of the pre-defined types (int / char / boolean).
    If unsuccessful, look for user-defined classes.
    """
    t, scope =  eat_by_value('int|char|boolean|void','keyword',
        optional=True, scope_key_to_update='new_type')(scope)
    if t is not None: return t, scope
    return eat_by_value('|'.join(existing_classes), 'identifier',
        optional=optional, scope_key_to_update='new_type')(scope)


@nested_scope
def eat_class(scope, existing_classes):
    """Eat tokens corresponding to a class declaration
    
    Recognized jack syntax:
    'class' className '{' classVarDec*, subroutineDec* '}'
    
    Args:
        scope: scope to analyse a class declaration from
        existing_classes (list): list of class names existing in the scope of
            the program. They should thus be recognized as valid data types.
    Returns:
        (vm code for the declaration, updated scope)
    """
    return apply_eaters( 
        eat_by_value('class', 'keyword'),
        eat_by_type('identifier', scope_key_to_update='class'),
        eat_by_value('{', 'symbol'),
        eat_until_none(eat_class_var_dec(existing_classes)),
        eat_until_none(eat_subroutine_dec(existing_classes)),
        eat_by_value('}', 'symbol'))(scope)


@delay_scope_application
def eat_class_var_dec(scope, existing_classes):
    """Eat tokens corresponding to class variables declaration

    Recognized jack syntax:
        ('static'|'field') type varName (',' varName)* ';'
     
    Args:
        scope: scope to analyse a class declaration from
        existing_classes (list): list of class names existing in the scope of
            the program. They should thus be recognized as valid data types.
    Returns:
        (vm code for the declaration, updated scope)
    """
    return apply_eaters(
        eat_by_value('static|field', 'keyword', optional=True,
            scope_key_to_update='static/field'),
        eat_type(existing_classes),
        eat_by_type('identifier', scope_key_to_update='new_id'),
        add_id_to_static_or_field,
        eat_until_none(
            eat_by_value(',', 'symbol', optional=True),
            eat_by_type('identifier', scope_key_to_update='new_id'),
            add_id_to_static_or_field),
        eat_by_value(';', 'symbol'))(scope)

def add_this_to_locals(scope):
    """Add the `this` keyword to the local variables"""
    if scope['function_type'] != 'method':
        return [''], scope
    scope = scope.copy()
    scope['new_id'] = 'this'
    _, scope = add_id_to_scope('argument')(scope)
    return [''], scope 


@delay_scope_application
@nested_scope
def eat_subroutine_dec(scope, existing_classes):
    """Eat tokens corresponding to subroutine declarations

    Recognized jack syntax:
        ('constructor'|'function'|'method') ('void'|type)
             subroutineName '(' parameterList ')' subroutineBody
     
    Args:
        scope: tokens to analyse a class declaration from
        existing_classes (list): list of class names existing in the scope of
            the program. They should thus be recognized as valid data types.
    Returns:
        (vm code of the declaration, updated scope)
    """
    return apply_eaters(
        eat_by_value('constructor|function|method', 'keyword', optional=True,
            scope_key_to_update='function_type'),
        eat_type(existing_classes),
        eat_by_type('identifier', scope_key_to_update='function'),
        add_this_to_locals,
        eat_by_value('(', 'symbol'),
        eat_param_list(existing_classes),
        eat_by_value(')', 'symbol'),
        eat_sub_routine_body(existing_classes))(scope)


@delay_scope_application
@catch_none
def eat_param_list(scope, existing_classes):
    """Eat scope corresponding to parameter lists

    Recognized jack syntax:
        ((type varName) (',' type varName)*)?
     
    Args:
        scope: scope to analyse a class declaration from
        existing_classes (list): list of class names existing in the scope of
            the program. They should thus be recognized as valid data types.
    Returns:
        (vm code of the declaration, updated scope)
    """
    return apply_eaters(
        eat_type(existing_classes, optional=True),
        eat_by_type('identifier', scope_key_to_update='new_id'),
        add_id_to_scope('argument'),
        eat_until_none(
            eat_by_value(',', 'symbol', optional=True),
            eat_type(existing_classes),
            eat_by_type('identifier', scope_key_to_update='new_id'),
            add_id_to_scope('argument')))(scope)


@no_scope_update
def generate_function_declaration(scope):
    """Generate the vm code for a function declaration"""
    n_locals = len(scope['local'])
    function_declaration = [
        f'function {scope["class"]}.{scope["function"]} {n_locals}']
    if scope['function_type'] == 'constructor':
        function_declaration += [
            f'push constant {len(scope["field"])}',
            'call Memory.alloc 1',
            'pop pointer 0']
    elif scope['function_type'] == 'method':
        function_declaration += ['push argument 0', 'pop pointer 0']
    return function_declaration


@delay_scope_application
def eat_sub_routine_body(scope, existing_classes):
    """Eat tokens corresponding to a subroutine body

    Recognized jack syntax:
        '{' varDec* statements '}'
     
    Args:
        scope: scope to analyse a class declaration from
        existing_classes (list): list of class names existing in the scope of
            the program. They should thus be recognized as valid data types.
    Returns:
        (vm code for the declaration, updated scope)
    """
    return apply_eaters(
        eat_by_value('{', 'symbol'),
        eat_until_none(eat_var_dec(existing_classes)),
        generate_function_declaration,
        eat_statements(existing_classes),
        eat_by_value('}', 'symbol'))(scope)


@delay_scope_application
def add_id_to_scope(scope, segment):
    """Add a new variable to the scope, for `local` or `argument` segments"""
    scope=scope.copy()
    scope[segment] = scope[segment] + [scope['new_id']]
    scope['variables'][scope['new_id']] = scope['new_type']
    scope['new_id'] = ''
    return [''], scope


def add_id_to_static_or_field(scope):
    """Add a new variable to the scope, for `static` or `field` segments"""
    scope=scope.copy()
    meta_type = scope['static/field']
    scope[meta_type] = scope[meta_type] + [scope['new_id']]
    scope['variables'][scope['new_id']] = scope['new_type']
    scope['new_id'] = ''
    return [''], scope


@delay_scope_application
def eat_var_dec(scope, existing_classes):
    """Eat tokens corresponding to variable declarations

    Recognized jack syntax:
        'var' type varName (',' varName)* ';'
     
    Args:
        scope: tokens to analyse a class declaration from
        existing_classes (list): list of class names existing in the scope of
            the program. They should thus be recognized as valid data types.
    Returns:
        (vm code for the declaration, updated scope)
    """
    return apply_eaters(
        eat_by_value('var', 'keyword', optional=True),
        eat_type(existing_classes),
        eat_by_type('identifier', scope_key_to_update='new_id'),
        add_id_to_scope('local'),
        eat_until_none(
            eat_by_value(',', 'symbol', optional=True),
            eat_by_type('identifier', scope_key_to_update='new_id'),
            add_id_to_scope('local')),
        eat_by_value(';', 'symbol'))(scope)


############
# Statements
############


@delay_scope_application
def eat_statements(scope, existing_classes):
    """Eat tokens corresponding to statements

    Recognized jack syntax:
        statement*
     
    Args:
        scope: tokens to analyse a class declaration from
        existing_classes (list): list of class names existing in the scope of
            the program. They should thus be recognized as valid data types.
    Returns:
        (vm code for the declaration, updated scope)
    """
    return eat_until_none(eat_statement(existing_classes))(scope)


@delay_scope_application
def eat_statement(scope, existing_classes):
    """Eat tokens corresponding to a statement

    Recognized jack syntax:
        ifStatement | whileStatement | letStatement | doStatement 
            | returnStatement
     
    Args:
        scope: tokens to analyse a class declaration from
        existing_classes (list): list of class names existing in the scope of
            the program. They should thus be recognized as valid data types.
    Returns:
        (vm code for the declaration, updated scope)
    """
    if scope["tokens"][0] == tag_word('if', 'keyword'):
        return eat_if_statement(existing_classes)(scope)
    if scope["tokens"][0] == tag_word('while', 'keyword'):
        return eat_while_statement(existing_classes)(scope)
    if scope["tokens"][0] == tag_word('let', 'keyword'):
        return eat_let_statement(existing_classes)(scope)
    if scope["tokens"][0] == tag_word('do', 'keyword'):
        return eat_do_statement()(scope)
    if scope["tokens"][0] == tag_word('return', 'keyword'):
        return eat_return_statement(scope)
    return None, scope


@delay_scope_application
@nested_scope
def eat_if_statement(scope, existing_classes):
    """Eat tokens corresponding to a if statement

    Recognized jack syntax:
        'if' '(' expression ')’ '{' statements '}’ (else '{' statements '})?
     
    Args:
        scope: tokens to analyse a class declaration from
        existing_classes (list): list of class names existing in the scope of
            the program. They should thus be recognized as valid data types.
    Returns:
        (vm code for the declaration, updated scope)
    """
    return apply_eaters(
        eat_by_value('if', 'keyword', scope_key_to_update='loop'),
        inc_n_counter,
        eat_by_value('(', 'symbol'),
        eat_expression(optional=True),
        eat_by_value(')', 'symbol'),
        generate_if_goto,
        generate_true_label,
        eat_by_value('{', 'symbol'),
        eat_statements(existing_classes),
        eat_by_value('}', 'symbol'),
        generate_end_goto,
        generate_false_label,
        eat_by_value('else', 'keyword', optional=True),
        eat_by_value('{', 'symbol'),
        eat_statements(existing_classes),
        eat_by_value('}', 'symbol'),
        generate_end_label)(scope)


@no_scope_update
def generate_start_label(scope):
    """Generate a `start` label for `while` statements"""
    return [f'label WHILE_EXP{scope["current_while"]}']


@no_scope_update
def generate_end_label(scope):
    """Generate a `end` label for `if`/`while` statements"""
    name=scope['loop']
    return [f'label {name.upper()}_END{scope["current_"+name]}']


@no_scope_update
def generate_true_label(scope):
    """Generate a `true` label for `if` statements"""
    return [f'label IF_TRUE{scope["current_if"]}']


@no_scope_update
def generate_false_label(scope):
    """Generate a `false` label for `if` statements"""
    return [f'label IF_FALSE{scope["current_if"]}']


@no_scope_update
def generate_continue_goto(scope):
    """Generate a "continue" instruction for `while` statements"""
    return [f'goto WHILE_EXP{scope["current_while"]}']


@no_scope_update
def generate_if_goto(scope):
    """Generate the true/false switch instruction for `if` statements"""
    return [f'if-goto IF_TRUE{scope["current_if"]}',
            f'goto IF_FALSE{scope["current_if"]}']

@no_scope_update
def generate_break_goto(scope):
    """Generate a "break" instruction for `while` statements"""
    return [f'if-goto WHILE_END{scope["current_while"]}']


@no_scope_update
def generate_end_goto(scope):
    """Generate a "skip-else" instruction for `if` statements

    This instruction should only be generated if there is an `else` part"""
    if get_token_value(scope['tokens'][0]) == 'else':
        return [f'goto IF_END{scope["current_if"]}']
    return ['']


@delay_scope_application
@nested_scope
def eat_while_statement(scope, existing_classes):
    """Eat tokens corresponding to a while statement

    Recognized jack syntax:
        'while' '(' expression ')’ '{' statements '}’
     
    Args:
        scope: tokens to analyse a class declaration from
        existing_classes (list): list of class names existing in the scope of
            the program. They should thus be recognized as valid data types.
    Returns:
        (vm code for the declaration, updated scope)
    """
    return apply_eaters(
        eat_by_value('while', 'keyword', scope_key_to_update='loop'),
        inc_n_counter,
        generate_start_label,
        eat_by_value('(', 'symbol'),
        eat_expression(optional=True),
        eat_by_value(')', 'symbol'),
        insert_vm_code('not'),
        generate_break_goto,
        eat_by_value('{', 'symbol'),
        eat_statements(existing_classes),
        eat_by_value('}', 'symbol'),
        generate_continue_goto,
        generate_end_label)(scope)


def get_segment(scope, identifier):
    return [s for s in ['local', 'argument', 'field', 'static']
        if identifier in scope[s]][0]


def pop_destination(scope):
    """Generate a `pop` instruction to the scoped `destination` variable

    Arrays are managed with the `array_dest` key in scope"""
    segment = get_segment(scope, scope["destination"])
    index = scope[segment].index(scope["destination"])
    if not scope['array_dest']:
        return [f'pop {segment} {index}'.replace('field', 'this')], scope
    scope = scope.copy()
    scope['array_dest'] = False
    return ['pop temp 0', 'pop pointer 1', 'push temp 0', 'pop that 0'], scope


@delay_scope_application
def push_identifier(scope, identifier):
    """Generate a `push` instruction for the desired identifier"""
    segment = get_segment(scope, identifier)
    index = scope[segment].index(identifier)
    return [f'push {segment} {index}'.replace('field', 'this')], scope


@delay_scope_application
def point_array(scope, key_to_identifier):
    """Generate instructions corresponding to an array-lookup"""
    return push_identifier(scope[key_to_identifier])(scope)[0] + ['add'], scope


@delay_scope_application
def eat_let_statement(scope, existing_classes):
    """Eat tokens corresponding to a let statement

    Recognized jack syntax:
        'let' varName '=' expression ';'
     
    Args:
        scope: tokens to analyse a class declaration from
        existing_classes (list): list of class names existing in the scope of
            the program. They should thus be recognized as valid data types.
    Returns:
        (vm code for the declaration, updated scope)
    """
    return apply_eaters(
        eat_by_value('let', 'keyword'),
        eat_by_type('identifier', scope_key_to_update='destination'),
        apply_eaters(
            eat_by_value('[', 'symbol', optional=True,
                scope_key_to_update='array_dest'),
            eat_expression(),
            eat_by_value(']', 'symbol'),
            point_array('destination')),
        eat_by_value('=', 'symbol'),
        eat_expression(),
        eat_by_value(';', 'symbol'),
        pop_destination,
        break_on_none=False)(scope)


@delay_scope_application
@no_scope
def insert_vm_code(code):
    """Utility useful to insert fixed code with `apply_eaters`"""
    return [code]


@delay_scope_application
def eat_do_statement(scope):
    """Eat tokens corresponding to a do statement

    Recognized jack syntax:
        'do' subroutineCall ';'
     
    Args:
        scope: tokens to analyse a class declaration from
    Returns:
        (vm code for the declaration, updated scope)
    """
    return apply_eaters(
        eat_by_value('do', 'keyword'),
        eat_subroutine_call(),
        eat_by_value(';', 'symbol'),
        insert_vm_code('pop temp 0'))(scope)


@delay_scope_application
def fill_empty_returns(scope, expression_getter):
    """Catch empty returns and make them return `0`

    In the vm, all functions have to return something"""
    expression, scope = expression_getter(scope)
    if expression is None:
        return insert_vm_code('push constant 0')(scope)
    return expression, scope


@nested_scope
def eat_return_statement(scope):
    """Eat tokens corresponding to a return statement

    Recognized jack syntax:
        returnStatemen: 'return' expression? ';'

    Args:
        scope: tokens to analyse a class declaration from
    Returns:
        (vm code for the declaration, updated scope)
    """
    return apply_eaters(
        eat_by_value('return', 'keyword', 
            scope_key_to_update='op'),
        fill_empty_returns(eat_expression(optional=True)),
        eat_by_value(';', 'symbol'),
        insert_vm_code('return'),
        break_on_none=False)(scope)


#############
# Expressions
#############


def empty_callback(scope):
    """A neutral function in the context of `apply_eaters`"""
    return [''], scope


@delay_scope_application
@catch_none
def eat_expression_list(scope, callback=empty_callback):
    """Eat tokens corresponding to a return statement

    Recognized jack syntax:
        (expression (',' expression)*)?

    Args:
        scope: tokens to analyse a class declaration from
        callback: function to call between expressions
    Returns:
        (vm code for the declaration, updated scope)
    """
    return apply_eaters(
        eat_expression(optional=True),
        callback,
        eat_until_none(
            eat_by_value(',', 'symbol', optional=True),
            eat_expression(),
            callback))(scope)


@no_scope_update
def generate_op_instruction(scope):
    """Generate vm code corresponding to the operation in the `op` scope key"""
    return {
        '+': ['add'],
        '-': ['sub'],
        '*': ['call Math.multiply 2'],
        '/': ['call Math.divide 2'],
        '&': ['and'],
        '|': ['or'],
        '=': ['eq'],
        '>': ['gt'],
        '<': ['lt'],
    }[scope['op']]


@no_scope_update
def generate_unary_op_instruction(scope):
    """Generate vm code corresponding to the operation in the `op` scope key"""
    return {
        '-': ['neg'],
        '~': ['not']}[scope['op']]


@delay_scope_application
@nested_scope
def eat_expression(scope, optional=False):
    """Eat tokens corresponding to an expression

    Recognized jack syntax:
         term (op term)*

    Args:
        scope: tokens to analyse a class declaration from
        optional (bool): continue silently if no expression wath found
    Returns:
        (vm code for the declaration, updated scope)
    """
    return apply_eaters(
        eat_term(optional=optional),
        eat_until_none(
            eat_op(optional=True, scope_key_to_update='op'),
            eat_term(),
            generate_op_instruction))(scope)


@delay_scope_application
def eat_op(scope, optional=False, scope_key_to_update=None):
    """Eat tokens corresponding to an operation symbol

    Recognized jack syntax:
        '+'|'-'|i'*'|'/'|'&'|'|'|'='|'>'|'<'

    Args:
        scope: tokens to analyse a class declaration from
        optional (bool): continue silently if no expression wath found
    Returns:
        (vm code for the declaration, updated scope)
    """
    if scope_key_to_update is None:
        return eat_by_value('+|-|*|/|&|&OR|=|>|<', 'symbol', 
            optional=optional)(scope)
    return eat_by_value('+|-|*|/|&|&OR|=|>|<', 'symbol', 
        optional=optional, scope_key_to_update=scope_key_to_update
    )(scope)


def is_a_class(scope, identifier):
    """Check if an identifier is a variable or a class name"""
    return identifier not in scope['variables'].keys()


@delay_scope_application
@nested_scope
def eat_subroutine_call(scope):
    """Eat tokens corresponding to a sub-routine call

    Recognized jack syntax:
        subroutineName '(' expressionList ')' 
            | (className|varname)'.'subroutineName'('expressionList')'

    Args:
        scope: tokens to analyse a class declaration from
    Returns:
        (vm code for the declaration, updated scope)
    """
    identifier, scope = eat_by_type('identifier')(scope)
    dot, scope = eat_by_value('.', 'symbol', 
        optional=True)(scope)
    if dot is not None:
        callee, scope = eat_by_type('identifier')(scope)
    else:
        callee=None
    arguments, scope = apply_eaters(
        eat_by_value('(', 'symbol'),
        eat_expression_list(callback=inc_scope_element('n_args')),
        eat_by_value(')', 'symbol')
    )(scope)

    if dot is None:
        # subroutineName '(' expressionList ')' syntax
        func_call = scope['class'] + '.' + get_token_value(identifier[0])
        return ['push pointer 0'] + arguments + [
            f'call {func_call} {scope["n_args"] + 1}'], scope

    # (className|varname)'.'subroutineName'('expressionList')' syntax
    caller = get_token_value(identifier[0])
    callee = get_token_value(callee[0])
    if is_a_class(scope, caller):
        func_call = caller+ '.' + callee
        return arguments + [f'call {func_call} {scope["n_args"]}'], scope
    var_class=scope['variables'][caller]
    return push_identifier(caller)(scope)[0] + arguments + [
        f'call {var_class+ "." + callee} {scope["n_args"] + 1}'], scope


@delay_scope_application
def eat_term(scope, optional=False):
    """Eat tokens corresponding to a term

    Recognized jack syntax:
        integerConstant | stringConstant | keywordConstant | varName
            | varName'['expression']' | subroutineCall | '('expression')' 
            | unaryOp term

    Args:
        scope: tokens to analyse a class declaration from
        optional (bool): continue silently if no expression wath found
    Returns:
        (vm code for the declaration, updated scope)
    """
    initial_scope = scope.copy()

    # integerConstant syntax
    integer_constant, scope = eat_by_type('integerConstant', 
        optional=True)(scope)
    if integer_constant is not None:
        return [f'push constant {get_token_value(integer_constant[0])}'], scope 

    # integerConstant syntax
    string_constant, scope = eat_by_type('stringConstant', 
        optional=True)(scope)
    if string_constant is not None:
        string = get_token_value(initial_scope['tokens'][0])
        return [f'push constant {len(string)}', 'call String.new 1'] + sum([
            [f'push constant {ord(s)}', 'call String.appendChar 2']
            for s in string
        ], []), scope

    # keywordConstant: 'true'|'false'|'null'|'this'
    is_keyword, scope = eat_by_value('true|false|null|this', 'keyword', 
        optional=True)(scope)
    if is_keyword is not None:
        return {
            'true': ['push constant 0', 'not'],
            'false': ['push constant 0'],
            'null': ['push constant 0'],
            'this': ['push pointer 0']
        }[get_token_value(initial_scope['tokens'][0])], scope

    # varName|varName'['expression']|subroutineCall'
    identifier, scope = eat_by_type('identifier', optional=True)(
        scope)
    if identifier is not None:
        if scope["tokens"][0] == tag_word('[', 'symbol'):
            return apply_eaters(
                eat_by_type('identifier', optional=True, 
                    scope_key_to_update='array_identifier'),
                eat_by_value('[', 'symbol'),
                eat_expression(),
                point_array('array_identifier'),
                eat_by_value(']', 'symbol'),
                insert_vm_code('pop pointer 1'),
                insert_vm_code('push that 0')
            )(initial_scope)
        if (scope["tokens"][0] == tag_word('.', 'symbol') 
                or scope["tokens"][0] == tag_word('(', 'symbol')):
            return eat_subroutine_call()(initial_scope)
        return push_identifier(get_token_value(identifier[0]))(scope)

    # '('expression')'
    expression, scope = apply_eaters(
        eat_by_value('(', 'symbol', optional=True),
        eat_expression(),
        eat_by_value(')', 'symbol'))(scope)
    if expression is not None:
        return expression, scope

    # unaryOp term
    # unaryOp: '-'|'~'
    unary_term, scope = apply_eaters(
        eat_by_value('-|~', 'symbol', optional=True, 
            scope_key_to_update='op'),
        eat_term(),
        generate_unary_op_instruction)(scope)
    if unary_term is not None:
        return unary_term, scope

    if optional:
        return None, scope
    
    raise ValueError(f'Expected a term, found `{scope["tokens"][:5]}...`')


#############
# Compilation
#############


def remove_empty_instructions(tokens):
    return [token for token in tokens if len(token) > 0]


def process_file(file_path, existing_classes):
    """Read, tokenize, compile and clean a file"""
    return '\n'.join(remove_empty_instructions(eat_class(
       new_scope(tokenize(read_file(file_path))),existing_classes)[0])) + '\n'


project_path = Path(sys.argv[1])

existing_classes = ['Math', 'String', 'Array', 'Output', 'Screen', 'Keyboard',
    'Memory', 'Sys'] + [
    f.name[:-5] # Remove the `.jack` extention
    for f in project_path.parent.glob('*.jack')]

if project_path.is_file(): # Single file translation
    print(process_file(project_path, existing_classes))
else: # Folder
    to_process = project_path.parent.glob('*.jack')
    for file_path in to_process:
        output_file = Path(file_path.parent.expanduser() 
            / file_path.name.replace('.jack', '.vm'))
        print('Compiling', file_path.name)
        output_file.write_text(process_file(file_path, existing_classes))
