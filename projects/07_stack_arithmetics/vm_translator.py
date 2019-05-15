"""Virtual machine code to assembly code translator for the hack computer

Usage:

python vm_translator.py path

If `path` is a file: output the corresponding assembly code to standard output
If `path` is a folder:
- look for `.vm` files in the folder ignoring hidden files
- translate them all
- merge the corresponding assembly files 
- pre-pend the `boot` assembly sequence
- output the result to standard output

Corresponding projects in the nand2tetris coursework: 07 and 08

# VM translator implementation details:
File parsing (line 170)
Utilities (line 213)
Memory access (line 248)
Arithmetic & Logic (line 364)
Branching (line 446)
Functions (line 475)
Translation (line 574)

# VM language specifications:

The virtual machine, VM, is an intermediate level between high-level code 
programing and machine-level code programing. The goal is to provide enough 
logic to support high-level concepts such as functions and objects, while still
being simple enough to be easily translated into machine language. 
This has two benefits: 
- writing high-level language compilers is easier since a part of the logic has
    been taken care of.
- once compiled to vm-code, programs are still portable from one machine to
    another but are already very similar to machine code: it's easier to support
    multiple machines.

The virtual language supported here implements a stack logic and 8 memory 
segments. 

The stack logic is what enables programs with objects, functions and branches. 
It is based on a `stack`, a last-in-first-out queue, into which numbers are 
stored and functions/operations are performed. For example, if we want to 
compute `5+6`, that is add(5, 6), we would:
| Action done                                               | Resulting stack  |
--------------------------------------------------------------------------------
| Append the first argument, 5, to the stack                | [5]              |
| Append the second argument, 6, to the stack               | [5, 6]           |
| Feed enough elements to the function add (it takes two)   | []               |
| Append the result to the stack                            | [11]             |

This way, we can compute any expression: f(3, g(4, 5), 6) * 2 results in:
| Action done                                               | Resulting stack  |
--------------------------------------------------------------------------------
| Append 3 to the stack                                     | [3]              |
| Append 4 to the stack                                     | [3, 4]           |
| Append 5 to the stack                                     | [3, 4, 5]        |
| Compute g on two arguments and store the result, G        | [3, G]           |
| append 6 to the stack                                     | [3, G, 6]        |
| Compute f on three arguments and store the result, F      | [F]              |
| append 2 to the stack                                     | [F, 2]           |
| multiply two elements and store the result, M             | [M]              |

The available stack instructions are (on stack [a, b]):
- ALU instructions
    add : add(a, b) -> a+b
    sub : sub(a, b) -> a-b
    neg : neg(b) -> -b (2th complement)
    eq  : eq(a, b) -> true if a=b else false (true=0xFFFF=-1, false=0x0000=0)
    gt  : gt(a, b) -> true if a>b
    lt  : lt(a, b) -> true if a<b
    and : and(a, b) -> bitwise AND
    or  : or(a, b) -> bitwise OR
    not : not(b) -> bitwise NOT
- branching instructions
    label label-name    : declare the label `label-name`
    goto label-name     : jump to label `label-name`
    if-goto label-name  : jump to label `label-name` if `true` is ontop of the 
        stack (consumes the topmost stack value)
- Function instructions
    function name n-locals      : start the declaration of a function with 
        n-locals local arguments
    return                      : declare the end of a function. The topmost 
        stack value is returned
    call function-name n-args   : call a function. The n-args topmost stack
        values are removed from the current stack and passed as arguments. This 
        called function will have its own "private" stack. Once it returns, its
        return value is appended to the stack. 
- Memory instructions
    push segment index  : Load segment[index] ontop of the stack where `segment`
        is the name of a memory segment as described below.
    pop segment index   : Write the topmost stack value to segment[index] and 
        remove it from the stack

The memory segments are:
- local: store local variables of a function, pointed onto by RAM[1].
- argument: store arguments of a function, pointed onto by RAM[2].
- this: store the current object, pointed onto by RAM[3].
- that: store current array, pointed onto by RAM[4].
- pointer: Segment containing `this` and `that`, that is RAM[3->4].
- temp: store temporary variables, reserved to the vm-implementation, RAM[5->15]
- static: store static variables, RAM[16->255]. Interactions with this segment 
    are done only with assembly labels, delegating the actual addressing to the 
    assembler.
- constant: a virtual segment containing all the integers. Looking at the `i`th 
    value of this segment actually returns the integer `i`.
Each of those segments can be read from using the `push` instruction and written
to using the `pop` instruction (except for the constant segment which is 
read-only). 

Note on the difference between "direct" and "pointed" segments: each segment has
a base address: 1 for local, 2 for argument, 3 for pointer, 16 for static,... 
`pointer`, `temp` and `static` are direct segments: writing to the `i`th value 
of those segments is just writing at `RAM[base address + i]` (with `i` starting
from 0).
`local`, `argument`, `this` and `that` are pointed segments: writing to the 
`i`th value of those segments actually consists of writing at 
`RAM[RAM[base address] + i]`.
"""

import sys
from pathlib import Path


def new_scope(function, scope_stack):
    """Create a new scope with given scope-stack
    
    Translating if-else conditions and function calls require the automatic
    generation of assembly labels. And each label should be unique. Since this
    vm-translator implementation only parses one instruction at a time, it needs
    a way to be sure it does not create twice the same label. This is the 
    purpose of the scope: It keeps track of the current function name and how 
    many labels have already been created in this function. The scope-stack 
    enables support of nested functions, by pushing parent scopes to the stack
    and poping them when exiting a function.
    """
    return {
        'function': function,
        'lt_counter': 0,
        'eq_counter': 0,
        'gt_counter': 0,
        'call_counter': 0,
        'scope_stack': scope_stack
    }


def no_scope(f):
    """Manage scope-handling around a scope-less function"""
    def helper(line, scope):
        return f(line), scope
    return helper


def no_scope_update(f):
    """Manage scope-handling around a function that only reads the scope"""
    def helper(line, scope):
        return f(line, scope), scope
    return helper


def inc_scope_key(scope, key):
    """Increment one key of the scope"""
    scope = scope.copy()
    scope[key] += 1
    return scope


##############
# File parsing
##############


def get_file_name(path):
    """Exctract the name of the vm-file pointed onto by `path`"""
    return path.split('/')[-1].split('.vm')[0]


def read_file(path):
    """Read a vm file and preprocess it
    
    Preprocessing includes:
    - Remove carriage returns and split file on new lines
    - Remove comments and trailing blanks in the lines
    - Remove empty lines
    """
    def read_lines():
        """Read the file given as script argument and split on new lines

        Carriage returns are removed.
        """
        return Path(path).expanduser().read_text().replace(
            '\r', '').split('\n')

    def filter_comment_and_trailing_blank_in_lines(lines):
        """Remove blanks and trailing comments from each line
        
        Anything inside a line, after a "//" sequence is a comment.
        """
        def filter_comment_and_trailing_blank_in_line(l):
            return l.split('//')[0].strip()
        return [filter_comment_and_trailing_blank_in_line(l) for l in lines]

    def remove_empty_lines(file):
        return [l for l in file if len(l) > 0]

    return remove_empty_lines(
        filter_comment_and_trailing_blank_in_lines(
            read_lines()))


###########
# Utilities
###########


def comment(string):
    """Format `string` as an assembly comment"""
    return '// ' + string


def inc_stack():
    """Generate asm code corresponding to a stack pointer increment"""
    return ['@SP', 'M=M+1']


def dec_stack():
    """Generate asm code corresponding to a stack pointer decrement"""
    return ['@SP', 'M=M-1']


def point():
    """Generate asm code corresponding to a pointer lookup with address M"""
    return ['A=M']


def dec_stack_and_point():
    """Generate asm code corresponding to decrementing the stack and point"""
    return dec_stack() + point()


def set_d_at(i):
    """Get `i` into the D register"""
    return [f'@{i}', 'D=A']


###############
# Memory access
###############


def push_D():
    """Push the content of the D-register on top of the stack"""
    return ['@SP', 'A=M', 'M=D']


def set_D_to_constant(i, _):
    """Set D to the `i`th value of the constant segment (that is `i`)"""
    return set_d_at(i)


def set_D_to_direct_segment(base):
    """Generate a D-setter for desired "direct" segment

    A direct segment is a segment starting directly at its shortcut RAM 
    address. For example, the `pointer` segment is RAM[3-4] and @pointer <-> @3.
    """
    def code_generator(i, _):
        """Set D to the `i`th value of desired "direct" segment"""
        return set_d_at(i) + [f'@{base}','A=D+A', 'D=M']
    return code_generator


def put_pointed_segment_into_D(base):
    """Generate a D-setter for desired "pointed" segment

    A direct segment is a segment starting at the address pointed onto by its 
    shortcut RAM address. For example, the `local` segment starts at the address
    contained in RAM[@LCL].
    """
    def code_generator(i, _):
        """Set D to the `i`th value of desired "pointed" segment"""
        return set_d_at(i) + [f'@{base}', 'A=D+M', 'D=M']
    return code_generator


def get_static_label(scope, i):
    """Generate the A-instruction pointing the `i`th `static` segment value"""
    return ['@' + scope['function'].split('.')[0] + f'.{i}']


def put_static_into_D(i, scope):
    """Set D to the `i`th value of the `static` segment"""
    return get_static_label(scope, i) + ['D=M']


# {segment: corresponding D-setter} dict
put_segment_into_D_map = {
    'local': put_pointed_segment_into_D('LCL'),
    'argument': put_pointed_segment_into_D('ARG'),
    'this': put_pointed_segment_into_D('THIS'),
    'that': put_pointed_segment_into_D('THAT'),
    'constant': set_D_to_constant,
    'static': put_static_into_D,
    'pointer': set_D_to_direct_segment(3),
    'temp': set_D_to_direct_segment(5),
}


def get_segment(instruction):
    """Get segment name from a push/pop instruction"""
    return instruction.split(' ')[1]


def get_index(instruction):
    """Get index from a push/pop instruction"""
    return instruction.split(' ')[2]


@no_scope_update
def push(push_instruction, scope):
    """Generate assembly code for a push instruction"""
    return put_segment_into_D_map[
        get_segment(push_instruction)
    ](get_index(push_instruction), scope) + push_D()


# {segment: corresponding address lookup into D} dict
put_var_addr_into_d_map = {
    'local': lambda i, _: set_d_at(i)+ [f'@LCL', 'D=D+M'],
    'argument': lambda i, _: set_d_at(i)+ [f'@ARG', 'D=D+M'],
    'this': lambda i, _: set_d_at(i)+ [f'@THIS', 'D=D+M'],
    'that': lambda i, _: set_d_at(i)+ [f'@THAT', 'D=D+M'],
    # No pop to constants
    'static': lambda i, scope: get_static_label(scope, i) + ['D=A'],
    'pointer': lambda i, _: set_d_at(i)+ [f'@3', 'D=D+A'],
    'temp': lambda i, _: set_d_at(i)+ [f'@5', 'D=D+A'],
}


def append_d_to_stack():
    """Generate assembly code saving the value of D ontop of the stack"""
    return ['@SP', 'A=M+1', 'M=D']


def pop_current_to_segment(pop_instruction, scope):
    """Generate assembly code to put current stack value into desired segment"""
    return (
        put_var_addr_into_d_map[get_segment(pop_instruction)](
            get_index(pop_instruction), scope) + # D = addr(segment) + index
        append_d_to_stack() + [ # *(SP + 1) = D = segment + index
        'A=A-1', 'D=M'] + [ # D = *(SP)
        'A=A+1', 'A=M'] + [ # A=*(SP + 1)=addr(segment) + index
        'M=D'])              # M=*(addr(segment)+index)=D


@no_scope_update
def pop(pop_instruction, scope):
    """Generate assembly code for a pop instruction"""
    return dec_stack() + pop_current_to_segment(pop_instruction, scope)


####################
# Arithmetic & Logic
####################


@no_scope
def add(_):
    """Generate assembly code for an addition on the stack"""
    return dec_stack_and_point() + ['D=M'] + dec_stack_and_point() + ['M=D+M']


@no_scope
def sub(_):
    """Generate assembly code for a substraction on the stack"""
    return dec_stack_and_point() + ['D=M'] + dec_stack_and_point() + ['M=M-D']


def sub_to_D():
    """Same as `sub` but puts the result into D instead of onto the stack"""
    return dec_stack_and_point() + [ 'D=M'] + dec_stack_and_point() + ['D=M-D']


@no_scope
def neg(_):
    """Generate assembly code for a negation on the stack"""
    return dec_stack_and_point() + ['M=-M']


def eq(_, scope):
    """Generate assembly code for an equality test on the stack"""
    return (
        sub_to_D() + [
            'M=-1', # By default, result = 1111 = True
            f'@__{scope["function"]}_eq.{scope["eq_counter"]}', 
            'D;JEQ', # If x-y=0: skip next part
            '@SP', 'A=M', 'M=0', # result = 0000 = False
            f'(__{scope["function"]}_eq.{scope["eq_counter"]})'],
        inc_scope_key(scope, 'eq_counter'))


def gt(_, scope):
    """Generate assembly code for an "greater than" test on the stack"""
    return (
        sub_to_D() + [
            'M=-1', # By default, result = 1111 = True
            f'@__{scope["function"]}_gt.{scope["gt_counter"]}', 
            'D;JGT', # If x-y>0: skip next part
            '@SP', 'A=M', 'M=0', # result = 0000 = False
            f'(__{scope["function"]}_gt.{scope["gt_counter"]})'],
        inc_scope_key(scope, 'gt_counter'))


def lt(_, scope):
    """Generate assembly code for an "lower than" test on the stack"""
    return (
        sub_to_D() + [
            'M=-1', # By default, result = 1111 = True
            f'@__{scope["function"]}_lt.{scope["lt_counter"]}', 
            'D;JLT', # If x-y<0: skip next part
            '@SP', 'A=M', 'M=0', # result = 0000 = False
            f'(__{scope["function"]}_lt.{scope["lt_counter"]})'], 
        inc_scope_key(scope, 'lt_counter'))


@no_scope
def and_f(_):
    """Generate assembly code for a "and" instruction"""
    return dec_stack_and_point() + ['D=M'] + dec_stack_and_point() + ['M=D&M']


@no_scope
def or_f(_):
    """Generate assembly code for a "or" instruction"""
    return dec_stack_and_point() + ['D=M'] + dec_stack_and_point() + ['M=D|M']


@no_scope
def not_f(_):
    """Generate assembly code for a "not" instruction"""
    return dec_stack_and_point() + ['M=!M']


###########
# Branching
###########


def get_asm_label(label_instruction, scope):
    """Generate assembly label name for specified instruction"""
    return f'{scope["function"]}${label_instruction.split(" ")[1]}'


@no_scope_update
def label(label_instruction, scope):
    """Generate assembly code for a "label" instruction"""
    return [f'({get_asm_label(label_instruction, scope)})']


@no_scope_update
def if_goto(if_goto_instruction, scope):
    """Generate assembly code for a "if-goto" instruction"""
    return dec_stack_and_point() + [
        'D=M', f'@{get_asm_label(if_goto_instruction, scope)}', 'D;JNE']


@no_scope_update
def goto(goto_instruction, scope):
    """Generate assembly code for a "goto" instruction"""
    return [f'@{get_asm_label(goto_instruction, scope)}', '0;JMP']

 
###########
# Functions
###########


def enter_function_scope(function, scope):
    """Create a nested scope for the current function"""
    return new_scope(function, [scope])


def get_function_name(function_instruction):
    """Extract function name from a `function` instruction"""
    return function_instruction.split(' ')[1]


def get_n_locals(function_instruction):
    """Extract the amount of local variables from a `function` instruction"""
    return int(function_instruction.split(' ')[2])


def function(function_instruction, scope):
    """Generate assembly code for a `function` instruction"""
    scope = enter_function_scope(get_function_name(function_instruction), scope)
    return [f'({scope["function"]})', '@0', 'D=A', # @0 <=> @SP
    ] + sum([
        point() + ['M=D'] + inc_stack()
        for i in range(get_n_locals(function_instruction))
    ], []), scope


@no_scope
def return_f(_):
    """Generate assembly code for a `return` instruction

    Memory structure when `return` is called:
    ARG  -> parent stack pointer = return memory location
    ARG+1-> SP should be reset to here
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
            return program address
            prev. LCL
            prev. ARG
            prev. THIS
            prev. THAT
    LCL  ->  
    """
    return [
        '@ARG', 'D=M', '@5', 'M=D',              # temp0=@ARG=mem loc of return
        '@SP', 'A=M-1', 'D=M', '@6', 'M=D',      # temp1=return value
        '@ARG', 'D=M+1', '@SP', 'M=D',           # Reset SP to prev stack + 1 
        '@LCL', 'AM=M-1', 'D=M', '@THAT', 'M=D', # Reset THAT
        '@LCL', 'AM=M-1', 'D=M', '@THIS', 'M=D', # Reset THIS
        '@LCL', 'AM=M-1', 'D=M', '@ARG', 'M=D',  # Reset ARG
        '@LCL', 'AM=M-1', 'A=A-1', 'D=M', '@7', 'M=D',# temp2=PC return addr
        '@LCL', 'A=M', 'D=M', '@LCL', 'M=D',     # Reset LCL
        '@6', 'D=M', '@5', 'A=M', 'M=D',         # *temp0=temp2
        '@7', 'A=M', '0;JMP',                    # jump temp2=PC return addr
    ]



def get_n_var(call_instruction):
    """Extract the number of variables from a `call` instruction"""
    return int(call_instruction.split(' ')[2])


def get_target_func(call_instruction):
    """Extract the function name from a `call` instruction"""
    return call_instruction.split(' ')[1]


def call(call_instruction, scope):
    """Generate assembly code for a `call` instruction"""
    return [
        # D=return adress
        f'@{scope["function"]}$ret{scope["call_counter"]}', 'D=A',
        # save ReturnAdd
        '@SP', 'A=M', 'M=D',                                      
        # save LCL
        '@LCL', 'D=M', '@SP', 'A=M+1', 'M=D', 
        # Use LCL to keep track of the stack
        'D=A+1', '@LCL', 'M=D',                                   
        # Save Arg (note: did not move stack-lcl)
        '@ARG', 'D=M', '@LCL', 'A=M', 'M=D',                      
        # (move stack-lcl) and Save THIS
        '@THIS', 'D=M', '@LCL', 'AM=M+1', 'M=D',                   
        # (move stack-lcl) and Save THAT
        '@THAT', 'D=M', '@LCL', 'AM=M+1', 'M=D',                   
        # Set ARG
        '@SP', 'D=M'] + ['D=D-1' for _ in range(get_n_var(call_instruction))
        ] + ['@ARG', 'M=D', 
        # Set LCL & SP
        '@LCL', 'MD=M+1', '@SP', 'M=D',                           
        # Run function
        f'@{get_target_func(call_instruction)}', '0;JMP',                      
        # Declare return label
        f'({scope["function"]}$ret{scope["call_counter"]})',
    ], inc_scope_key(scope, 'call_counter')


#############
# Translation
#############


# {instruction: assembly code generator} dict
translation_map = {
    # Memory
    'push': push,
    'pop': pop,
    # Arithmetic & Logic
    'add': add,
    'sub': sub,
    'neg': neg,
    'eq': eq,
    'gt': gt,
    'lt': lt,
    'and': and_f,
    'or': or_f,
    'not': not_f,
    # Branching
    'label': label,
    'if-goto': if_goto,
    'goto': goto,
    # Function
    'function': function,
    'return': return_f,
    'call': call
}


# alu_actions, they all need the stack pointer to be incremented after execution
alu_actions = {'add', 'sub', 'neg', 'eq', 'gt', 'lt', 'and', 'or', 'not'}


def get_instruction_name(instruction):
    """Extract the name of the instruction"""
    return instruction.split(' ')[0]


def inc_stack_if_needed(instruction):
    """Generate assembly code to increment the stack pointer if needed"""
    if get_instruction_name(instruction) in alu_actions.union({'push'}):
        return inc_stack()
    return []


def translate_instruction(instruction, scope):
    """Generate assembly code corresponding to `instruction`"""
    new_asm_lines, scope = translation_map[get_instruction_name(instruction)](
        instruction, scope)
    return new_asm_lines + inc_stack_if_needed(instruction), scope

def translate_file(lines, scope):
    """Generate assembly code corresponding to a vm file"""
    asm_code_lines = []
    for line in lines:
        new_asm_lines, scope=translate_instruction(line, scope)
        asm_code_lines += [comment(line)] + new_asm_lines
    return asm_code_lines


def get_scope(file_path):
    """Generate a scope for the vm file pointed onto by `file_path`"""
    return new_scope(get_file_name(file_path), [])


def merge_asm_code(*args):
    """Merge assembly code from different files"""
    return '\n'.join(args)


def get_boot():
    """Generate assembly code corresponding to the boot sequence"""
    return merge_asm_code(*['@256', 'D=A', '@0', 'M=D' # SP=250
    ], *translate_instruction('call Sys.init 0', new_scope('Boot', []))[0])


def translate_and_post_process_file(file_path):
    """Translate all the instructions from a vm file into one asm string"""
    return merge_asm_code(
        *translate_file(read_file(file_path), get_scope(file_path.name)))


def is_hidden(file_path):
    """Check if `file_path` points to a hidden file"""
    return file_path.name.startswith('.')


project_path = Path(sys.argv[1])
if project_path.is_file(): # Single file translation
    print(translate_and_post_process_file(project_path))
else: # Folder
    print(merge_asm_code(
        get_boot(),
        *[translate_and_post_process_file(file_path)
             for file_path in project_path.glob('*.vm') 
             if not is_hidden(file_path)]))
