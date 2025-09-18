// 3-qubit Grover, marked state 101
SEED 1
ALLOCATE r 3

# prepare uniform superposition
HADAMARD_LAYER r

GROVER_ITERATE r "101"
MEASURE r SHOTS 64