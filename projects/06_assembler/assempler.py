"""Assembler for the hack computer

Usage:

python assembler.py file

Loads an assembly file and translate it into machine language for the hack 
computer as specified in project 6 of the nand2tetris course.

# Assembler implementation details
This assembler works in 3 steps:
1. Load and clean the assembly file
2. Construct a symbol table referencing the user-defined labels and variables
3. Translate the asm file to binary code
The file follows this pattern:
File parsing (line 147)
Symbol table (line 207)
Assembling (line 322)
??

# Assembly language specifications:

## Note on registers
The Hack computer has three 16-bit registers: the D-, A- and M-registers.
The D-register is used to store "data" that can be used as input for the ALU.
The A-register can be used in the same way but it also has a second role:
    The RAM use it as address input. So any read/write instruction to the RAM is
    done on the register which has the value of the A-register as address.
The M-register represents this register in the RAM that is 'pointed' onto by the
    A-register. Reading/writing to it consists actually in reading/writing to 
    the RAM. 

## Assembly instructions
There are three types of assembly instructions: A-instructions, C-instructions 
and labels. Indents and blanks are ignored. Comments can only be in-line, start
with "//" and are ignored.

## A-instructions
- `"@" integer` where integer is a number in the range 0->32768. Sets the A 
    register to contain the specified integer. Ex: @42
- `"@" label` where label is a user-defined label. Sets the A register to 
    contain the code address corresponding to the label. 
    Labels are upper-cased by convention, with "_" as word separator. Ex: @MAIN
- `"@" variable` where variable is a user-defined variable. Sets the A register 
    to contain the RAM adress corresponding to the variable. If a variable is 
    encountered for the first time, it is automatically assigned an address. 
    The address assignment starts at RAM address 16 and increments. 
    Variables are lowercased by convention, with "_" as word separator. Ex: @i

## C-instructions
`(Dest-code "=")? op-code (";" jump-code)?`
- op-code:
    Only the op-code is mandatory. It represents an instruction to be performed 
    by the ALU. Available codes and their associated outputs are:
    - 0 -> the constant 0
    - 1 -> the constant 1
    - -1 -> the constant -1
    - D -> the value contained in the D-register
    - A -> the value contained in the A-register
    - M -> the value contained in the M-Register
    - !D -> bit-wise negation of the D-register
    - !A -> bit-wise negation of the A-register
    - !M -> bit-wise negation of the M-register
    - -D -> numerical negation of the D-register using 2's complement
    - -A -> numerical negation of the A-register using 2's complement
    - -M -> numerical negation of the M-register using 2's complement
    - D+1 -> 1 + value of the D-register 
    - A+1 -> 1 + value of the A-register 
    - M+1 -> 1 + value of the M-register 
    - D-1 -> -1 + value of the D-register
    - A-1 -> -1 + value of the A-register
    - M-1 -> -1 + value of the M-register
    - D+A -> value of the D-register + value of the A-register
    - D+M -> value of the D-register + value of the M-register
    - D-A -> value of the D-register - value of the A-register
    - D-M -> value of the D-register - value of the M-register
    - A-D -> value of the A-register - value of the D-register
    - M-D -> value of the M-register - value of the D-register
    - D&A -> bit-wise AND of the values of the D and A registers
    - D&M -> bit-wise AND of the values of the D and M registers
    - D|A -> bit-wise OR of the values of the D and A registers
    - D|M -> bit-wise OR of the values of the D and M registers
- dest-code: 
    If specified, should be followed with a "=" character. Available codes are:
    - D -> write the ALU instruction's output to the D-register
    - A -> write the ALU instruction's output to the A-register
    - M -> write the ALU instruction's output to the M-register
    - AD -> write the ALU instruction's output to the A- and D-registers
    - AM -> write the ALU instruction's output to the A- and M-registers
    - MD -> write the DLU instruction's output to the D- and M-registers
    - ADM -> write the DLU instruction's output to the A-, D- and M-registers
- jump-code:
    If specified, should be preceded by a ";" character. The computer is fed
    with a programm containing one binary instruction per line. Each of those
    instructions should be seen as having a number, starting at 0 and increasing
    by one. The jump-code lets the computer jump to the instruction of which the
    address is contained in the A-register if the result of the current
    operation satisfies a certain condition. Available codes and corresponding
    conditions are:
    - JEQ -> jump if the output is equal to 0
    - JLT -> jump if the output is lower than 0
    - JLE -> jump if the output is lower than 0 or equal to 0
    - JGT -> jump if the output is greater than 0
    - JGE -> jump if the output is greater than 0 or equal to 0
    - JNE -> jump if the output is not 0
    - JMP -> just jump wathever the output
- Examples:
@3         // Set A to 3
0;JMP      // unconditional jump to code line 3.
@42        // Set A to 42
D=D-A;JEQ: // Set D to D-A. if D-A == 0, jump to code line nb 42.
@i         // Point onto var i, the real RAM address is handled by the assembler
M=A        // Set corresponding value to it's own address
A=A+1      // Point to the RAM address just after i

## Labels
`"(" LABEL_NAME ")"`
When performing a jump, the appropriate line of code should be put in the 
A-register. Setting directly the line number with a `@integer` instruction
is delicate since one has to figure out the line number ignoring comments, 
blank lines, etc... And all the addresses have to be updated if the beginning of
the assembly code is edited afterward.
So the assembly language proposes to mark lines with a label using the `(LABEL)`
syntax. The assembler will then automatically adjust any `@LABEL` instruction 
to match the desired code line at assembly time.
Example:
// This code runs a loop 42 times and then stops in an infinite empty loop
00    @MAIN      // @2
01    0;JMP
   (MAIN)
02    @42        // Set D to 42
03    D=A
04    @DECREMENT // @6
05    0;JMP
   (DECREMENT)
06    D=D-1      // Decrement D
07    @END       // @11
08    D;JEQ      // Go there if D==0
09    @DECREMENT // Or continue the loop
10    0;JMP
   (END)
11    @END       // Infinity loop to end the programm
12    0;JMP
"""

import sys
from pathlib import Path
import re


##############
# File parsing
##############


def load_asm_file():
    """Read the asm file and preprocess it

    The path to the file is treated as a global variable.
    Preprocessing includes:
    - Remove carriage returns and split file on new lines
    - Remove comments and blanks in the lines
    - Remove empty lines
    """
    def read_lines():
        """Read the file given as script argument and split on new lines
        
        Carriage returns are removed.
        """
        return Path(sys.argv[1]).expanduser().read_text().replace(
            '\r', '').split('\n')

    def filter_comment_and_blank_in_lines(lines):
        """Remove blanks and trailing comments from each line

        Anything inside a line, after a "//" sequence is a comment.
        """
        def filter_comment_and_blank_in_line(l):
            return re.sub('\s', '', l).split('//')[0]
        return [filter_comment_and_blank_in_line(l) for l in lines]
	
    def remove_empty_lines(file):
        return [l for l in file if len(l) > 0]
    
    return remove_empty_lines(
        filter_comment_and_blank_in_lines(
            read_lines()))


def is_label(line):
    """Recognise "label" declarations
    
    A label is an line in the form `"(" LABEL_NAME ")"`
    """
    return line.startswith('(') and line.endswith(')')


def extract_label_name(label_declaration):
    """Extract the label name from a label instruction"""
    return label_declaration.strip('()')


def is_a_instruction(line):
    """Recognise "A-instructions"
    
    An A-instruction starts with "@"
    """
    return line.startswith('@')


##############
# Symbol table 
##############


def default_symbol_table():
    """Construct a symbol table containing the pre-defined variables

    Those variables are:
    - SP: VM stack-pointer, RAM[0]
    - LCL: VM local variable pointer, RAM[1]
    - ARG: VM function argument pointer, RAM[2]
    - THIS: VM object pointer, RAM[3]
    - THAT: VM array pointer, RAM[4]
    - SCREEN: base address for the screen memory-map, RAM[0x4000]
    - KBD: address of the keyboard memory-map, RAM[0x6000]
    - R0 -> R15: Shortcuts for the first 16 RAM locations
    """
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
    """Increment `program_counter` if `line` is an instruction"""
    if is_label(line):
        return program_counter
    return program_counter + 1


def insert_into(symbol_table, label, value):
    """Return a copy of `symbol_table` with the `label: value` pair added"""
    return {**symbol_table, 
            **{label: value}}

 
def add_label(label, symbol_table, program_counter):
    """Add a label to the symbol table"""
    if label in symbol_table:
        raise ValueError(f'Duplicate attemp at '
            f'declaring label {label} '
            f'before line {program_counter+1}')
    return insert_into(symbol_table, '@' + label, program_counter)


def find_and_add_labels(line, program_counter, symbol_table):
    """Look for a label declaration in `line` and add it to the symbol table"""
    if is_label(line):
        return add_label(extract_label_name(line), symbol_table, 
                    program_counter)
    return symbol_table


def add_user_labels(asm_lines, program_counter, symbol_table):
    """Add the user-defined labels in `asm_lines` to `symbol_table`"""
    for line in asm_lines:
        symbol_table = find_and_add_labels(line, program_counter,
            symbol_table)
        program_counter = inc_p_c(line, program_counter)
    return symbol_table


def is_int(string):
    """Test if string is an int"""
    try: 
        int(string)
        return True
    except ValueError:
        return False


def find_and_add_variables(line, variable_counter, symbol_table):
    """Recognise if line declares a new variable and add it to `symbol_table`
    
    This function assumes that labels have already been added to the 
    symbol-table. So any `@var` instruction where `var` is not in `symbol_table`
    is a new variable.
    """
    if not is_a_instruction(line):
        return variable_counter, symbol_table
    if line in symbol_table:
        return variable_counter, symbol_table
    if is_int(line[1:]):
        return variable_counter, insert_into(symbol_table, line, 
            int(line[1:]))
    return variable_counter+1, insert_into(symbol_table, line, 
        variable_counter) 


def add_user_variables(asm_lines, variable_counter, symbol_table):
    """Add the user-defined variables to the symbol_table

    This function assumes that labels have already been added to `symbol_table`.
    """
    for line in asm_lines:
        variable_counter, symbol_table = find_and_add_variables(line, 
            variable_counter, symbol_table)
    return symbol_table


############
# Assembling
############


def int_to_binary(integer, bits=15):
    """Convert an integer to it's binary representation, as string"""
    if bits < 0:
        return ''
    high_bit_value = 2**bits
    return (
        '1' if integer >= high_bit_value else '0'
        ) + int_to_binary(integer % high_bit_value, bits-1)


def get_dest(c_instruction):
    """Return the destination part of a c-instruction

    C-instruction format:
    `(Dest-code "=")? op-code (";" jump-code)?`
    """
    return c_instruction.split('=')[0] if '=' in c_instruction else ''


def assemble_dest(dest):
    """Convert an assembly destination to its binary counterpart

    The legal assembly destinations are: A, D, M, AD, AM, MD, ADM. 
    The binary representation of the destination is:
    X  X  X
    ^  ^  ^
    |  |  Write to M
    |  |  ----------
    |  Write to D
    |  ----------
    Write to A
    """
    if dest not in ['', "A", "D", "M", "AD", "AM", "MD", "ADM"]:
        raise ValueError(f"Unrecognised c-instruction destination: '{dest}'")
    return (
        ('1' if 'A' in dest else '0') +
        ('1' if 'D' in dest else '0') +
        ('1' if 'M' in dest else '0'))


def get_jump(c_instruction):
    """Return the jump part of a c-instruction

    C-instruction format:
    `(Dest-code "=")? op-code (";" jump-code)?`
    """
    return c_instruction.split(';')[1] if ';' in c_instruction else ''


def assemble_jump(jump):
    """Convert an assembly jump code to its binary counterpart

    The legal assembly destinations are: JMP, JEQ, JLT, JLE, JGT, JGE, JNE
    The binary representation of the jump is:
    X  X  X
    ^  ^  ^
    |  |  Jump if output is greater than 0
    |  |  --------------------------------
    |  Jump if output is equal to 0
    |  ----------------------------
    Jump if output is lower than 0
    """
    if len(jump) == 0:
        return '000'
    if jump not in ["JMP", "JEQ", "JLT", "JLE", "JGT", "JGE", "JNE"]:
        raise ValueError(f"Unrecognized jump instruction: {jump}")
    if jump == 'JMP':
        return '111'
    return (
        str(1 * ('L' in jump or jump == 'JNE')) + 
        str(1 * ('E' in jump and jump != 'JNE')) +
        str(1 * ('G' in jump or jump == 'JNE'))
    )


def get_op_code(c_instruction):
    """Return the op-code part of a c-instruction

    C-instruction format:
    `(Dest-code "=")? op-code (";" jump-code)?`
    """
    if '=' in c_instruction:
        return c_instruction.split('=')[1].split(';')[0]
    return c_instruction.split(';')[0]


def assemble_op_code_no_M(op_code):
    """Convert an assembly op code to its binary counterpart

    Note that this method assumes that the A/M switch is made. It
    will thus only recognise operations on the A register. Any "M" has to be 
    replaced with "A".
    The legal assembly destinations are: 0, 1, -1, D, M, !D, !A, -D, -A, D+1, 
    A+1, D-1, A-1, D+A, D-A, A-D, D&A, D|A.
    The binary representation of the op-code is:
    X  X  X  X  X  X
    ^  ^  ^  ^  ^  ^
    |  |  |  |  |  Flip the output bits
    |  |  |  |  |  --------------------
    |  |  |  |  operation switch (0->`AND`, 1->`+`)
    |  |  |  |  -----------------------------------
    |  |  |  flip the A/M input's bits
    |  |  |  -------------------------
    |  |  Zero the A/M input
    |  |  ------------------
    |  Flip the D input's bits
    |  -----------------------
    Zero the D input
    """
    if op_code == '0':
        return '101010'
    if op_code == '1':
        return '111111'
    if op_code == '-1':
        return '111010'
    if op_code == 'D':
        return '001100'
    if op_code == 'A':
        return '110000'
    if op_code == '!D':
        return '001101'
    if op_code == '!A':
        return '110001'
    if op_code == '-D':
        return '001111'
    if op_code == '-A':
        return '110011'
    if op_code == 'D+1':
        return '011111'
    if op_code == 'A+1':
        return '110111'
    if op_code == 'D-1':
        return '001110'
    if op_code == 'A-1':
        return '110010'
    if op_code == 'D+A':
        return '000010'
    if op_code == 'D-A':
        return '010011'
    if op_code == 'A-D':
        return '000111'
    if op_code == 'D&A':
        return '000000'
    if op_code == 'D|A':
        return '010101'
    raise ValueError(f'Unrecognized op code: {op_code}')


def assemble_op_code(op_code):
    """Assemble the A/M switch and the op-code"""
    return ('1' if 'M' in op_code else '0') + \
        assemble_op_code_no_M(op_code.replace('M', 'A'))


def assemble_c_instruction(c_instruction):
    """Assemble a c-instruction

    The binary representation of a c-instruction is
    111 a.ffff.ff dd.d jjj
    ^^^ ^ ^^^^ ^^ ^^ ^ ^^^
    ||| | |||| || || | jump instruction
    ||| | |||| || || | ----------------
    ||| | |||| || Destination instruction
    ||| | |||| || -----------------------
    ||| | Operation instruction
    ||| | ---------------------
    ||| A/M switch (0->A, 1->M)
    ||| -----------------------
    c-instruction marker
    """
    return (
        '111' + 
        assemble_op_code(get_op_code(c_instruction)) + 
        assemble_dest(get_dest(c_instruction)) +
        assemble_jump(get_jump(c_instruction)))


def assemble_line(line, symbol_table):
    """Recognize if a line is a label, A- or C-instruction and assemble it"""
    if is_label(line):
        return ''
    if is_a_instruction(line):
        return int_to_binary(symbol_table[line]) + '\n'
    return assemble_c_instruction(line) + '\n'


def assemble_lines(asm_lines, symbol_table):
    return ''.join([
        assemble_line(line, symbol_table)
        for line in asm_lines
    ])


asm_file = load_asm_file()

print(assemble_lines(asm_file, 
    add_user_variables(asm_file, 16, 
        add_user_labels(asm_file, 0, default_symbol_table()))), end='')
