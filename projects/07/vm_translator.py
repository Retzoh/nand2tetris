import sys
from pathlib import Path


def no_scope(f):
    def helper(line, scope):
        return f(line), scope
    return helper


def no_scope_update(f):
    def helper(line, scope):
        return f(line, scope), scope
    return helper


def inc_scope_key(scope, key):
    scope = scope.copy()
    scope[key] += 1
    return scope


def new_scope(function, scope_stack):
    return {
        'function': function,
        'lt_counter': 0,
        'eq_counter': 0,
        'gt_counter': 0,
        'call_counter': 0,
        'scope_stack': scope_stack
    }


##############
# File parsing
##############


def get_file_name(path):
    return path.split('/')[-1].split('.vm')[0]


def read_file(path):
    def read_lines():
        return Path(path).expanduser().read_text().split('\n')

    def filter_comment_and_trailing_blank_in_lines(lines):
        def filter_comment_and_trailing_blank_in_line(l):
            return l.split('//')[0].strip()
        return [filter_comment_and_trailing_blank_in_line(l) for l in lines]

    def remove_empty_lines(file):
        return [l for l in file if len(l) > 0]

    return remove_empty_lines(
        filter_comment_and_trailing_blank_in_lines(
            read_lines()))


def comment_line(line):
    return '// ' + line


def inc_stack():
    return ['@SP', 'M=M+1']


def dec_stack():
    return ['@SP', 'M=M-1']


def point():
    return ['A=M']


def dec_stack_and_point():
    return dec_stack() + point()


########
# Memory
########
#Segments:
#local
#argument
#this
#that
#constant
#static
#pointer
#temp


def set_d_at(i):
    return [f'@{i}', 'D=A']


def push_D():
    return ['@SP', 'A=M', 'M=D']


def put_pointed_segment_into_D(base):
    def push_segment(i, _):
        return set_d_at(i) + [f'@{base}', 'A=D+M', 'D=M']
    return push_segment


def put_direct_segment_into_D(base):
    def push_segment(i, _):
        return set_d_at(i) + [f'@{base}','A=D+A', 'D=M']
    return push_segment


def put_constant_into_D(i, _):
    return set_d_at(i)


def get_static_label(scope, i):
    return ['@' + scope['function'].split('.')[0] + f'.{i}']


def put_static_into_D(i, scope):
    return get_static_label(scope, i) + ['D=M']


put_segment_into_D_map = {
    'local': put_pointed_segment_into_D('LCL'),
    'argument': put_pointed_segment_into_D('ARG'),
    'this': put_pointed_segment_into_D('THIS'),
    'that': put_pointed_segment_into_D('THAT'),
    'constant': put_constant_into_D,
    'static': put_static_into_D,
    'pointer': put_direct_segment_into_D(3),
    'temp': put_direct_segment_into_D(5),
}


def get_segment(line):
    return line.split(' ')[1]


def get_index(line):
    return line.split(' ')[2]


@no_scope_update
def push(line, scope):
    return put_segment_into_D_map[
        get_segment(line)](get_index(line), scope) + push_D()


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
    return ['@SP', 'A=M+1', 'M=D']


def pop_current_to_segment(line, scope):
    return (put_var_addr_into_d_map[get_segment(line)](get_index(line), scope) + 
        append_d_to_stack() + [ # *(SP + 1) = D = segment + i
        'A=A-1', 'D=M'] + [ # D = *(SP)
        'A=A+1', 'A=M'] + [ # A=*(SP + 1)=LCL + i
        'M=D'])              # M=D


@no_scope_update
def pop(line, scope):
    return dec_stack() + pop_current_to_segment(line, scope)


####################
# Arithmetic & Logic
####################


@no_scope
def add(_):
    return dec_stack_and_point() + ['D=M'] + dec_stack_and_point() + ['M=D+M']


@no_scope
def sub(_):
    return dec_stack_and_point() + ['D=M'] + dec_stack_and_point() + ['M=M-D']


@no_scope
def neg(_):
    return dec_stack_and_point() + ['M=-M']


def eq(_, scope):
    return (
        dec_stack_and_point() + [
            'D=M'] + dec_stack_and_point() + ['D=M-D', 
            'M=-1',                                     # By default, result = 1111 ...
            f'@__{scope["function"]}_eq.{scope["eq_counter"]}', 
            'D;JEQ',                                    # If x-y=0: skip next part
            '@SP', 'A=M', 'M=0',                        # result = 0000 ...
            f'(__{scope["function"]}_eq.{scope["eq_counter"]})'],
        inc_scope_key(scope, 'eq_counter'))


def gt(_, scope):
    return (
        dec_stack_and_point() + [
            'D=M'] + dec_stack_and_point() + ['D=M-D',
            'M=-1',                                     # By default, result = 1111 ...
            f'@__{scope["function"]}_gt.{scope["gt_counter"]}', 
            'D;JGT',                                    # If x-y>0: skip next part
            '@SP', 'A=M', 'M=0',                        # result = 0000 ...
            f'(__{scope["function"]}_gt.{scope["gt_counter"]})'],
        inc_scope_key(scope, 'gt_counter'))


def lt(_, scope):
    return (
        dec_stack_and_point() + [
            'D=M'] + dec_stack_and_point() + ['D=M-D',
            'M=-1',                                      # By default, result = 1111 ...
            f'@__{scope["function"]}_lt.{scope["lt_counter"]}', 
            'D;JLT',                                    # If x-y<0: skip next part
            '@SP', 'A=M', 'M=0',                        # result = 0000 ...
            f'(__{scope["function"]}_lt.{scope["lt_counter"]})'], 
        inc_scope_key(scope, 'lt_counter'))


@no_scope
def and_f(_):
    return dec_stack_and_point() + ['D=M'] + dec_stack_and_point() + ['M=D&M']


@no_scope
def or_f(_):
    return dec_stack_and_point() + ['D=M'] + dec_stack_and_point() + ['M=D|M']


@no_scope
def not_f(_):
    return dec_stack_and_point() + ['M=!M']


###########
# Branching
###########


def get_asm_label(line, scope):
    return f'{scope["function"]}${line.split(" ")[1]}'


@no_scope_update
def label(line, scope):
    return [f'({get_asm_label(line, scope)})']


@no_scope_update
def if_goto(line, scope):
    return dec_stack_and_point() + [
        'D=M', f'@{get_asm_label(line, scope)}', 'D;JNE']


@no_scope_update
def goto(line, scope):
    return [f'@{get_asm_label(line, scope)}', '0;JMP']

 
###########
# Functions
###########


def enter_function_scope(function, scope):
    return new_scope(function, [scope])


def get_function_name(line):
    return line.split(' ')[1]


def get_n_locals(line):
    return int(line.split(' ')[2])


def function(line, scope):
    scope = enter_function_scope(get_function_name(line), scope)
    return [f'({scope["function"]})', '@0', 'D=A', # @0 <=> @SP
    ] + sum([
        point() + ['M=D'] + inc_stack()
        for i in range(get_n_locals(line))
    ], []), scope


@no_scope
def return_f(line):
    """
    Mem structure:
    ARG  -> prev. SP = return memory location
    ARG+1-> SP should be reset to here
    ////..................................////
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
        '@7', 'A=M', '0;JMP',                           # jump temp2=PC return addr
    ]



def get_n_var(line):
    return int(line.split(' ')[2])


def get_target_func(line):
    return line.split(' ')[1]


def call(line, scope):
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
        '@SP', 'D=M'] + ['D=D-1' for _ in range(get_n_var(line))
        ] + ['@ARG', 'M=D', 
        # Set LCL & SP
        '@LCL', 'MD=M+1', '@SP', 'M=D',                           
        # Run function
        f'@{get_target_func(line)}', '0;JMP',                      
        f'({scope["function"]}$ret{scope["call_counter"]})',
    ], inc_scope_key(scope, 'call_counter')


#############
# Translation
#############


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


alu_actions = {'add', 'sub', 'neg', 'eq', 'gt', 'lt', 'and', 'or', 'not'}

def get_instruction(line):
    return line.split(' ')[0]


def inc_stack_if_needed(line):
    return inc_stack() if get_instruction(line) in alu_actions.union({'push'}) else []


def translate_line(line, scope):
    new_asm_lines, scope = translation_map[get_instruction(line)](line, scope)
    return new_asm_lines + inc_stack_if_needed(line), scope

def translate_file(lines, scope):
    asm_code_lines = []
    for line in lines:
        new_asm_lines, scope=translate_line(line, scope)
        asm_code_lines += [comment_line(line)] + new_asm_lines
    return asm_code_lines


def get_clean_scope(file_path):
    return new_scope(get_file_name(file_path), [])


def merge_asm_code(*args):
    return '\n'.join(args)


def get_boot():
    return merge_asm_code(*['@256', 'D=A', '@0', 'M=D' # SP=250
    ], *translate_line('call Sys.init 0', new_scope('Boot', []))[0])


def translate_and_merge_file(file_path):
    return merge_asm_code(
        *translate_file(read_file(file_path), get_clean_scope(file_path.name)))


def is_hidden(file_path):
    return file_path.name.startswith('.')


project_path = Path(sys.argv[1])
if project_path.is_file(): # Single file translation
    print(translate_and_merge_file(project_path))
else: # Folder
    print(merge_asm_code(
        get_boot(),
            *[translate_and_merge_file(file_path)
             for file_path in project_path.glob('*.vm') if not is_hidden(file_path)] 
            ))
