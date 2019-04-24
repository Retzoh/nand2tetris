// This file is part of www.nand2tetris.org
// and the book "The Elements of Computing Systems"
// by Nisan and Schocken, MIT Press.
// File name: projects/04/Fill.asm

// Runs an infinite loop that listens to the keyboard input.
// When a key is pressed (any key), the program blackens the screen,
// i.e. writes "black" in every pixel;
// the screen should remain fully black as long as the key is pressed. 
// When no key is pressed, the program clears the screen, i.e. writes
// "white" in every pixel;
// the screen should remain fully clear as long as no key is pressed.

// This programm uses the following convention:
// If a key is pressed on the keyboard
//   @key==1
// else:
//   @key==0
// 
// If the screen is filled
//   @fill_value==-1
// else:
//   @fill_value==0

// This way we know that:
// If @key + @fill_value == 0
//   we don't need to refresh the screen
// Else
//   we have to:
//     - set @fill_value to -@key
//       (pressed -> @key=1 -> @fill_value = -1 -> black)
//       (not pressed -> @key=0 -> @fill_value = -0 = 0 -> white)
//     - fill the screen with @fill_value
(INIT)    // Initialize values
@fill_value  // screen is blank
M=0
@key         // no key is pressed
M=0
@counter     // counter to count pixel batches
M=0
@addr        // Pointer to 16-pixels
M=0

(MAIN)    // Infinite loop
            // Detect if key was pressed / unpressed
@key          // Set key to 1 if pressed, else 0
M=0             // Default 0
@KBD            // Get keyboard input
D=M             // if kb is 0 (<=> no key pressed)
@SKIP           //   dont set key to 1 (GOTO SKIP)
D;JEQ           // else:
@key            //   set key to 1
M=1
(SKIP) 
@key          // If key + fill_value == 0 -> skip fill screen
D=M              // D = key
@fill_value
D=D+M            // D = key + fill_value
@MAIN            // If D == 0
D;JEQ              // continue (GOTO MAIN)
@key          // Else fill_value = -key 
D=M             // aka 0 if not pressed, -1 if pressed
@fill_value
M=-D
          // Fill the screen with fill_value
@SCREEN     // Set addr to start of screen
D=A
@addr
M=D
@8191        // counter = 8 191 = 256 * 32 - 1
D=A          //   (aka row * col / 16 - 1)
@counter
M=D
(LOOP)      // while counter >= 0:
@fill_value    // Load caracter to print
D=M  
@addr          // Write fill_value to RAM[addr]
M=M+1             // Move addr to next batch of 16 pixels (This is too soon but saves op later)
A=M-1             // Point to the pixels to draw on  (So we have to -1 the pointer)
M=D               // and print on screen
@counter              // counter -= 1
MD=M-1
@LOOP         // If counter >= 0 -> continue loop
D;JGE
@MAIN             // Return to inifite loop
0;JMP
