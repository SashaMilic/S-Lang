SEED 10
ALLOCATE r 3
H r[0]
CNOT r[0], r[1]
MEASURE r[0] AS c0
MEASURE r[1] AS c1
IF (c0 == 1 && c1 == 0) {
  X r[2]
}
ELIF (c0 == 1 || c1 == 1) {
  Z r[2]
}
ELSE {
  H r[2]
}
ENDIF
MEASURE r SHOTS 32
