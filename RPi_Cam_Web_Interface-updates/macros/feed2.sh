#!/bin/bash
# Explicit implementation: OpenBSD nc has different EOF behavior.
exec /bin/nc.traditional -q 0 -w 3 localhost 33333 <<< "F"
