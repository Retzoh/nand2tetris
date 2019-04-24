import sys
from pathlib import Path


##############
# File parsing
##############


def load_asm_file():
    def read_lines():
        return Path(sys.argv[1]).expanduser().read_text().split('\n')

    def filter_comment_and_blank_in_lines(lines):
        def filter_comment_and_blank_in_line(l):
            return l.replace(' ', '').replace('\t', '').split('//')[0]
        return [filter_comment_and_blank_in_line(l) for l in lines]
	
    def remove_empty_lines(file):
        return [l for l in file if len(l) > 0]
    
    return remove_empty_lines(
        filter_comment_and_blank_in_lines(
            read_lines()))


def is_label(line):
    return line.startswith('(') and line.endswith(')')


def to_label(line):
    return line.strip('()')


def is_a_instruction(line):
    return line.startswith('@')


def to_variable(line):
    return line[1:]


##############
# Symbol table 
##############
def default_symbol_table():
    return {
	key: (value)
	for key, value in {
	    **{'@SP': 0,
	       '@LCL': 1,
	       '@ARG': 2,
	       '@THIS': 3,
	       '@THAT': 4,
	       '@SCREEN': 0x4000,
	       '@KBD': 0x6000,},
	     **{f'@R{i}': i
		for i in range(16)}
    }.items()}


def inc_p_c(line, program_counter):
    if is_label(line):
        return program_counter
    return program_counter + 1


def insert_into(symbol_table, label, value):
    return {**symbol_table, 
            **{label: value}}

 
def add_label(label, symbol_table, program_counter):
    if label in symbol_table:
        raise ValueError(f'Duplicate attemp at '
            f'declaring label {label} '
            f'before line {program_counter+1}')
    return insert_into(symbol_table, '@' + label, program_counter)


def find_and_add_labels(line, program_counter, symbol_table):
    if is_label(line):
        return add_label(to_label(line), symbol_table, 
                    program_counter)
    return symbol_table


def add_user_labels(asm_file, program_counter, symbol_table):
    for line in asm_file:
        symbol_table = find_and_add_labels(line, program_counter,
            symbol_table)
        program_counter = inc_p_c(line, program_counter)
    return symbol_table
    
    # Functional version
    if len(asm_file) == 0:
        return symbol_table
    return add_user_labels(
        asm_file[1:], 
        inc_p_c(asm_file[0], program_counter), 
        find_and_add_labels(asm_file[0], program_counter, 
            symbol_table))


def is_int(s):
    try: 
        int(s)
        return True
    except ValueError:
        return False


def find_and_add_variables(line, variable_counter, symbol_table):
    if not is_a_instruction(line):
        return variable_counter, symbol_table
    if line in symbol_table:
        return variable_counter, symbol_table
    if is_int(line[1:]):
        return variable_counter, insert_into(symbol_table, line, 
            int(line[1:]))
    return variable_counter+1, insert_into(symbol_table, line, 
        variable_counter) 


def add_user_variables(asm_file, variable_counter, symbol_table):
    for line in asm_file:
        variable_counter, symbol_table = find_and_add_variables(line, 
            variable_counter, symbol_table)
    return symbol_table

    # Functional version
    if len(asm_file) == 0:
        return symbol_table
    return add_user_variables(
        asm_file[1:],
        *find_and_add_variables(asm_file[0], variable_counter, 
            symbol_table))


############
# Assembling
############


def int_to_binary(integer, order=15):
    if order < 0:
        return ''
    return (
        '1' if integer >= 2**order else '0'
        ) + int_to_binary(integer % 2**order, order - 1)


def get_mem_bit(line):
    return '?'


def get_dest(line):
    if '=' in line:
        return line.split('=')[0]
    return ''


def assemble_dest(dest):
    return (
        ('1' if 'A' in dest else '0') +
        ('1' if 'D' in dest else '0') +
        ('1' if 'M' in dest else '0'))


def get_jump(line):
    if ';' in line:
        return line.split(';')[1]
    return ''


def assemble_jump(jump):
    if len(jump) == 0:
        return '000'
    if jump == 'JMP':
        return '111'
    return (
        str(1 * ('L' in jump or jump == 'JNE')) + 
        str(1 * ('E' in jump and jump != 'JNE')) +
        str(1 * ('G' in jump or jump == 'JNE'))
    )


def get_comp(line):
    if '=' in line:
        return line.split('=')[1].split(';')[0]
    return line.split(';')[0]


def get_op_code(op):
    if op == '0':
        return '101010'
    if op == '1':
        return '111111'
    if op == '-1':
        return '111010'
    if op == 'D':
        return '001100'
    if op == 'A':
        return '110000'
    if op == '!D':
        return '001101'
    if op == '!A':
        return '110001'
    if op == '-D':
        return '001111'
    if op == '-A':
        return '110011'
    if op == 'D+1':
        return '011111'
    if op == 'A+1':
        return '110111'
    if op == 'D-1':
        return '001110'
    if op == 'A-1':
        return '110010'
    if op == 'D+A':
        return '000010'
    if op == 'D-A':
        return '010011'
    if op == 'A-D':
        return '000111'
    if op == 'D&A':
        return '000000'
    if op == 'D|A':
        return '010101'
    raise ValueError(f'Unrecognized op code: {op}')


def assemble_comp(comp):
    return ('1' if 'M' in comp else '0') + \
        get_op_code(comp.replace('M', 'A'))


def assemble_c_instruction(line):
    return (
        '111' + 
        assemble_comp(get_comp(line)) + 
        assemble_dest(get_dest(line)) +
        assemble_jump(get_jump(line)))


def assemble_line(line, symbol_table):
    if is_label(line):
        return ''
    if is_a_instruction(line):
        return int_to_binary(symbol_table[line]) + '\n'
    return assemble_c_instruction(line) + '\n'


def assemble_file(asm_file, symbol_table):
    return ''.join([
        assemble_line(line, symbol_table)
        for line in asm_file
    ])

    # Functional version
    if len(asm_file) == 0:
        return ''
    return assemble_line(asm_file[0], symbol_table) + \
        assemble_file(
            asm_file[1:],
            symbol_table)


asm_file = load_asm_file()

print(assemble_file(asm_file, 
    add_user_variables(asm_file, 16, 
        add_user_labels(asm_file, 0, default_symbol_table()))), end='')
