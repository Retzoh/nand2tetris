// This file is part of www.nand2tetris.org
// and the book "The Elements of Computing Systems"
// by Nisan and Schocken, MIT Press.
// File name: projects/04/Mult.asm

// See https://www.nand2tetris.org/course, project 4 for the hack machine
// langage and assembler specifications

// Multiplies R0 and R1 and stores the result in R2.
// (R0, R1, R2 refer to RAM[0], RAM[1], and RAM[2], respectively.)

// R0 * R1 <=> add R0 to 0, R1 times
(INIT)   // Start
@result     // result=0
M=0
@R1         // i=R1
D=M
@i
M=D
@R0         // inc=R0
D=M
@inc
M=D


(LOOP)   // Loop (while i > 0, result += inc, i--)
@i          //If i == 0, GOTO RETURN
D=M
@RETURN
D;JEQ
@inc        // add inc to result
D=M
@result
M=M+D
@i          // i -= 1
M=M-1
@LOOP       // Continue loop
0;JMP

(RETURN) // Return
@result     // result -> R2 (output)
D=M
@R2
M=D
@END        // End
0;JMP

(END)    // End loop
@END
0;JMP
