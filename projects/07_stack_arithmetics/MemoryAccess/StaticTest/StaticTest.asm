// push constant 111
@111
D=A
@SP
A=M
M=D
@SP
M=M+1
// push constant 333
@333
D=A
@SP
A=M
M=D
@SP
M=M+1
// push constant 888
@888
D=A
@SP
A=M
M=D
@SP
M=M+1
// pop static 8
@SP
M=M-1
@StaticTest.{i}
D=A
@SP
A=M+1
M=D
A=A-1
D=M
A=A+1
A=M
M=D
// pop static 3
@SP
M=M-1
@StaticTest.{i}
D=A
@SP
A=M+1
M=D
A=A-1
D=M
A=A+1
A=M
M=D
// pop static 1
@SP
M=M-1
@StaticTest.{i}
D=A
@SP
A=M+1
M=D
A=A-1
D=M
A=A+1
A=M
M=D
// push static 3
@StaticTest.{i}
D=M
@SP
A=M
M=D
@SP
M=M+1
// push static 1
@StaticTest.{i}
D=M
@SP
A=M
M=D
@SP
M=M+1
// sub
@SP
M=M-1
A=M
D=M
@SP
M=M-1
A=M
M=M-D
@SP
M=M+1
// push static 8
@StaticTest.{i}
D=M
@SP
A=M
M=D
@SP
M=M+1
// add
@SP
M=M-1
A=M
D=M
@SP
M=M-1
A=M
M=D+M
@SP
M=M+1
