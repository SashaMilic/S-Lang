SEED 1
ALLOCATE r 2

IMPORT "examples/fn_prep.slang"

CALLR k = PREP(1, 0)
TRACE "Prepared and got k"
HADAMARD_LAYER r
PROBS
MEASURE r SHOTS 16