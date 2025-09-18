// Should approximately return to the input basis state
SEED 1
ALLOCATE r 4
# prepare a random-ish basis state: |1010>
X r[1]
X r[3]

QFT r NOSWAP
IQFT r REVERSE=false

MEASURE r SHOTS 16